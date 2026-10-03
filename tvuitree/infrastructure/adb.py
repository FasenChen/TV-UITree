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
        """掉线后重连一次；判据是 `adb devices` 的状态列，不是 connect 的回显措辞。

        回显措辞随 adb 版本与 locale 变化：`already connected` / `connected to` /
        `cannot connect` / `failed to connect` 都出现过。靠子串猜会把「回显里有
        connected 但设备其实 offline」判成重连成功，让重试继续打向已死设备，
        把错误推迟成更难懂的下游异常。这里改用与措辞无关的事实：设备在
        `adb devices` 里且状态列是 device。
        """
        if self._healing or not (self.serial and ":" in self.serial and self.auto_connect):
            return False
        self._healing = True
        try:
            try:
                self._popen(["connect", self.serial], timeout=25, heal=False)
                ok = self._serial_is_device()
            except AdbError:
                return False
            if ok:
                logging.warning("[adb] 连接中断，已自动重连 %s", self.serial)
            return ok
        finally:
            self._healing = False

    def _serial_is_device(self) -> bool:
        """本 serial 是否出现在 `adb devices` 且状态列为 device。"""
        try:
            rc, out, _err = self._popen(["devices"], timeout=20, heal=False)
        except AdbError:
            return False
        if rc != 0:
            return False
        for line in out.splitlines()[1:]:
            if not line.strip() or "\t" not in line:
                continue
            parts = line.split("\t")
            if parts[0].strip() == self.serial:
                return parts[1].strip() == "device"
        return False

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
        self._connected = False
        if self.serial and ":" in self.serial and self.auto_connect:
            try:
                rc, out, err = self._popen(["connect", self.serial], timeout=20)
                msg = (out + err).strip()
                if not quiet and msg:
                    logging.info("[adb] %s", msg)
            except AdbError:
                pass
        try:
            rc, out, _ = self._popen(["devices"], timeout=20, heal=False)
        except AdbError:
            return False
        if rc != 0:
            return False
        targets = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip() and "\t" in ln]
        if self.serial:
            # 已指定目标：成员判据不变（README 记录的 no_connect 行为依赖它）
            self._connected = self.serial in targets
            return self._connected
        if len(targets) == 1:
            # 只有一台设备时自动选中，保留给外部库使用者的便利
            self.serial = targets[0]
            self._connected = True
            return True
        if targets and not quiet:
            # 多台设备时绝不猜：静默选中一台会让所有读写打到调用方从未指定的设备
            logging.warning("[adb] 未指定 serial 且检测到多台设备，拒绝自动选择：%s",
                            ", ".join(targets))
        self._connected = False
        return False

    # ---- 基础信息 ----
    def props(self) -> dict:
        """读取设备属性；行数与键数不符时明确报错，绝不返回串位的值。

        `getprop <key>` 对未设置的键也输出恰好一行（空行），所以不能过滤空行：
        一过滤，后面的值就整体前移，model 会静默变成 device 的值 —— 而 device
        字段是模型和人工排查的共同证据，串位比缺失更伤信任。
        用 shell_raw 只取 stdout：shell() 会把非空 stderr 追加进来，污染行数。
        """
        keys = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
                "ro.build.version.release", "ro.build.version.sdk",
                "ro.build.version.incremental", "ro.product.cpu.abilist", "ro.build.type"]
        rc, out, err = self.shell_raw(";".join(f"getprop {k}" for k in keys), timeout=30)
        if rc != 0:
            raise AdbError(f"getprop 失败（exit={rc}）：{(err or out).strip()}")
        vals = [ln.strip() for ln in out.splitlines()]
        if len(vals) != len(keys):
            raise AdbError(
                f"getprop 返回 {len(vals)} 行，与请求的 {len(keys)} 个键不符；"
                "拒绝按行序配对，避免设备属性串位")
        return dict(zip(keys, vals))

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
