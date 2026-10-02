"""Read and write the existing full-tree JSON format."""

from __future__ import annotations

import json
import sys
from typing import Optional

from .terminal import C, c


def _emit(obj: dict, out_path: Optional[str]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        byte_count = len((text + "\n").encode("utf-8"))
        print(c(f"[out] 已写入 {out_path}（{byte_count} 字节）", C.GRY), file=sys.stderr)
    else:
        print(text)


def _load_full(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as source:
        obj = json.load(source)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的全量 JSON。")
    return obj
