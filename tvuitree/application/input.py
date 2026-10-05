"""Send normalized remote-control keys through an injected ADB device."""

from __future__ import annotations

from collections.abc import Iterator

import re
import time

KEY_ALIASES = {
    "UP": "DPAD_UP", "DOWN": "DPAD_DOWN", "LEFT": "DPAD_LEFT", "RIGHT": "DPAD_RIGHT",
    "OK": "DPAD_CENTER", "ENTER": "ENTER", "CENTER": "DPAD_CENTER", "SELECT": "DPAD_CENTER",
    "BACK": "BACK", "HOME": "HOME", "MENU": "MENU", "SETTINGS": "SETTINGS",
    "PLAY": "MEDIA_PLAY_PAUSE", "PLAYPAUSE": "MEDIA_PLAY_PAUSE",
    "NEXT": "MEDIA_NEXT", "PREV": "MEDIA_PREVIOUS",
    "VOLUP": "VOLUME_UP", "VOLDOWN": "VOLUME_DOWN", "MUTE": "VOLUME_MUTE",
    "POWER": "POWER", "TAB": "TAB", "DEL": "DEL",
}


def normalize_keycode(name: str) -> str:
    """归一化单个键码；非法语法在任何设备操作前拒绝。"""
    k = name.strip()
    if re.fullmatch(r"[0-9]+", k):
        return k
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k):
        raise ValueError(f"非法键码：{name!r}")
    k = KEY_ALIASES.get(k.upper(), k.upper())
    code = k if k.startswith("KEYCODE_") else "KEYCODE_" + k
    if not re.fullmatch(r"KEYCODE_[A-Z0-9][A-Z0-9_]*", code):
        raise ValueError(f"非法键码：{name!r}")
    return code


def send_key(adb, name: str) -> str | None:
    """发送按键。成功返回 None，失败返回错误说明。"""
    kc = normalize_keycode(name)
    rc, out, err = adb.shell_raw(f"input keyevent {kc}", timeout=20)
    blob = (out + err).strip()
    if rc != 0 or "Error" in blob or "Exception" in blob or "Unknown" in blob:
        return blob or f"exit={rc}"
    return None


def send_sequence(adb, keys: list[str], *, delay: float = 0.5, repeat: int = 1, sleep=time.sleep) -> Iterator[tuple[str, str | None]]:
    keys = [normalize_keycode(key) for key in keys]
    repetitions = max(1, repeat)
    for rep in range(repetitions):
        for index, key in enumerate(keys):
            yield normalize_keycode(key), send_key(adb, key)
            if delay > 0 and not (rep == repetitions - 1 and index == len(keys) - 1):
                sleep(delay)
