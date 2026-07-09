#!/usr/bin/env python3
"""Render a Chinese overnight strategy dashboard from overnight_strategy.json."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def risk_label(value: Any) -> str:
    return {
        "low": "低风险",
        "medium": "中等风险",
        "high": "高风险",
        "critical": "不可交易",
    }.get(str(value), str(value or "未评估"))


def short_risk_label(value: Any) -> str:
    return {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "禁",
    }.get(str(value), "—")


def risk_class(value: Any) -> str:
    return {
        "low": "risk-low",
        "medium": "risk-medium",
        "high": "risk-high",
        "critical": "risk-critical",
    }.get(str(value), "risk-medium")


def regime_label(value: Any) -> str:
    return {
        "narrow_tech_rally": "科技主线集中上涨",
        "broad_rally": "市场普遍上涨",
        "strong_sector": "强势主线行情",
        "balanced": "均衡震荡",
        "neutral": "中性震荡",
        "weak": "弱势行情",
        "risk_off": "风险收缩",
        "panic": "恐慌行情",
    }.get(str(value or ""), str(value or "市场状态未确认"))


def direction_class(value: Any) -> str:
    return {
        "持有偏多": "up",
        "持有": "up",
        "谨慎持有": "warn",
        "观望": "muted",
    }.get(str(value), "muted")


def stock_rows(items: list[dict[str, Any]], actionable: bool) -> str:
    rows = []
    for item in items:
        action = (
            f'<div class="reason">{esc(item.get("key_reason"))}</div>'
            if actionable
            else f'<div class="plan">{esc(item.get("key_reason"))}</div>'
        )
        rows.append(
            f"""
            <tr>
              <td class="code">{esc(item.get("code"))}</td>
              <td class="strong">{esc(item.get("name"))}</td>
              <td>{esc(item.get("sector"))}</td>
              <td><span class="score-badge">{esc(item.get("overnight_score"))}</span></td>
              <td><span class="risk risk-short {risk_class(item.get("risk_severity"))}">{short_risk_label(item.get("risk_severity"))}</span></td>
              <td><span class="pill {direction_class(item.get("direction"))}">{esc(item.get("direction"))}</span></td>
              <td>{esc(item.get("trading_strategy"))}</td>
              <td>{action}</td>
            </tr>
            """
        )
    if not rows:
        return '<tr><td colspan="8" class="empty">暂无标的</td></tr>'
    return "".join(rows)


def watch_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        rows.append(
            f"""
            <tr>
              <td class="code">{esc(item.get("code"))}</td>
              <td class="strong">{esc(item.get("name"))}</td>
              <td>{esc(item.get("overnight_score"))}</td>
              <td><span class="pill muted">观望</span></td>
              <td>{esc(item.get("key_reason"))}</td>
              <td><span class="risk {risk_class(item.get("risk_severity"))}">{risk_label(item.get("risk_severity"))}</span></td>
              <td>{esc("、".join(item.get("rules_applied") or []))}</td>
            </tr>
            """
        )
    return "".join(rows) or '<tr><td colspan="7" class="empty">暂无观察标的</td></tr>'


def exit_plan_details(items: list[dict[str, Any]]) -> str:
    blocks = []
    labels = (
        ("auction_condition", "竞价条件"),
        ("open_strategy", "开盘策略"),
        ("stop_loss", "止损线"),
        ("take_profit", "止盈计划"),
    )
    for item in items:
        plan = item.get("t_plus_1_plan") if isinstance(item.get("t_plus_1_plan"), dict) else {}
        refs = item.get("execution_references") if isinstance(item.get("execution_references"), dict) else {}
        details = "".join(
            f'<div class="plan-line"><b>{label}</b><span>{esc(plan.get(key))}</span></div>'
            for key, label in labels
        )
        blocks.append(
            f"""
            <details class="stock-detail" open>
              <summary><span class="code">{esc(item.get("code"))}</span> {esc(item.get("name"))}
                <span class="summary-meta">{esc(item.get("direction"))} · {esc(item.get("trading_strategy"))} · {esc(item.get("position_plan"))}</span></summary>
              <div class="detail-grid">
                <section class="reason-section"><h4>核心理由</h4><p>{esc(item.get("key_reason"))}</p>
                  <p class="accent-line">评分 {esc(item.get("overnight_score"))} · 预期溢价 {esc(item.get("expected_premium"))} · {risk_label(item.get("risk_severity"))}</p>
                </section>
                <section><h4>执行参考</h4><div class="reference-strip">
                <span><small>现价</small>{esc(refs.get("price"))}</span>
                <span><small>VWAP</small>{esc(refs.get("vwap"))}</span>
                <span><small>MA5</small>{esc(refs.get("ma5"))}</span>
                <span><small>MA10</small>{esc(refs.get("ma10"))}</span>
                <span><small>MA20</small>{esc(refs.get("ma20"))}</span>
                </div></section>
                <section class="plan-section"><h4>竞价与开盘</h4>{details[:details.find('<div class="plan-line"><b>止损线') if '<div class="plan-line"><b>止损线' in details else len(details)]}</section>
                <section class="plan-section"><h4>止盈止损</h4>{details[details.find('<div class="plan-line"><b>止损线'):] if '<div class="plan-line"><b>止损线' in details else ''}</section>
              </div>
            </details>
            """
        )
    return "".join(blocks) or '<div class="empty">暂无兑现计划</div>'


def render(doc: dict[str, Any]) -> str:
    date = esc(doc.get("date"))
    market = doc.get("market") if isinstance(doc.get("market"), dict) else {}
    portfolio = doc.get("portfolio") if isinstance(doc.get("portfolio"), dict) else {}
    positions = [x for x in doc.get("positions", []) if isinstance(x, dict)]
    watchlist = [x for x in doc.get("watchlist", []) if isinstance(x, dict)]
    controls = portfolio.get("risk_control") if isinstance(portfolio.get("risk_control"), list) else []
    control_html = "".join(f"<li>{esc(value)}</li>" for value in controls) or "<li>暂无额外风控说明</li>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>隔夜策略 · {date}</title>
  <style>
    :root {{ color-scheme:dark; --bg:#080d12; --panel:#111923; --line:#283648; --text:#e7edf5; --sub:#91a1b5;
      --red:#ff6b6b; --red2:#ff8a65; --green:#32d583; --yellow:#fdb022; --accent:#22d3ee; --blue:#60a5fa; }}
    * {{ box-sizing:border-box }} body {{ margin:0; background:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),
      linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(180deg,#0a1017,var(--bg) 52%,#070b10);
      background-size:32px 32px,32px 32px,auto; color:var(--text); font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif; }}
    .page {{ padding:22px 32px 40px; }}
    .page-header {{ padding:30px 32px 20px; border-bottom:1px solid var(--line); background:linear-gradient(135deg,rgba(13,22,32,.96),rgba(9,16,24,.92)); }}
    .page-header h1 {{ margin:0 0 8px; font-size:28px }} .page-header p {{ color:#b8c5d6 }}
    .hero {{ display:flex; justify-content:space-between; gap:28px; padding:28px; border:1px solid var(--line);
      border-radius:20px; background:linear-gradient(120deg,rgba(255,92,104,.13),rgba(16,29,46,.96) 38%); }}
    h1,h2,p {{ margin:0 }} h1 {{ font-size:30px }} h2 {{ font-size:20px; margin-bottom:14px }}
    .eyebrow {{ color:var(--red2); letter-spacing:.16em; font-weight:700 }} .sub {{ color:var(--sub) }}
    .hero-main {{ max-width:850px }} .hero-main p {{ margin-top:12px; font-size:15px }}
    .hero-side {{ min-width:250px; display:grid; grid-template-columns:1fr 1fr; gap:10px }}
    .metric {{ padding:14px; border:1px solid var(--line); border-radius:14px; background:rgba(6,14,25,.55) }}
    .metric b {{ display:block; font-size:22px; color:var(--red) }} .metric span {{ color:var(--sub) }}
    .section {{ margin-top:22px; padding:22px; border:1px solid var(--line); border-radius:18px; background:rgba(16,29,46,.92) }}
    .top-grid {{ display:grid; grid-template-columns:1.05fr 1.25fr .9fr; gap:12px; margin-bottom:26px }}
    .top-card,.panel,.stock-detail {{ background:rgba(17,25,35,.92); border:1px solid var(--line); border-radius:8px;
      box-shadow:0 0 0 1px rgba(34,211,238,.04),0 16px 42px rgba(0,0,0,.24) }}
    .top-card {{ min-height:178px; padding:16px; position:relative; overflow:hidden }} .top-card::after {{ content:""; position:absolute; left:0; right:0; top:0; height:2px; background:linear-gradient(90deg,var(--accent),transparent) }}
    .top-label {{ color:var(--sub); font-size:12px; margin-bottom:12px }} .state-main {{ font-size:24px; font-weight:800 }}
    .state-orb {{ width:44px; height:44px; flex:none; border-radius:50%; background:radial-gradient(circle,var(--yellow),rgba(253,176,34,.18) 64%,transparent 66%); box-shadow:0 0 30px rgba(253,176,34,.28) }}
    .state-row {{ display:flex; align-items:center; gap:13px; margin-bottom:12px }} .state-note {{ color:#b8c5d6; line-height:1.55 }}
    .portfolio-number {{ font-size:38px; line-height:1; font-weight:800 }} .portfolio-stats {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px }}
    .portfolio-stats div {{ padding:9px; border-radius:7px; background:#151f2b }} .portfolio-stats b {{ display:block; color:#fff }}
    .direction-list {{ display:grid; gap:9px }} .direction-list div {{ display:flex; justify-content:space-between; padding:7px 9px; background:#151f2b; border-radius:7px }}
    h2.section-title {{ margin:28px 0 12px; font-size:20px }} h2.section-title::before {{ content:""; display:inline-block; width:7px; height:18px; margin-right:10px; vertical-align:-3px; border-radius:2px; background:linear-gradient(var(--accent),var(--blue)) }}
    .panel {{ padding:14px; overflow:auto }}
    .strategy-table th:not(:last-child),.strategy-table td:not(:last-child) {{ white-space:nowrap }}
    .strategy-table th:nth-child(4),.strategy-table td:nth-child(4),
    .strategy-table th:nth-child(5),.strategy-table td:nth-child(5) {{ text-align:center }}
    .section-head {{ display:flex; align-items:end; justify-content:space-between; gap:20px; margin-bottom:12px }}
    table {{ width:100%; border-collapse:collapse }} th {{ text-align:left; color:var(--sub); font-weight:500;
      padding:10px; border-bottom:1px solid var(--line) }} td {{ padding:13px 10px; vertical-align:top; border-bottom:1px solid rgba(37,52,74,.7) }}
    td small {{ display:block; color:var(--sub); white-space:nowrap }} .plan {{ max-width:390px; margin-top:6px }} .plan b,.reason b {{ color:var(--sub); margin-right:7px }}
    .reason {{ max-width:520px; color:#eef4fb; line-height:1.7 }} .stock-title {{ display:flex; align-items:center; gap:8px; white-space:nowrap }}
    .score-badge {{ min-width:34px; height:22px; padding:0 7px; display:inline-flex; align-items:center; justify-content:center;
      border-radius:7px; color:var(--red2); background:rgba(255,92,104,.1); font-size:12px; font-weight:700 }}
    .strategy-label {{ display:inline-block; min-width:68px; font-weight:700 }} .position-cell {{ margin-bottom:7px; white-space:nowrap }}
    .pill,.risk {{ display:inline-flex; min-width:72px; height:28px; padding:0 10px; align-items:center; justify-content:center;
      border-radius:8px; white-space:nowrap; font-size:12px; font-weight:700 }}
    .risk-short {{ min-width:28px; width:28px; padding:0 }}
    .up {{ color:#fff; background:rgba(255,92,104,.75) }} .warn {{ color:#221a00; background:var(--yellow) }}
    .muted {{ color:#c4cfdb; background:#34445a }} .risk-low {{ color:var(--green); background:rgba(50,199,135,.12) }}
    .risk-medium {{ color:var(--yellow); background:rgba(247,201,72,.12) }} .risk-high,.risk-critical {{ color:var(--red); background:rgba(255,92,104,.12) }}
    .risk-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px }} .risk-box {{ padding:18px; border-radius:14px; background:#0b1727 }}
    .risk-box ul {{ margin:8px 0 0; padding-left:20px }} .watch-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px }}
    .watch-card {{ padding:15px; border:1px solid var(--line); border-radius:14px; background:#0b1727 }}
    .watch-card header,.watch-meta {{ display:flex; justify-content:space-between; gap:10px }} .watch-card small {{ display:block; color:var(--sub) }}
    .watch-meta {{ color:var(--red2); margin:10px 0 6px }} .watch-card p {{ color:#d9e3ef }} .watch-card footer {{ color:var(--sub); margin-top:8px }}
    .exit-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px }} .exit-card {{ padding:18px; border:1px solid var(--line); border-radius:15px; background:#0b1727 }}
    .exit-card header {{ display:flex; justify-content:space-between; gap:12px }} .exit-card small {{ display:block; color:var(--sub) }}
    .exit-position {{ margin:11px 0; padding:8px 10px; border-radius:9px; color:var(--red2); background:rgba(255,92,104,.08) }}
    .core-reason {{ display:grid; grid-template-columns:72px 1fr; gap:10px; margin-bottom:4px; padding:10px 0; color:#fff }}
    .core-reason b {{ color:var(--red2) }}
    .reference-strip {{ display:grid; grid-template-columns:repeat(5,1fr); gap:7px; margin:8px 0 12px }}
    .reference-strip span {{ padding:8px; border:1px solid rgba(37,52,74,.75); border-radius:9px; text-align:center; color:#eaf1f8; background:#0e1b2c }}
    .reference-strip small {{ display:block; color:var(--sub); font-size:11px }}
    .stock-detail {{ margin:10px 0 }} .stock-detail summary {{ cursor:pointer; padding:12px 14px; font-weight:700; color:#f3f7fd }}
    .summary-meta {{ float:right; color:var(--sub); font-size:12px; font-weight:500 }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(2,minmax(280px,1fr)); gap:12px; padding:0 14px 14px }}
    .detail-grid section {{ border-top:1px solid var(--line); padding-top:10px }} .detail-grid h4 {{ margin:0 0 8px; color:#c9f7ff }}
    .detail-grid p {{ margin:7px 0; color:#cbd7e6 }} .accent-line {{ color:var(--red2)!important }}
    .plan-section .plan-line {{ grid-template-columns:72px 1fr }} .code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:#d8f3ff }}
    .plan-line {{ display:grid; grid-template-columns:72px 1fr; gap:10px; padding:8px 0; border-top:1px solid rgba(37,52,74,.65) }}
    .plan-line b {{ color:#c7d5e5 }} .plan-line span {{ color:#e5edf6 }}
    .trace {{ margin-top:12px; padding:14px; border-left:3px solid var(--red); color:#c8d5e4; background:#0b1727 }}
    .footer {{ color:var(--sub); text-align:center; margin:24px 0 6px }} .empty {{ color:var(--sub); text-align:center; padding:25px }}
    @media(max-width:1100px) {{ .top-grid {{ grid-template-columns:1fr }} }}
    @media(max-width:980px) {{ .hero,.risk-grid {{ display:block }} .hero-side {{ margin-top:18px }} .watch-grid {{ grid-template-columns:1fr 1fr }}
      .table-wrap {{ overflow:auto }} table {{ min-width:880px }} }}
    @media(max-width:700px) {{ .page,.page-header {{ padding-left:16px; padding-right:16px }} .detail-grid {{ grid-template-columns:1fr }} .summary-meta {{ float:none; display:block }} }}
    @media print {{ body {{ background:#fff; color:#111 }} .page {{ max-width:none }} .hero,.section,.watch-card,.risk-box {{ background:#fff; border-color:#ccc }}
      .sub,td small,.exit,.footer,.watch-card footer {{ color:#555 }} }}
  </style>
</head>
<body>
<header class="page-header">
  <h1>尾盘隔夜策略报告 · {date}</h1>
  <p>数据源：overnight_strategy.json</p>
</header>
<main class="page">
  <section class="top-grid">
    <section class="top-card">
      <div class="top-label">市场状态</div>
      <div class="state-row"><div class="state-orb"></div><div><div class="state-main">{esc(regime_label(market.get("regime_hint")))}</div>
      <div class="sub">{risk_label(market.get("risk_severity"))}</div></div></div>
      <p class="state-note">{esc(market.get("tomorrow_expectation"))}</p>
    </section>
    <section class="top-card">
      <div class="top-label">组合计划</div>
      <div class="portfolio-number">{len(positions)} <small>只执行</small></div>
      <div class="portfolio-stats"><div><b>{esc(portfolio.get("position_cap"))}</b><span class="sub">仓位约束</span></div>
      <div><b>{esc(portfolio.get("execution_window"))}</b><span class="sub">执行窗口</span></div></div>
      <p class="state-note" style="margin-top:10px">{esc(market.get("reasoning_trace"))}</p>
    </section>
    <section class="top-card">
      <div class="top-label">策略分布</div>
      <div class="direction-list">
        <div><span>持有</span><b>{sum(1 for x in positions if x.get("direction") == "持有")}</b></div>
        <div><span>谨慎持有</span><b>{sum(1 for x in positions if x.get("direction") == "谨慎持有")}</b></div>
        <div><span>观察池</span><b>{len(watchlist)}</b></div>
        <div><span>整体风险</span><b>{risk_label(market.get("risk_severity"))}</b></div>
      </div>
    </section>
  </section>

  <h2 class="section-title">策略总表</h2>
  <section class="panel">
    <div class="table-wrap"><table class="strategy-table">
      <colgroup>
        <col style="width:7%"><col style="width:7%"><col style="width:12%"><col style="width:5%">
        <col style="width:5%"><col style="width:9%"><col style="width:10%"><col style="width:45%">
      </colgroup>
      <thead><tr><th>代码</th><th>名称</th><th>板块</th><th>评分</th><th>风险</th><th>方向</th><th>交易策略</th><th>核心理由</th></tr></thead>
      <tbody>{stock_rows(positions, True)}</tbody>
    </table></div>
  </section>

  <h2 class="section-title">单股执行详情</h2>
  {exit_plan_details(positions)}

  <h2 class="section-title">组合风控</h2>
  <section class="section risk-grid">
    <div class="risk-box"><h2>组合风控</h2><ul>{control_html}</ul></div>
    <div class="risk-box"><h2>执行原则</h2><ul>
      <li>先检查不可交易条件，再执行仓位计划。</li>
      <li>竞价或开盘条件不满足时，以放弃交易为优先。</li>
      <li>页面仅为 JSON 合同的中文阅读视图，不替代实时行情确认。</li>
    </ul></div>
  </section>

  <h2 class="section-title">观察池</h2>
  <section class="panel">
    <div class="table-wrap"><table>
      <thead><tr><th>代码</th><th>名称</th><th>评分</th><th>方向</th><th>核心理由</th><th>风险</th><th>规则</th></tr></thead>
      <tbody>{watch_rows(watchlist)}</tbody>
    </table></div>
  </section>

  <div class="footer">数据源：overnight_strategy.json · Schema {esc(doc.get("schema_version"))} · 生成时间 {esc(doc.get("generated_at"))}</div>
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path("intraday") / args.date
    input_path = Path(args.input) if args.input else root / "overnight_strategy.json"
    output_path = Path(args.output) if args.output else root / "overnight_strategy.html"
    doc = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if not isinstance(doc, dict) or doc.get("schema_version") != "intraday_overnight_strategy.v1":
        print("[ERROR] input must be intraday_overnight_strategy.v1", file=sys.stderr)
        return 1
    if doc.get("date") != args.date:
        print(f"[ERROR] input date must be {args.date}", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render(doc), encoding="utf-8")
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
