"""Read the accessibility hierarchy from uiautomator2."""

from __future__ import annotations

import logging
from typing import Optional

from .adb import AdbError

def fetch_u2(serial: Optional[str], quiet: bool = False) -> tuple:
    """连接设备并取**非压缩**全量层次。返回 (xml_text, meta)。

    失败一律抛异常 —— 不做「拿不到就退回 dumpsys」的静默降级，
    那会让同一条命令有时候是一体式结果、有时候只有一半。
    """
    try:
        import uiautomator2 as u2
    except ImportError as e:
        raise AdbError(
            "未安装 uiautomator2。本工具以它为主数据源，装不上就无法产出结果。\n"
            "  安装： <python> -m pip install uiautomator2\n"
            f"  (import 报错：{e})"
        )
    try:
        d = u2.connect(serial) if serial else u2.connect()
    except Exception as e:
        raise AdbError(f"uiautomator2 连接失败（{serial}）：{type(e).__name__}: {e}")

    try:
        info = dict(d.info or {})
    except Exception:
        info = {}
    try:
        info = dict(info, window_size=list(d.window_size()))
    except Exception:
        pass

    try:
        xml = d.dump_hierarchy(compressed=False)
    except TypeError:
        xml = d.dump_hierarchy()          # 老版本没有 compressed 形参
    except Exception as e:
        raise AdbError(f"dump_hierarchy 失败：{type(e).__name__}: {e}")

    if not xml or "<hierarchy" not in xml:
        raise AdbError("dump_hierarchy 返回内容不含 <hierarchy>，无法解析")

    try:
        import importlib.metadata as md
        ver = md.version("uiautomator2")
    except Exception:
        ver = "?"

    if not quiet:
        logging.info("[u2] uiautomator2 %s 已连接，层次 %s 字节", ver, len(xml))
    return xml, {"version": ver, "info": info}
