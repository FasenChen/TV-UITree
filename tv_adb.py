#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tv_adb.py — 设备接入层（tv_tree.py / tv_input.py / tv_shot.py 共用）

职责边界（只做这三件事）
------------------------
  1. 找到 adb 可执行文件；
  2. 连上设备，并在 adbd 掉线时自愈重连一次；
  3. 执行命令并把结果取回来，附带读设备/屏幕/窗口这几项基础信息。

**不含任何控件树解析逻辑** —— 那是 tv_tree.py 的事。
按键与截图也不在这里 —— 那是 tv_input.py / tv_shot.py 的事。

为什么单独成文件
----------------
三个脚本都要「找到 adb + 连上设备 + 执行命令」。写在各自文件里就是三份
同样的代码，改一处要改三处（本项目刻意去掉这类重复）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import Optional

DEFAULT_HOST = "192.168.31.102"
DEFAULT_PORT = 5555

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


class C:
    """终端着色。非 tty 或 --no-color 时整体关掉。"""

    _on = True
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"
    BLU = "\033[34m"; MAG = "\033[35m"; CYA = "\033[36m"; GRY = "\033[90m"

    @classmethod
    def off(cls):
        cls._on = False
        for name in ("R", "B", "DIM", "RED", "GRN", "YEL", "BLU", "MAG", "CYA", "GRY"):
            setattr(cls, name, "")


def c(text: str, color: str) -> str:
    return f"{color}{text}{C.R}" if C._on else text


def setup_console(no_color: bool = False) -> None:
    """Windows 控制台兼容 + 着色开关。

    编码这条是实测踩过的坑：本机 stdout 可能是 cp936 或 ascii。cp936 能显示中文
    就保留（切 UTF-8 反而会让重定向出来的文件乱码），只有编码根本无法表示中文
    （None/ascii）时才切到 UTF-8。
    """
    if no_color or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        C.off()
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", None) or "").lower()
            if enc in ("", "ascii", "us-ascii", "ansi_x3.4-1968"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass


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
                print(c(f"[adb] 连接中断，已自动重连 {self.serial}", C.YEL), file=sys.stderr)
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
                    print(c(f"[adb] {msg}", C.GRY), file=sys.stderr)
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


# ---- component 字符串处理 ----

def component_from_window(text: Optional[str]) -> Optional[str]:
    """`Window{... u0 com.pkg/.Cls}` → `com.pkg/.Cls`"""
    if not text:
        return None
    m = re.search(r"\s([A-Za-z][\w.]*)/([\w.$]+)\}", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"([A-Za-z][\w.]*)/([\w.$]+)", text)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def component_from_activity_record(text: Optional[str]) -> Optional[str]:
    """`ActivityRecord{... u0 com.pkg/.Cls t42}` → `com.pkg/.Cls`"""
    if not text:
        return None
    m = re.search(r"\s([A-Za-z][\w.]*)/([\w.$]+)\s", text + " ")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def normalize_component(comp: Optional[str]) -> Optional[tuple]:
    """`com.pkg/.Cls` → `("com.pkg", "com.pkg.Cls")`；不合法返回 None。"""
    if not comp or "/" not in comp:
        return None
    pkg, cls = comp.split("/", 1)
    if cls.startswith("."):
        cls = pkg + cls
    return (pkg, cls)


# ---- CLI 公共参数 ----

def add_conn_args(p: argparse.ArgumentParser) -> None:
    """三个脚本共用的设备接入参数。"""
    p.add_argument("--host", default=DEFAULT_HOST, help=f"电视 IP（默认 {DEFAULT_HOST}）")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"adb TCP 端口（默认 {DEFAULT_PORT}）")
    p.add_argument("--serial", default=None, help="直接指定 adb serial（如 USB 连接时的序列号）")
    p.add_argument("--address", default=None, help="直接指定 host:port，等价于 --host + --port")
    p.add_argument("--adb", default=None, help="adb 可执行文件路径（默认自动探测）")
    p.add_argument("--no-connect", action="store_true", help="不自动执行 adb connect")
    p.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    p.add_argument("-q", "--quiet", action="store_true", help="不打印诊断信息")


def resolve_serial(args) -> str:
    return args.serial or args.address or f"{args.host}:{args.port}"


def connect_device(args, quiet: bool = False) -> Optional[Adb]:
    """建 Adb 并连接。失败时打印可直接照做的排查步骤，返回 None。

    `--no-connect` 时不执行 adb connect，但仍会检查设备是否已在列表里。
    """
    serial = resolve_serial(args)
    adb = Adb(resolve_adb(args.adb), serial, auto_connect=not args.no_connect)
    if adb.connect(quiet=quiet or getattr(args, "quiet", False)):
        return adb
    print(c(f"无法连接 {serial}", C.RED), file=sys.stderr)
    print(c(f"  1) 电视与电脑在同一网段？  ping {args.host}", C.YEL), file=sys.stderr)
    print(c("  2) 电视已开启 ADB 调试 / 网络调试？", C.YEL), file=sys.stderr)
    print(c(f"  3) 端口对不对？  {adb.adb} connect {args.host}:{args.port}", C.YEL), file=sys.stderr)
    print(c("  4) adb 路径对不对？  --adb <路径>", C.YEL), file=sys.stderr)
    return None
