"""Send normalized remote-control keys through an injected ADB device."""

from __future__ import annotations

from collections.abc import Iterator

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
    """'DOWN' / 'dpad_down' / '20' → 'KEYCODE_DPAD_DOWN' / '20'"""
    k = name.strip()
    if k.isdigit():
        return k
    k = k.upper()
    k = KEY_ALIASES.get(k, k)
    if k.startswith("KEYCODE_"):
        return k
    return "KEYCODE_" + k


def send_key(adb, name: str) -> str | None:
    """发送按键。成功返回 None，失败返回错误说明。"""
    kc = normalize_keycode(name)
    rc, out, err = adb.shell_raw(f"input keyevent {kc}", timeout=20)
    blob = (out + err).strip()
    if rc != 0 or "Error" in blob or "Exception" in blob or "Unknown" in blob:
        return blob or f"exit={rc}"
    return None


def send_sequence(adb, keys: list[str], *, delay: float = 0.5, repeat: int = 1, sleep=time.sleep) -> Iterator[tuple[str, str | None]]:
    repetitions = max(1, repeat)
    for rep in range(repetitions):
        for index, key in enumerate(keys):
            yield normalize_keycode(key), send_key(adb, key)
            if delay > 0 and not (rep == repetitions - 1 and index == len(keys) - 1):
                sleep(delay)
