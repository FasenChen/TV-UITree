"""Render benchmark summaries as Markdown, offline HTML and SVG charts."""

from __future__ import annotations

import base64
import html
import math
from pathlib import Path

LABELS = {
    "get_full_tree": "完整树 · 双源", "get_full_tree_a11y": "完整树 · 仅无障碍",
    "get_screen_summary": "屏幕摘要 · 双源", "get_screen_summary_a11y": "屏幕摘要 · 仅无障碍",
    "get_visible_controls": "可见控件", "get_current_focus": "当前焦点",
    "get_focus_screenshot": "焦点截图", "direct_screenshot": "直接截图",
}
STAGES = {"connect": "连接检查", "capture_tree": "树采集", "summarize": "摘要 / 焦点",
          "screenshot": "PNG 截图", "mark": "焦点标注", "encode": "Base64 编码", "save": "文件保存"}
INK = "#203348"


def _text(x: float, y: float, text: str, size: int = 20, color: str = INK,
          anchor: str = "start") -> str:
    """转义图中的文字；标签不依赖外部字体文件。"""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}">{html.escape(text)}</text>')


def _svg(width: int, height: int, parts: list[str]) -> str:
    """使用原生矢量图，Markdown 和离线 HTML 共用同一图表。"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/>'
            '<g font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif">'
            + "".join(parts) + '</g></svg>')


def _heatmap(title: str, subtitle: str, columns: list[str], rows: list[str],
             values: list[list[float | None]], totals: list[float] | None = None) -> str:
    """数字给出精确读数，颜色只辅助比较；阶段图另标占比。"""
    cell = 160 if totals is not None else 200
    width, height = max(1100, 300 + cell * len(columns)), 210 + 86 * len(rows)
    parts = [_text(24, 48, title, 30), _text(24, 84, subtitle, 17, "#536779")]
    scale = 100 if totals is not None else max((v for row in values for v in row if v is not None), default=1)
    scale = max(scale, 1)
    for j, column in enumerate(columns):
        parts.append(_text(292 + j * cell + cell / 2, 137, column, 18, anchor="middle"))
    for i, (label, row) in enumerate(zip(rows, values)):
        top = 156 + i * 86
        for line, text in enumerate(label.splitlines()):
            parts.append(_text(274, top + (30 + line * 28 if totals is not None else 42), text,
                               20 if line == 0 else 16, anchor="end"))
        for j, value in enumerate(row):
            x = 292 + j * cell
            share = value / totals[i] * 100 if totals is not None and totals[i] and value is not None else 0
            ratio = max(0, min(1, (share if totals is not None else value or 0) / scale))
            rgb = [round(a + (b - a) * ratio) for a, b in zip((237, 245, 252), (14, 76, 140))]
            fill = '#%02x%02x%02x' % tuple(rgb)
            parts.append(f'<rect x="{x}" y="{top}" width="{cell-4}" height="82" fill="{fill}"/>')
            color = "white" if ratio > .70 else INK
            number = "—" if value is None else f"{value:.1f}" if totals is not None else f"{value:.2f}"
            parts.append(_text(x + cell / 2, top + 43, number, 26, color, "middle"))
            if totals is not None and value is not None:
                parts.append(_text(x + cell / 2, top + 69, f"{share:.1f}%", 17, color, "middle"))
    parts.append(_text(24, height - 16, "— 表示无成功样本或没有此阶段；颜色越深，耗时或占比越高。", 16, "#536779"))
    return _svg(width, height, parts)


def _rounds(samples: list[dict]) -> str:
    """双源读取逐轮展示；失败轮次留空，不连接跨缺口的样本。"""
    series = [(case, color) for case, color in [("get_full_tree", "#1765a8"), ("get_screen_summary", "#b44e33")]
              if any(s["case"] == case for s in samples)]
    good = [s for s in samples if s["ok"] and s["case"] in dict(series)]
    end = max((s["round"] for s in samples), default=1)
    ceiling = max(1, math.ceil(max((s["client_ms"] / 1000 for s in good), default=1)))
    parts = [_text(24, 44, "双源读取的逐轮变化", 30), _text(24, 80, "正式样本；纵轴为秒，横轴为轮次。空缺表示未成功取得样本。", 17, "#536779")]
    for step in range(5):
        y, value = 400 - step * 65, ceiling * step / 4
        parts.extend([f'<path d="M 90 {y} H 1060" stroke="#dbe4eb"/>', _text(78, y + 6, f"{value:.1f}", 16, anchor="end")])
    for round_number in sorted({1, end, max(1, math.ceil(end / 2))}):
        x = 90 + (round_number - 1) / max(1, end - 1) * 970
        parts.append(_text(x, 432, str(round_number), 17, anchor="middle"))
    for index, (case, color) in enumerate(series):
        points = sorted((s for s in good if s["case"] == case), key=lambda s: s["round"])
        commands, previous = [], None
        for sample in points:
            x = 90 + (sample["round"] - 1) / max(1, end - 1) * 970
            y = 400 - sample["client_ms"] / 1000 / ceiling * 260
            commands.append(f'{"L" if previous == sample["round"] - 1 else "M"} {x:.2f} {y:.2f}')
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>')
            previous = sample["round"]
        dash = ' stroke-dasharray="8 5"' if index else ''
        parts.extend([f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="2"{dash}/>',
                      _text(90 + index * 350, 487, LABELS[case], 20, color)])
    return _svg(1100, 520, parts)


def _table(headers: list[str], rows: list[list[str]]) -> tuple[str, str]:
    """同一组数值分别输出为 Markdown 与 HTML 表格。"""
    markdown = '\n'.join('| ' + ' | '.join(html.escape(v).replace('|', '\\|').replace('\n', ' ') for v in row) + ' |'
                         for row in [headers, ['---'] * len(headers), *rows])
    heading = ''.join(f'<th scope="col">{html.escape(v)}</th>' for v in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(v)}</td>' for v in row) + '</tr>' for row in rows)
    return markdown, f'<div class="table-scroll"><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>'


def write_visual_report(report: dict, output: Path) -> None:
    """从既有汇总生成图文报告，不写回原始报告或设备配置。"""
    summary, samples = report["summary"], report["samples"]
    formal = [s for s in samples if not s["warmup"]]
    cases = list(summary)
    labels = [LABELS.get(case, case) for case in cases]
    metrics = ["mean", "p50", "p90", "p99"]
    values = [[summary[case]["client_ms"][m] / 1000 if summary[case]["client_ms"] else None for m in metrics] for case in cases]
    stages = [stage for stage in STAGES if any(stage in item["stages_ms"] for item in summary.values())]
    stages += sorted({stage for item in summary.values() for stage in item["stages_ms"]} - set(STAGES))
    totals, stage_values, stage_labels = [], [], []
    for case, label in zip(cases, labels):
        item = summary[case]
        total = item["client_ms"]["mean"] if item["client_ms"] else 0
        row = [item["stages_ms"][s]["mean"] if s in item["stages_ms"] else None for s in stages]
        row.append(total - sum(v for v in row if v is not None) if item["client_ms"] else None)
        totals.append(total)
        stage_values.append(row)
        stage_labels.append(f"{label}\n合计 {total:.1f} ms" if item["client_ms"] else label)
    charts = [
        ("client-latency.svg", "客户端耗时", _heatmap("客户端等待时间", "单位：秒；平均值 / p50 / p90 / p99。数字保留两位小数。", ["平均值", "p50 中位数", "p90", "p99"], labels, values)),
        ("stage-means.svg", "耗时主要花在哪个阶段", _heatmap("各阶段平均耗时及占比", "大字：毫秒（ms）；小字：占本项客户端平均总耗时的比例。", [STAGES.get(s, s) for s in stages] + ["响应 / 其他"], stage_labels, stage_values, totals)),
        ("dual-source-rounds.svg", "双源读取的逐轮变化", _rounds(formal)),
    ]
    succeeded = sum(s["ok"] for s in formal)
    expected = report["count"] * len(cases)
    rate = f"{succeeded / len(formal):.1%}" if formal else "无正式样本"
    mode = "USB ADB" if any("serial" in c.get("arguments", {}) for c in report.get("cases", [])) else "网络 ADB"
    scene = {True: "前后场景指纹一致", False: "前后场景指纹变化"}.get(report.get("scene_unchanged"), "前后场景未完成核对")
    config = {True: "配置字节不变", False: "配置字节变化"}.get(report.get("config_unchanged"), "配置未核对")
    title = "MCP 脚本性能压测报告"
    facts = f"开始时间：{report['started_at']}；连接方式：{mode}。每项计划正式 {report['count']} 次、预热 {report['warmup']} 次。"
    facts += f"相邻调用等待 {report.get('interval_seconds', 0):g} 秒；等待不计入工具耗时。"
    result = f"状态：{report['status']}。完成 {len(formal)}/{expected} 次正式调用，成功 {succeeded} 次、失败 {len(formal)-succeeded} 次，已完成正式调用成功率 {rate}；{scene}，{config}。"
    limits = ["测试按单设备串行执行，结果适用于本次设备、固件、界面与本机环境，不代表并发容量。",
              "p50 是中位数；p90 表示 90% 成功样本不超过该耗时；p99 同理。均使用最近秩法；成功样本不足 100 个时，p99 等于本次最大值，不能估计长期尾部延迟。",
              "预热与失败不进入耗时统计。逐轮图只展示成功正式样本，缺失或失败不补值。不同工具分次采集，期间画面仍可能变化。",
              "客户端耗时从发起调用计至完整响应返回；直接截图含连接检查。响应 / 其他为客户端均值减已计时阶段均值，包含未分段计时与响应处理，不能当作纯网络或 MCP 协议耗时；极小负值可能来自日志舍入。"]
    if report.get("scene_unchanged") is not True:
        limits.insert(0, "比较条件未确认一致，以下数据仅供现场诊断，不能作为严格同场景性能结论。")
    if len(formal) < expected:
        limits.insert(0, "正式调用未全部完成；成功率的分母只包含已完成调用，不能解释为计划任务全部成功。")
    if report.get("config_unchanged") is not True:
        limits.insert(0, "配置字节未确认保持不变，需核对原始报告，不能视为连接设置固定的对照。")
    environment = report.get("environment", {})
    software = f"Python {str(environment.get('python', '未知')).split()[0]}；MCP {environment.get('mcp', '未知')}；uiautomator2 {environment.get('uiautomator2', '未知')}。"
    startup = f"{report['startup_ms']:.1f} ms" if report.get("startup_ms") is not None else "未完成"
    conditions = f"MCP 服务启动 / 初始化：{startup}，不计入单次调用。"
    before, after = report.get("scene_before"), report.get("scene_after")
    if before and after:
        fields = [("window", "窗口"), ("focus", "焦点"), ("pixels_sha256", "截图像素")]
        conditions += "前后读数核对：" + '、'.join(f"{label}{'一致' if before.get(key) == after.get(key) else '变化'}" for key, label in fields) + "。"
    medians = [f"{label} p50 {summary[case]['client_ms']['p50']/1000:.2f} 秒" for case, label in zip(cases, labels) if summary[case]["client_ms"]]
    conclusions = '；'.join(medians) + '。' if medians else "本次没有成功样本，无法计算耗时。"
    markdown = [f"# {title}", "## 测试概况", html.escape(facts), html.escape(result), html.escape(software), conditions, "## 结果概览", html.escape(conclusions),
                "## 结果边界", '\n'.join(f"- {note}" for note in limits)]
    body = [f'<header><p class="eyebrow">TV-UITree / PERFORMANCE</p><h1>{title}</h1><p>{html.escape(facts)}</p></header>',
            f'<section class="status"><strong>{html.escape(result)}</strong><p>{html.escape(software)}</p><p>{html.escape(conditions)}</p></section>',
            f'<section><h2>结果概览</h2><p>{html.escape(conclusions)}</p></section>',
            '<section class="notice"><h2>结果边界</h2><ul>' + ''.join(f'<li>{html.escape(note)}</li>' for note in limits) + '</ul></section>']
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name, heading, svg in charts:
        (assets / name).write_text(svg, encoding="utf-8")
        markdown += [f"## {heading}", f"[![{heading}](assets/{name})](assets/{name})"]
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        min_width = 1100 if name == "stage-means.svg" else 700
        hint = '<p class="muted">阶段图较宽，可横向滚动查看全部阶段；精确数值见下方展开表格。</p>' if name == "stage-means.svg" else ''
        body.append(f'<section><h2>{heading}</h2>{hint}<div class="chart-scroll"><img style="min-width:{min_width}px" alt="{heading}" src="data:image/svg+xml;base64,{encoded}"></div></section>')
    client_rows = [[LABELS.get(case, case), f"{item['success']}/{item['success']+item['failed']}",
                    *[f"{item['client_ms'][metric]:.1f}" if item['client_ms'] else "—" for metric in ["min", "mean", "p50", "p90", "p99", "max"]]]
                   for case, item in summary.items()]
    stage_rows = [[LABELS.get(case, case), STAGES.get(stage, stage), *[f"{stats[m]:.1f}" for m in metrics]]
                  for case, item in summary.items() for stage, stats in item["stages_ms"].items()]
    comparison_rows = [[LABELS.get(case, case), str(item["comparison"]["pairs"]), f"{item['comparison']['mean_delta_ms']:.1f}", f"{item['comparison']['ratio_of_means']:.2f}x"]
                       for case, item in summary.items() if case != "direct_screenshot" and item["comparison"]]
    for heading, columns, rows in [
        ("客户端精确数值（毫秒）", ["待测项", "成功 / 已完成", "min", "mean", "p50", "p90", "p99", "max"], client_rows),
        ("阶段精确数值（毫秒）", ["待测项", "阶段", "mean", "p50", "p90", "p99"], stage_rows),
        ("同轮直接截图比较（仅配对成功样本）", ["待测项", "配对数", "平均差（ms）", "均值比"], comparison_rows),
    ]:
        md_table, html_table = _table(columns, rows)
        markdown += [f'<details>\n<summary>{heading}</summary>\n\n{md_table}\n\n</details>']
        body.append(f'<details><summary>{heading}</summary>{html_table}</details>')
    note = "平均差 = 本项客户端耗时 − 同轮直接截图耗时；均值比 = 配对样本两组均值之比。各工具工作量不同，差值不能全部归因于 MCP 协议。"
    markdown += [note, "## 原始数据", "原始文件保留在当前目录：`report.json`、`report.txt`、`samples.jsonl`、`stderr.log`。可能包含设备标识和本机路径；图文报告未展示这些标识。分享原始文件前请检查内容。"]
    body += [f'<p class="muted">{note}</p>', '<footer>由本目录 report.json 生成。HTML 已内嵌图表，可离线单独打开。原始 JSON / TXT / JSONL / 日志可能包含设备标识和本机路径，分享前请检查内容。</footer>']
    document = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MCP 性能压测报告</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf2f6;color:#203348;font:16px/1.75 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1200px;margin:auto;background:white;padding:40px 48px 64px;border-top:5px solid #1765a8}header{padding-bottom:24px;border-bottom:1px solid #dbe4eb}h1{font-size:clamp(30px,4vw,46px);line-height:1.3;margin:10px 0}h2{font-size:25px;margin:0 0 14px}.eyebrow{font-size:13px;letter-spacing:.15em;color:#1765a8}section{margin:32px 0}.status,.notice{padding:20px 24px;background:#f1f6fb;border-left:4px solid #1765a8}.notice{background:#fff9ed;border-color:#a66b15}li{margin-bottom:8px}ul{padding-left:24px}.chart-scroll,.table-scroll{overflow:auto}img{display:block;width:100%;min-width:700px;height:auto}details{border-top:1px solid #dbe4eb;padding:14px 0}summary{cursor:pointer;font-weight:600;padding:8px 0}summary:focus-visible{outline:2px solid #1765a8;outline-offset:4px}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:9px 12px;border-bottom:1px solid #dbe4eb;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{background:#f1f6fb}footer,.muted{color:#536779;font-size:14px}footer{border-top:1px solid #dbe4eb;margin-top:36px;padding-top:20px}@media(max-width:700px){main{padding:24px 18px}.notice,.status{padding:16px}h2{font-size:22px}}@media print{body{background:white}main{padding:0;max-width:none}section{break-inside:avoid}img{min-width:0}details{break-inside:avoid}}
</style></head><body><main>''' + '\n'.join(body) + '</main></body></html>\n'
    (output / "README.md").write_text('\n\n'.join(markdown) + '\n', encoding="utf-8")
    (output / "report.html").write_text(document, encoding="utf-8")
