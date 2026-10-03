"""Read and write the existing full-tree JSON format."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from typing import Optional

from .terminal import C, c

# Windows 保留设备名：os.replace 打到这些名字上会失败或行为未定义，
# 而 `--out NUL` 是本仓库既有的离线检查写法，必须继续可用。
_WINDOWS_DEVICE_NAMES = {"nul", "con", "prn", "aux"}
_WINDOWS_DEVICE_RE = re.compile(r"(com|lpt)[1-9]")


def _is_device_target(out_path: str) -> bool:
    """目标是否是设备文件（NUL / CON / COM1 / os.devnull 等），这类目标只能直写。"""
    if out_path == os.devnull:
        return True
    stem = os.path.splitext(os.path.basename(out_path))[0].lower()
    return stem in _WINDOWS_DEVICE_NAMES or bool(_WINDOWS_DEVICE_RE.fullmatch(stem))


def emit_json(obj: dict, out_path: Optional[str]) -> None:
    """写 JSON。文件目标走原子替换，失败时不留半成品也不残留临时文件。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if not out_path:
        print(text)
        return
    payload = text + "\n"
    if _is_device_target(out_path):
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
    else:
        # dirname 必须先 abspath：os.path.dirname("full.json") 是空串，
        # mkstemp(dir="") 的行为不可靠。
        directory = os.path.dirname(os.path.abspath(out_path))
        fd, temp_name = tempfile.mkstemp(prefix=".tvuitree-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            os.replace(temp_name, out_path)
        except OSError:
            # 不清理就会在目标目录留下 .tmp：金样的「新文件」扫描会把它当成差异。
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    byte_count = len(payload.encode("utf-8"))
    print(c(f"[out] 已写入 {out_path}（{byte_count} 字节）", C.GRY), file=sys.stderr)


def emit_json_checked(obj: dict, out_path: Optional[str]) -> Optional[int]:
    """写 JSON；失败时打印中文说明并返回退出码 2，成功返回 None。

    退出码与文案属于 interfaces：AGENTS.md 规定文件错误用 2，且不得吐 traceback。
    """
    try:
        emit_json(obj, out_path)
    except OSError as error:
        print(c(f"写不了 {out_path}：{error}", C.RED), file=sys.stderr)
        return 2
    return None


def load_full_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as source:
        obj = json.load(source)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的全量 JSON。")
    return obj
