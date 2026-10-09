"""Collect the current TV state through MCP and write a standalone HTML report."""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_TOOLS = {"set_default_network_device", "set_default_usb_device"}


def _json_value(value: Any) -> Any:
    """把 MCP 的模型值转换为可写入 JSON 的普通值。"""
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _image_base64(value: Any) -> str | None:
    """从工具结果中找出截图数据。"""
    if isinstance(value, dict):
        image = value.get("image_base64")
        if isinstance(image, str):
            return image
        for child in value.values():
            image = _image_base64(child)
            if image:
                return image
    elif isinstance(value, list):
        for child in value:
            image = _image_base64(child)
            if image:
                return image
    return None


def _without_image_data(value: Any) -> Any:
    """截图在页面中展示一次，避免再把 Base64 展开到原始数据区。"""
    if isinstance(value, dict):
        return {
            key: "[截图已嵌入报告]" if key == "image_base64" else _without_image_data(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_without_image_data(child) for child in value]
    return value


def _tool_payload(result: Any) -> tuple[Any, str | None]:
    """读取结构化内容或文本 JSON，并保留返回的 PNG。"""
    blocks = [_json_value(block) for block in result.content]
    texts = [block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
    images = [block.get("data") for block in blocks if isinstance(block, dict) and block.get("type") == "image"]
    payload = _json_value(result.structuredContent) if result.structuredContent is not None else None
    if payload is None:
        if len(texts) == 1:
            try:
                payload = json.loads(texts[0])
            except (TypeError, ValueError):
                payload = {"text": texts[0]}
        else:
            payload = {"content": texts}
    png = next((image for image in images if isinstance(image, str)), None)
    return payload, png or _image_base64(payload)


def _has_error(record: dict[str, Any]) -> bool:
    payload = record["payload"]
    return bool(
        record["is_error"]
        or (isinstance(payload, dict) and (payload.get("error") or payload.get("call_error")))
    )


def _parse_server_timings(text: str) -> dict[str, dict[str, Any]]:
    """解析 MCP 服务 stderr 中每个工具的计时块。"""
    lines = text.splitlines()
    timings = {}
    header_pattern = re.compile(
        r"^\[tv-uitree\] \d{2}:\d{2}:\d{2}\.\d{3} (\w+)  total (\d+(?:\.\d+)?) ms(?:  failed at (\w+))?$"
    )
    stage_pattern = re.compile(r"^  (\w+)\s+(\d+(?:\.\d+)?) ms\s+(\d+(?:\.\d+)?)%$")
    index = 0
    while index < len(lines):
        header = header_pattern.fullmatch(lines[index])
        if header is None:
            index += 1
            continue
        stages = []
        index += 1
        while index < len(lines) and lines[index].startswith("  "):
            stage = stage_pattern.fullmatch(lines[index])
            if stage is None:
                break
            stages.append({"name": stage[1], "ms": float(stage[2]), "share": float(stage[3])})
            index += 1
        timings[header[1]] = {
            "server_ms": float(header[2]),
            "failed_stage": header[3],
            "stages": stages,
        }
    return timings


async def _collect() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """通过本地 stdio MCP 服务调用除默认设备写入外的全部工具。"""
    server = StdioServerParameters(
        command=sys.executable,
        args=["main.py", "mcp"],
        cwd=ROOT,
        encoding="utf-8",
        encoding_error_handler="replace",
    )
    records = []
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as server_log:
        async with stdio_client(server, errlog=server_log) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                manifest = [
                    {"name": tool.name, "description": tool.description or ""}
                    for tool in tools.tools
                ]
                for tool in tools.tools:
                    if tool.name in EXCLUDED_TOOLS:
                        continue
                    print(f"正在采集：{tool.name}", flush=True)
                    started = dt.datetime.now().astimezone()
                    call_started = time.perf_counter()
                    call_ms = None
                    try:
                        result = await session.call_tool(
                            tool.name,
                            {},
                            read_timeout_seconds=dt.timedelta(minutes=3),
                        )
                        call_ms = (time.perf_counter() - call_started) * 1000
                        payload, png = _tool_payload(result)
                        record = {
                            "name": tool.name,
                            "description": tool.description or "",
                            "time": started.strftime("%H:%M:%S"),
                            "payload": payload,
                            "png_base64": png,
                            "is_error": bool(result.isError),
                            "call_ms": call_ms,
                        }
                    except Exception as exc:
                        if call_ms is None:
                            call_ms = (time.perf_counter() - call_started) * 1000
                        record = {
                            "name": tool.name,
                            "description": tool.description or "",
                            "time": started.strftime("%H:%M:%S"),
                            "payload": {"call_error": f"{type(exc).__name__}: {exc}"},
                            "png_base64": None,
                            "is_error": True,
                            "call_ms": call_ms,
                        }
                    records.append(record)
        server_log.flush()
        server_log.seek(0)
        timings = _parse_server_timings(server_log.read())
    for item in records:
        item["timing"] = timings.get(item["name"])
    return records, manifest


def _record(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((item["payload"] for item in records if item["name"] == name), {})


def _focus_text(records: list[dict[str, Any]]) -> str:
    focus = _record(records, "get_current_focus")
    node = focus.get("node") if isinstance(focus, dict) else None
    if isinstance(node, dict):
        labels = [node.get("label"), *(node.get("related_text") or [])]
        value = " / ".join(str(label) for label in labels if label)
        if value:
            return value
    if isinstance(focus, dict):
        return str(focus.get("reason") or focus.get("status") or "焦点未知")
    return "焦点未知"


def _visible_labels(records: list[dict[str, Any]]) -> list[str]:
    visible = _record(records, "get_visible_controls")
    page = visible.get("page") if isinstance(visible, dict) else None
    nodes = page.get("nodes", []) if isinstance(page, dict) else []
    labels = []
    for node in nodes:
        if isinstance(node, dict):
            labels.extend(label for label in node.get("labels", []) if isinstance(label, str) and label)
    return list(dict.fromkeys(labels))


def _summary_html(records: list[dict[str, Any]]) -> str:
    observation = _record(records, "get_screen_summary")
    screen = observation.get("screen") if isinstance(observation, dict) else {}
    window = observation.get("window") if isinstance(observation, dict) else {}
    page = observation.get("page") if isinstance(observation, dict) else {}
    screen = screen if isinstance(screen, dict) else {}
    window = window if isinstance(window, dict) else {}
    page = page if isinstance(page, dict) else {}
    visible = _record(records, "get_visible_controls")
    visible_page = visible.get("page") if isinstance(visible, dict) else None
    visible_nodes = visible_page.get("nodes", []) if isinstance(visible_page, dict) else []
    visible_count = len(visible_nodes)
    logical_size = "×".join(str(screen[key]) for key in ("width", "height") if screen.get(key)) or "未知"
    physical = screen.get("physical")
    physical_size = "×".join(map(str, physical)) if isinstance(physical, list) else "未知"
    component = window.get("component") or window.get("mCurrentFocus") or "未知"
    focus = _focus_text(records)
    labels = _visible_labels(records)
    label_html = "".join(f'<span class="item-label">{html.escape(label)}</span>' for label in labels)
    if not label_html:
        label_html = '<span class="item-empty">未返回可见文字标签</span>'
    image = next((item["png_base64"] for item in records if item["png_base64"]), None)
    if image:
        screen_html = (
            '<figure class="screen-view"><img alt="电视当前画面，焦点区域以红框标出" '
            f'src="data:image/png;base64,{image}"><figcaption>焦点框来自截图工具的无障碍坐标标注</figcaption></figure>'
        )
    else:
        screen_html = '<div class="screen-empty">本次没有取得截图，请查看截图工具返回的错误信息。</div>'
    return f'''<section class="overview" aria-label="当前电视画面">
  <div class="screen-column">{screen_html}</div>
  <aside class="readout">
    <p class="readout-label">当前焦点</p><h2>{html.escape(focus)}</h2>
    <div class="readout-rule"></div>
    <p class="readout-label">当前窗口</p><p class="component">{html.escape(str(component))}</p>
    <dl class="measurements">
      <div><dt>逻辑分辨率</dt><dd>{html.escape(logical_size)}</dd></div>
      <div><dt>物理分辨率</dt><dd>{html.escape(physical_size)}</dd></div>
      <div><dt>完整摘要节点</dt><dd>{html.escape(str(page.get("node_count", "未知")))}</dd></div>
      <div><dt>可见文字项</dt><dd>{visible_count}</dd></div>
    </dl>
  </aside>
</section>
<section class="visible-list" aria-label="当前可见文字"><h2>屏幕上读到的文字</h2><div class="labels">{label_html}</div></section>'''


def _tool_rows(records: list[dict[str, Any]]) -> str:
    rows = []
    for item in records:
        payload = _without_image_data(item["payload"])
        pretty = html.escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        fields = ", ".join(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        failed = _has_error(item)
        status = "需要查看" if failed else "已返回"
        status_class = "failed" if failed else "success"
        call_ms = item.get("call_ms")
        timing = item.get("timing")
        if isinstance(call_ms, (int, float)):
            call_time = f"{call_ms:.0f} ms" if call_ms < 1000 else f"{call_ms / 1000:.2f} s"
        else:
            call_time = "未知"
        if isinstance(timing, dict):
            server_ms = timing.get("server_ms")
            server_time = f"{server_ms:.0f} ms" if isinstance(server_ms, (int, float)) and server_ms < 1000 else (
                f"{server_ms / 1000:.2f} s" if isinstance(server_ms, (int, float)) else "未知"
            )
            stage_html = "".join(
                f'<div class="timing-stage"><span>{html.escape(stage["name"])}</span>'
                f'<b>{stage["ms"]:.1f} ms</b></div>'
                for stage in timing.get("stages", [])
            ) or '<div>未记录阶段</div>'
        else:
            server_time = "未返回"
            stage_html = '<div>服务端阶段计时不可用</div>'
        rows.append(f'''<article class="tool-row">
  <div class="tool-heading"><div><h3>{html.escape(item["name"])}</h3><p>{html.escape(item["description"])}</p></div>
  <div class="tool-status {status_class}"><div class="tool-result"><span aria-hidden="true"></span>{status}</div>
  <div class="timing-total">调用总耗时 <strong>{call_time}</strong></div>
  <div class="timing-server">服务端总计 {server_time}</div><div class="timing-stages">{stage_html}</div></div></div>
  <div class="tool-meta"><span>采集时间 {html.escape(item["time"])}</span><span>字段 {html.escape(fields or "无")}</span></div>
  <details><summary>展开原始返回</summary><pre>{pretty}</pre></details>
</article>''')
    return "\n".join(rows)


def _render_report(records: list[dict[str, Any]], manifest: list[dict[str, str]]) -> str:
    now = dt.datetime.now().astimezone()
    succeeded = sum(not _has_error(item) for item in records)
    skipped = [item["name"] for item in manifest if item["name"] in EXCLUDED_TOOLS]
    discovered = "、".join(html.escape(item["name"]) for item in manifest) or "无"
    skipped_text = "、".join(html.escape(name) for name in skipped) or "无"
    screenshot_note = "截图已嵌入本文档" if any(item["png_base64"] for item in records) else "本次未取得截图"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>电视现场记录</title><style>
:root{{--page:#e7ebe7;--paper:#fbfcf8;--ink:#182b31;--muted:#52666a;--line:#c7d1cc;--quiet:#eaf0ec;--green:#246b59;--signal:#c85e43;--code:#18292d;--code-text:#e8f0ec}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 "Segoe UI Variable","Aptos","Microsoft YaHei UI",sans-serif}}
.page{{max-width:1320px;min-height:100vh;margin:0 auto;padding:0 54px 64px;background:var(--paper);border-top:5px solid var(--signal)}}
.masthead{{display:flex;justify-content:space-between;align-items:center;padding:20px 0;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}}
.brand{{display:flex;align-items:center;gap:10px;font-weight:650;color:var(--ink)}}.brand-mark{{width:10px;height:10px;background:var(--signal);display:inline-block}}
.cover{{display:flex;justify-content:space-between;align-items:end;gap:24px;padding:48px 0 30px}}.cover h1{{font-size:clamp(34px,5vw,56px);line-height:1.04;letter-spacing:-.04em;margin:0;font-weight:650}}.cover p{{max-width:600px;color:var(--muted);margin:14px 0 0}}
.run-state{{min-width:190px;border-left:2px solid var(--green);padding:4px 0 4px 16px}}.run-state strong{{font-size:25px;display:block;line-height:1.1;font-weight:620}}.run-state span{{display:block;color:var(--muted);font-size:13px;margin-top:6px}}
.overview{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.75fr);gap:34px;align-items:stretch;padding:18px 0 28px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}}
.screen-view{{margin:0}}.screen-view img{{display:block;width:100%;height:auto;max-height:640px;object-fit:contain;object-position:center;background:#111;border:1px solid #b8c3bd}}.screen-view figcaption{{color:var(--muted);font-size:12px;margin-top:7px}}.screen-empty{{min-height:270px;display:grid;place-items:center;background:var(--quiet);color:var(--muted);padding:24px;text-align:center}}
.readout{{padding:12px 0 0}}.readout-label{{font-size:12px;color:var(--muted);margin:0 0 5px}}.readout h2{{font-size:clamp(23px,3vw,34px);line-height:1.16;letter-spacing:-.025em;margin:0 0 20px;overflow-wrap:anywhere}}.readout-rule{{height:1px;background:var(--line);margin:22px 0}}.component{{font-size:14px;overflow-wrap:anywhere;margin:0 0 22px;color:var(--ink)}}
.measurements{{margin:0;border-top:1px solid var(--line)}}.measurements div{{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}}.measurements dt{{font-size:13px;color:var(--muted)}}.measurements dd{{margin:0;font-variant-numeric:tabular-nums;font-weight:620;text-align:right}}
.visible-list{{padding:22px 0 30px;border-bottom:1px solid var(--line)}}.visible-list h2,.section-title{{font-size:20px;margin:0 0 13px;letter-spacing:-.015em}}.labels{{display:flex;flex-wrap:wrap;gap:7px}}.item-label{{display:inline-block;border:1px solid #b8c6c0;padding:5px 10px;font-size:13px;background:#f5f8f4;color:#29433e}}.item-empty{{color:var(--muted);font-size:14px}}
.tools-section{{padding-top:34px}}.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:20px;margin-bottom:8px}}.section-title{{margin:0}}.section-head p{{margin:0;color:var(--muted);font-size:13px}}.tool-row{{border-top:1px solid var(--line);padding:20px 0 22px}}.tool-heading{{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}}.tool-heading h3{{font:600 18px/1.25 "Cascadia Code","Consolas",monospace;margin:0 0 5px}}.tool-heading p{{font-size:14px;color:var(--muted);margin:0;max-width:850px}}
.tool-status{{white-space:normal;font-size:12px;display:flex;flex:0 0 250px;width:250px;flex-direction:column;align-items:stretch;gap:6px;border-left:1px solid var(--line);padding:1px 0 0 16px;text-align:left}}.tool-result{{display:flex;align-items:center;gap:7px;font-size:12px}}.tool-result>span{{width:8px;height:8px;flex:0 0 8px;display:inline-block;border-radius:50%;background:var(--green)}}.tool-status.failed{{color:#973e2b}}.tool-status.failed .tool-result>span{{background:var(--signal)}}
.timing-total{{display:flex;justify-content:space-between;align-items:baseline;gap:10px;font-size:13px;color:var(--ink);font-variant-numeric:tabular-nums}}.timing-total strong{{font-size:17px;font-weight:650}}.timing-server{{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}}.timing-stages{{display:grid;gap:3px;font-size:11px;line-height:1.4;color:var(--muted);font-variant-numeric:tabular-nums}}.timing-stage{{display:flex;justify-content:space-between;gap:12px}}.timing-stage b{{font-weight:500;white-space:nowrap}}.tool-status.failed .timing-total,.tool-status.failed .timing-server,.tool-status.failed .timing-stages{{color:inherit}}
.tool-meta{{display:flex;flex-wrap:wrap;gap:8px 22px;color:var(--muted);font-size:12px;margin:12px 0}}details{{border-left:2px solid #b7c4be;padding:2px 0 2px 12px}}summary{{cursor:pointer;color:var(--green);font-size:13px;font-weight:620;width:max-content;max-width:100%}}summary:focus-visible{{outline:3px solid #236e5d;outline-offset:4px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:560px;overflow:auto;background:var(--code);color:var(--code-text);padding:17px 19px;margin:12px 0 0;font:12px/1.55 "Cascadia Code","Consolas",monospace}}
.footnote{{border-top:1px solid var(--line);padding-top:18px;margin-top:24px;color:var(--muted);font-size:12px}}@media(max-width:760px){{.page{{padding:0 22px 42px}}.cover{{padding:34px 0 24px;align-items:flex-start;flex-direction:column}}.run-state{{border-left:0;border-top:1px solid var(--line);padding:10px 0 0;width:100%}}.run-state strong{{display:inline;margin-right:8px}}.run-state span{{display:inline}}.overview{{grid-template-columns:1fr;gap:24px}}.readout{{padding:0}}.section-head{{align-items:flex-start;flex-direction:column;gap:4px}}.tool-heading{{flex-direction:column;gap:10px}}.tool-status{{width:100%;flex:none;border-left:0;border-top:1px solid var(--line);padding:10px 0 0}}}}
@media(max-width:420px){{.page{{padding-inline:15px}}.masthead{{align-items:flex-start;gap:10px;flex-direction:column}}.measurements div{{gap:8px}}}}
</style></head><body><main class="page">
<header class="masthead"><div class="brand"><span class="brand-mark" aria-hidden="true"></span><span>TV UITree</span><span>/</span><span>现场采集</span></div><time>{html.escape(now.strftime("%Y-%m-%d %H:%M:%S %z"))}</time></header>
<section class="cover"><div><h1>电视现场记录</h1><p>当前画面、焦点与 MCP 工具回传。原始数据按工具归档，可逐项展开。</p></div><div class="run-state"><strong>{succeeded} / {len(records)}</strong><span>读取工具成功</span><span>发现 {len(manifest)} 项，跳过 {len(skipped)} 项配置写入</span></div></section>
{_summary_html(records)}
<section class="tools-section" aria-label="MCP 工具返回"><div class="section-head"><h2 class="section-title">工具回传</h2><p>已发现：{discovered}<br>按要求跳过：{skipped_text}</p></div>
{_tool_rows(records)}</section>
<footer class="footnote">设备参数沿用当前 config.json；此脚本不会修改设备配置或发送遥控按键。{html.escape(screenshot_note)}。树、观察与截图各自采集，页面切换时它们可能对应不同瞬间。</footer>
</main></body></html>'''


async def main() -> int:
    """采集 MCP 工具并保存独立 HTML 报告。"""
    try:
        records, manifest = await _collect()
    except Exception as exc:
        print(f"MCP 服务启动或工具发现失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if not records:
        print("没有可调用的读取工具。", file=sys.stderr)
        return 1
    if any(item["name"] in EXCLUDED_TOOLS for item in records):
        print("安全检查失败：设备配置写入工具不应被调用。", file=sys.stderr)
        return 1

    report = _render_report(records, manifest)
    expected_rows = sum(item["name"] not in EXCLUDED_TOOLS for item in manifest)
    if report.count('class="tool-row"') != expected_rows:
        print("报告校验失败：工具返回数与工具清单不一致。", file=sys.stderr)
        return 1

    output_dir = ROOT / "_temp"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    output_path = output_dir / f"tv-tool-report-{timestamp}.html"
    output_path.write_text(report, encoding="utf-8")
    print(f"HTML 报告：{output_path}")
    print(f"工具返回：{sum(not _has_error(item) for item in records)}/{len(records)} 成功")
    return 0 if all(not _has_error(item) for item in records) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
