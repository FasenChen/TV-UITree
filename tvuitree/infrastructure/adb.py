"""Execute ADB commands and read Android TV device metadata."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import logging
from typing import Optional

from tvuitree.domain.component import component_from_window, component_from_activity_record

# Windows 上常见的 adb 位置（按顺序探测）
ADB_CANDIDATES = [
    r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe",
    r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe",
    r"C:\platform-tools\adb.exe",
    r"D:\platform-tools\adb.exe",
    r"D:\SoftwareInstalled\Android\android_sdk\platform-tools\adb.exe",
    r"C:\Android\Sdk\platform-tools\adb.exe",
]

# adb 报「设备掉线」时的典型措辞（实机 TV 上会偶发 device offline）
_OFFLINE_RE = re.compile(
    rb"device offline|device not found|no devices/emulators|connection reset|"
    rb"closed by remote|adb: device", re.I)


class AdbError(RuntimeError):
    """adb 层面的失败（找不到 adb / 超时 / 设备掉线且重连失败）。"""



def resolve_adb(explicit: Optional[str]) -> str:
    """按「显式指定 → PATH → 常见安装位置 → 环境变量」的顺序找 adb。"""
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    for cand in ADB_CANDIDATES:
        path = os.path.expandvars(cand)
        if os.path.isfile(path):
            return path
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env)
        if root:
            exe = "adb.exe" if os.name == "nt" else "adb"
            path = os.path.join(root, "platform-tools", exe)
            if os.path.isfile(path):
                return path
    return "adb"


class Adb:
    """一个 serial 对应一个实例。所有设备的读写都从这里出去。"""

    def __init__(self, adb_path: str, serial: Optional[str], auto_connect: bool = True):
        self.adb = adb_path
        self.serial = serial
        self.auto_connect = auto_connect
        self._connected = False
        self._healing = False          # 正在重连（防止递归）

    # ---- 基础执行 ----
    def _popen(self, args: list, timeout: float = 30.0, binary: bool = False,
               heal: bool = True):
        cmd = [self.adb] + (["-s", self.serial] if self.serial else []) + args
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb 超时({timeout}s)：{' '.join(args)}")
        except FileNotFoundError:
            raise AdbError(f"找不到 adb 可执行文件：{self.adb}")
        # 电视端 adbd 会主动断开（实测：连续操作后出现 device offline），
        # 此时自动重连一次再重试原命令，避免整轮采集作废。
        if heal and _OFFLINE_RE.search(p.stdout + p.stderr) and self._reconnect():
            return self._popen(args, timeout=timeout, binary=binary, heal=False)
        if binary:
            return p.returncode, p.stdout, p.stderr
        out = p.stdout.decode("utf-8", errors="replace")
        err = p.stderr.decode("utf-8", errors="replace")
        return p.returncode, out, err

    def _reconnect(self) -> bool:
        if self._healing or not (self.serial and ":" in self.serial and self.auto_connect):
            return False
        self._healing = True
        try:
            try:
                rc, out, err = self._popen(["connect", self.serial], timeout=25, heal=False)
            except AdbError:
                return False
            msg = out + err
            ok = "connected" in msg.lower() and "cannot" not in msg.lower()
            if ok:
                logging.warning("[adb] 连接中断，已自动重连 %s", self.serial)
            return ok
        finally:
            self._healing = False

    def shell(self, command: str, timeout: float = 30.0) -> str:
        rc, out, err = self._popen(["shell", command], timeout=timeout)
        return out + (("\n" + err) if err.strip() else "")

    def shell_raw(self, command: str, timeout: float = 30.0) -> tuple:
        """返回 (returncode, stdout, stderr)，用于需要看返回码的场景。"""
        return self._popen(["shell", command], timeout=timeout)

    def exec_out(self, args: list, timeout: float = 60.0) -> bytes:
        """二进制安全取回（screencap / dumpsys 都走这里，避开 shell 的换行改写）。"""
        rc, out, err = self._popen(["exec-out"] + args, timeout=timeout, binary=True)
        if rc != 0 and not out:
            raise AdbError(err.decode("utf-8", errors="replace").strip() or "exec-out 失败")
        return out

    # ---- 连接 ----
    def connect(self, quiet: bool = False) -> bool:
        if self.serial and ":" in self.serial and self.auto_connect:
            try:
                rc, out, err = self._popen(["connect", self.serial], timeout=20)
                msg = (out + err).strip()
                if not quiet and msg:
                    logging.info("[adb] %s", msg)
            except AdbError:
                pass
        rc, out, _ = self._popen(["devices"], timeout=20)
        targets = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip() and "\t" in ln]
        self._connected = bool(self.serial) and self.serial in targets
        if not self._connected and not self.serial:
            self._connected = bool(targets)
            if targets:
                self.serial = targets[0]
        return self._connected

    # ---- 基础信息 ----
    def props(self) -> dict:
        keys = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
                "ro.build.version.release", "ro.build.version.sdk",
                "ro.build.version.incremental", "ro.product.cpu.abilist", "ro.build.type"]
        out = self.shell(";".join(f"getprop {k}" for k in keys))
        vals = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return dict(zip(keys, vals + [""] * len(keys)))

    def screen(self) -> dict:
        """wm size / wm density → {width, height, physical, override, density}

        width/height 取 override（有就用），因为 a11y 报的 bounds 就是按 override 分辨率来的。
        """
        size_out = self.shell("wm size")
        den_out = self.shell("wm density")
        phys = ovr = None
        for ln in size_out.splitlines():
            m = re.search(r"(Physical|Override) size:\s*(\d+)x(\d+)", ln)
            if m:
                if m.group(1) == "Physical":
                    phys = (int(m.group(2)), int(m.group(3)))
                else:
                    ovr = (int(m.group(2)), int(m.group(3)))
        density = None
        m = re.search(r"Physical density:\s*(\d+)", den_out)
        if m:
            density = int(m.group(1))
        w, h = (ovr or phys or (0, 0))
        return {"width": w, "height": h, "physical": phys, "override": ovr,
                "density": density}

    def window_focus(self) -> dict:
        """窗口级焦点：哪一层窗口 / 哪个 Activity 在前台。"""
        out = self.shell("dumpsys window")
        info = {"mCurrentFocus": None, "mFocusedApp": None}
        for ln in out.splitlines():
            s = ln.strip()
            if s.startswith("mCurrentFocus="):
                info["mCurrentFocus"] = s.split("=", 1)[1].strip()
            elif s.startswith("mFocusedApp="):
                info["mFocusedApp"] = s.split("=", 1)[1].strip()
        info["component"] = (component_from_window(info["mCurrentFocus"])
                             or component_from_activity_record(info["mFocusedApp"]))
        return info
