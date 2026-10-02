"""Collect and summarize TV UI state for both CLI and MCP."""

from __future__ import annotations

from typing import Optional

from tvuitree.domain.observation import DEFAULT_MAX_NODES, summarize_full_json
from tvuitree.domain.visible import select_visible

def collect_full_json(*, adb, serial: Optional[str], save_raw: Optional[str] = None,
                      quiet: bool = False, use_dumpsys: bool = True) -> dict:
    """从已连接的 ``Adb`` 采集一份完整 JSON，供 CLI 与 MCP 共用。"""
    from tvuitree.domain.tree.capture import run_align
    from tvuitree.infrastructure.snapshot import snapshot
    from tvuitree.domain.tree.output import build_full_json
    from tvuitree.infrastructure.adb import AdbError
    import datetime as dt

    anomalies: list = []
    snap = snapshot(adb, serial, save_raw, quiet, use_dumpsys=use_dumpsys,
                    anomalies=anomalies)
    if use_dumpsys and snap["block"] is None:
        raise AdbError(
            "dumpsys 里没有可用的 ACTIVITY 段，拿不到补充源。"
            "（若确认不需要补充源，用 --no-dumpsys）"
        )
    u2_roots, view_roots, stats = run_align(snap)
    full = build_full_json(
        u2_roots, view_roots, snap["u2_meta"], snap["dev"], snap["screen"],
        snap["win"], stats, snap["pkg"], snap,
        show_dumpsys=use_dumpsys,
        captured_at=dt.datetime.now().isoformat(timespec="seconds"),
    )
    full["_parse_anomalies"] = list(anomalies)
    return full


def collect_observation(*, adb=None, serial: Optional[str] = None,
                        full_json: Optional[dict] = None,
                        save_raw: Optional[str] = None, quiet: bool = False,
                        use_dumpsys: bool = True,
                        max_nodes: int = DEFAULT_MAX_NODES) -> dict:
    """统一观察 API。

    传入 ``full_json`` 时走离线摘要；传入 ``adb`` 时实时采集后摘要。
    两条路径最终都经过 ``summarize_full_json``，因此 CLI 和 MCP 的输出一致。
    """
    if full_json is None:
        if adb is None:
            raise ValueError("collect_observation 需要 adb 或 full_json")
        full_json = collect_full_json(
            adb=adb, serial=serial, save_raw=save_raw, quiet=quiet,
            use_dumpsys=use_dumpsys,
        )
    parse_anomalies = full_json.get("_parse_anomalies") if isinstance(full_json, dict) else None
    return summarize_full_json(full_json, max_nodes=max_nodes, parse_anomalies=parse_anomalies)


def collect_visible(*, adb=None, serial: Optional[str] = None,
                    full_json: Optional[dict] = None,
                    save_raw: Optional[str] = None, quiet: bool = False) -> dict:
    """从实时采集或已保存的全量 JSON 得到可见树投影。"""
    if full_json is None:
        if adb is None:
            raise ValueError("collect_visible 需要 adb 或 full_json")
        full_json = collect_full_json(
            adb=adb, serial=serial, save_raw=save_raw, quiet=quiet,
            use_dumpsys=False,
        )
    return select_visible(full_json)
