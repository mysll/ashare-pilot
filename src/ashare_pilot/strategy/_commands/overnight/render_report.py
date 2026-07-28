#!/usr/bin/env python3
"""Render the validated overnight strategy v2 as a compact HTML board."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import intraday_dir, read_json
from ashare_pilot.strategy._commands.overnight.validate import validate


def esc(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def _shadow(item: dict[str, Any]) -> str:
    shadow = item.get("theme_support_shadow")
    if not isinstance(shadow, dict) or shadow.get("available") is not True:
        reason = shadow.get("missing_reason") if isinstance(shadow, dict) else None
        return f"主题影子不可用（{esc(reason)}）"
    return (
        f"{esc(shadow.get('primary_theme'))} · 核心热度 "
        f"{esc(shadow.get('core_heat'))} · 扩散热度 "
        f"{esc(shadow.get('diffusion_heat'))} · 排名 "
        f"{esc(shadow.get('theme_rank'))}"
    )


def _execution_rows(values: list[dict[str, Any]], actionable: bool) -> str:
    if not values:
        return '<tr><td colspan="8" class="empty">无</td></tr>'
    rows = []
    for item in values:
        plan = item.get("t_plus_1_plan")
        plan = plan if isinstance(plan, dict) else {}
        rows.append(
            "<tr>"
            f"<td class='mono'>{esc(item.get('code'))}</td>"
            f"<td>{esc(item.get('name'))}</td>"
            f"<td>{esc(item.get('direction'))}</td>"
            f"<td>{esc(item.get('overnight_score'))}</td>"
            f"<td>{esc(item.get('rank_tier'))}</td>"
            f"<td>{esc(item.get('key_reason'))}</td>"
            f"<td>{esc(plan.get('stop_loss'))}</td>"
            f"<td>{_shadow(item)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _observation_rows(values: list[dict[str, Any]]) -> str:
    if not values:
        return '<tr><td colspan="8" class="empty">观察池为空</td></tr>'
    return "".join(
        "<tr>"
        f"<td class='mono'>{esc(item.get('code'))}</td>"
        f"<td>{esc(item.get('name'))}</td>"
        f"<td>{esc(item.get('score_status'))}</td>"
        f"<td>{esc(item.get('overnight_score'))}</td>"
        f"<td>{esc(item.get('primary_observation_reason'))}</td>"
        f"<td>{esc(item.get('observation_summary'))}</td>"
        f"<td>{esc(item.get('watch_condition'))}</td>"
        f"<td>{_shadow(item)}</td>"
        "</tr>"
        for item in values
    )


def _quality_text(quality: Any) -> str:
    if not isinstance(quality, dict):
        return esc(quality)
    money = quality.get("money_flow")
    if not isinstance(money, dict):
        return esc(quality)
    if money.get("fetch_status") == "threshold_reached":
        label = "数据完整性 · 资金流数据按最低额度过滤"
        minimum = money.get("min_main_inflow_yuan")
        detail = (
            f"最低额度为 {float(minimum) / 10_000:.0f} 万元"
            if isinstance(minimum, (int, float))
            else "最低额度未知"
        )
        detail += "，达到阈值边界并主动停止"
    elif money.get("status") == "partial":
        label = "数据完整性 · 资金流数据部分完整"
        requested = money.get("requested_stock_count")
        matched = money.get("matched_stock_count")
        coverage = money.get("coverage_pct")
        detail = f"覆盖 {matched}/{requested} 只（{coverage}%）"
        if money.get("failed_page") is not None:
            detail += f"，第 {money['failed_page']} 页失败后未重新抓取"
    elif money.get("status") in {"unavailable", "failed"}:
        label = "数据完整性 · 资金流数据不可用"
        detail = "资金流维度不可用于评分"
    else:
        label = "数据完整性 · 资金流数据完整"
        detail = "可用"
    return f"{label}：{detail}；{esc(money)}"


def render(document: dict[str, Any], mapper: dict[str, Any] | None = None) -> str:
    recommendations = [
        item for item in document.get("recommendations", []) if isinstance(item, dict)
    ]
    eligible = [
        item
        for item in document.get("eligible_watchlist", [])
        if isinstance(item, dict)
    ]
    observations = [
        item for item in document.get("observations", []) if isinstance(item, dict)
    ]
    no_candidates = (
        '<div class="notice">无合适执行候选：这是正常业务结果，当前仓位为零。</div>'
        if not recommendations and not eligible
        else ""
    )
    quality = document.get("data_quality")
    recall = document.get("recall_quality")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>隔夜双池策略 · {esc(document.get('date'))}</title>
<style>
:root{{--bg:#081018;--panel:#101b27;--line:#27384b;--text:#e8eef6;--sub:#9aabba;--cyan:#35d0e5;--warn:#ffbd45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,"Noto Sans SC",sans-serif}}
main{{max-width:1680px;margin:auto;padding:28px}}h1{{margin:0}}h2{{margin:28px 0 10px;color:var(--cyan)}}p{{color:var(--sub)}}
.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card,.notice{{padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}
.card b{{display:block;font-size:28px}}.notice{{margin-top:16px;color:var(--warn)}}table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}}
th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:var(--sub)}}.mono{{font-family:ui-monospace,monospace}}.empty{{text-align:center;color:var(--sub)}}
.quality{{white-space:pre-wrap;word-break:break-word}}@media(max-width:800px){{main{{padding:14px}}.summary{{grid-template-columns:1fr}}.scroll{{overflow:auto}}}}
</style></head><body><main>
<h1>Intraday 双池隔夜策略</h1><p>{esc(document.get('date'))} · rank tier 仅表示相对排名，不是买入等级</p>
<section class="summary">
<div class="card">可行动推荐<b>{len(recommendations)}</b></div>
<div class="card">合格但观望<b>{len(eligible)}</b></div>
<div class="card">确定性观察<b>{len(observations)}</b></div>
</section>{no_candidates}
<h2>可行动推荐</h2><div class="scroll"><table><thead><tr><th>代码</th><th>名称</th><th>方向</th><th>分数</th><th>Rank Tier</th><th>理由</th><th>止损</th><th>Theme Shadow</th></tr></thead>
<tbody>{_execution_rows(recommendations, True)}</tbody></table></div>
<h2>合格但观望</h2><div class="scroll"><table><thead><tr><th>代码</th><th>名称</th><th>方向</th><th>分数</th><th>Rank Tier</th><th>理由</th><th>止损</th><th>Theme Shadow</th></tr></thead>
<tbody>{_execution_rows(eligible, False)}</tbody></table></div>
<h2>确定性观察池</h2><div class="scroll"><table><thead><tr><th>代码</th><th>名称</th><th>评分状态</th><th>分数</th><th>主因</th><th>观察摘要</th><th>复核条件</th><th>Theme Shadow</th></tr></thead>
<tbody>{_observation_rows(observations)}</tbody></table></div>
<h2>数据质量与召回降级</h2><div class="card quality">{_quality_text(quality)}<br>召回质量：{esc(recall)}</div>
</main></body></html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--mapper")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = intraday_dir(args.date)
    input_path = (
        Path(args.input) if args.input else root / "overnight_strategy.json"
    )
    mapper_path = (
        Path(args.mapper) if args.mapper else root / "intraday_mapper.json"
    )
    output_path = (
        Path(args.output) if args.output else root / "overnight_strategy.html"
    )
    try:
        document = read_json(input_path)
        mapper = read_json(mapper_path) if mapper_path.exists() else None
    except (OSError, ValueError) as exc:
        print(f"[ERROR] report input unreadable: {exc}", file=sys.stderr)
        return 1
    errors = validate(document, args.date, mapper)
    if errors:
        print("[ERROR] strategy must validate before rendering", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    output = render(document, mapper)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    except OSError as exc:
        print(f"[ERROR] HTML render write failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
