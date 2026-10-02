"""Read default TV connection settings from the repository configuration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def load_device_config() -> dict[str, object]:
    """每次连接都重新读配置，使文件改动对下一次调用生效。"""
    try:
        with CONFIG_PATH.open(encoding="utf-8") as source:
            config = json.load(source)
    except FileNotFoundError as error:
        raise ValueError(f"缺少设备配置文件：{CONFIG_PATH}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取设备配置文件 {CONFIG_PATH}：{error}") from error
    if not isinstance(config, dict):
        raise ValueError(f"设备配置文件必须是 JSON 对象：{CONFIG_PATH}")
    return config


def save_device_config(config: dict[str, object]) -> None:
    """原子替换配置文件，写入失败时保留旧文件。"""
    target = CONFIG_PATH
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
        os.replace(temp_name, target)
    except OSError as error:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise ValueError(f"无法写入设备配置文件 {target}：{error}") from error
