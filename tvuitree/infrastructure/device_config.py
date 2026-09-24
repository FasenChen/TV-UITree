"""Read default TV connection settings from the repository configuration."""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def load_device_config() -> dict[str, object]:
    """Read the config on each connection so changes apply to the next call."""
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
