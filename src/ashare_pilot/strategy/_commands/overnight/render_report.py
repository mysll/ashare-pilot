#!/usr/bin/env python3
"""Render the overnight strategy JSON as an A-share decision terminal."""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import intraday_dir


def esc(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def risk_label(value: Any) -> str:
    return {"low": "低", "medium": "中等", "high": "高", "critical": "不可交易"}.get(
        str(value), "未评估"
    )


def risk_class(value: Any) -> str:
    return {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "critical": "critical",
    }.get(str(value), "medium")


def regime_label(value: Any) -> str:
    raw = str(value or "").strip()
    label = {
        "narrow_tech_rally": "震荡上行 / 机会大于风险",
        "broad_rally": "普遍上涨 / 积极参与",
        "strong_sector": "主线强势 / 聚焦核心",
        "balanced": "均衡震荡 / 精选个股",
        "neutral": "中性震荡 / 控制节奏",
        "weak": "弱势行情 / 防守优先",
        "risk_off": "风险收缩 / 降低仓位",
        "panic": "恐慌行情 / 暂停执行",
    }.get(raw)
    if label:
        return label
    if not raw:
        return "市场状态未确认"
    for sep in (" — ", "—", "：", ":", "。"):
        if sep in raw:
            raw = raw.split(sep, 1)[0].strip()
            break
    return raw[:18] + ("…" if len(raw) > 18 else "")


def split_market_reason(value: Any, limit: int = 90) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    if len(raw) <= limit:
        return raw, raw
    head = raw[:limit].rstrip()
    return f"{head}…", raw


def direction_class(value: Any) -> str:
    return {"持有偏多": "long", "持有": "long", "谨慎持有": "cautious", "观望": "watch"}.get(
        str(value), "watch"
    )


def direction_label(value: Any) -> str:
    return {
        "持有偏多": "建议买入",
        "持有": "建议买入",
        "谨慎持有": "谨慎买入",
        "观望": "暂不买入",
    }.get(str(value), str(value or "—"))


def generated_time(value: Any) -> str:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def score_bar(value: Any) -> str:
    try:
        score = max(0.0, min(100.0, float(value)))
        label = f"{score:.1f}"
    except (TypeError, ValueError):
        score, label = 0.0, "—"
    return (
        f'<div class="score"><b>{label}</b><span><i style="width:{score:.1f}%"></i></span></div>'
    )


def plan_of(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("t_plus_1_plan")
    return value if isinstance(value, dict) else {}


def market_chips(mapper: dict[str, Any] | None) -> str:
    market = mapper.get("market") if isinstance(mapper, dict) and isinstance(mapper.get("market"), dict) else {}
    indices = market.get("indices") if isinstance(market.get("indices"), list) else []
    wanted = {"sh000001", "sz399001", "sz399006", "sh000688"}
    chips = []
    for item in indices:
        if not isinstance(item, dict) or item.get("code") not in wanted or not item.get("percent"):
            continue
        change = str(item["percent"])
        tone = "index-up" if change.startswith("+") else "index-down" if change.startswith("-") else "index-flat"
        chips.append(
            f'<span class="index-chip {tone}">{esc(item.get("name"))} <b>{esc(change)}</b></span>'
        )
    return "".join(chips)


def strategy_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        plan = plan_of(item)
        rows.append(
            f"""<tr>
              <td><span class="badge {direction_class(item.get('direction'))}">{esc(direction_label(item.get('direction')))}</span></td>
              <td class="mono">{esc(item.get('code'))}</td>
              <td class="stock-name">{esc(item.get('name'))}</td>
              <td>{esc(item.get('primary_theme'))}</td>
              <td>{esc(item.get('market_board'))}</td>
              <td>{score_bar(item.get('overnight_score'))}</td>
              <td><span class="badge risk-{risk_class(item.get('risk_severity'))}">{risk_label(item.get('risk_severity'))}</span></td>
              <td class="action" title="{esc(plan.get('open_strategy'))}">{esc(plan.get('open_strategy'))}</td>
              <td class="reason" title="{esc(item.get('key_reason'))}">{esc(item.get('key_reason'))}</td>
            </tr>"""
        )
    return "".join(rows) or '<tr><td colspan="9" class="empty">今日无可执行标的</td></tr>'


def execution_cards(items: list[dict[str, Any]]) -> str:
    cards = []
    for item in items:
        plan = plan_of(item)
        cards.append(
            f"""<article class="execution-card">
              <header>
                <div><h3>{esc(item.get('name'))}</h3><span class="mono">{esc(item.get('code'))}</span></div>
                <div class="card-score"><small>SCORE</small>{esc(item.get('overnight_score'))}</div>
              </header>
              <div class="card-tags">
                <span>{esc(item.get('primary_theme'))}</span>
                <span>{esc(item.get('market_board'))}</span>
                <span class="badge {direction_class(item.get('direction'))}">{esc(direction_label(item.get('direction')))}</span>
                <span class="badge risk-{risk_class(item.get('risk_severity'))}">{risk_label(item.get('risk_severity'))}风险</span>
              </div>
              <dl>
                <div><dt>开盘动作</dt><dd>{esc(plan.get('open_strategy'))}</dd></div>
                <div><dt>止损纪律</dt><dd>{esc(plan.get('stop_loss'))}</dd></div>
                <div><dt>止盈计划</dt><dd>{esc(plan.get('take_profit'))}</dd></div>
              </dl>
              <footer><b>核心理由</b><span>{esc(item.get('key_reason'))}</span></footer>
            </article>"""
        )
    return "".join(cards) or '<div class="empty">今日无执行指令卡</div>'


def watch_group(item: dict[str, Any]) -> tuple[str, str]:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("key_reason", "position_plan", "reasoning_trace", "primary_theme")
    )
    code = str(item.get("code") or "")
    if code.startswith("sh688") or "科创" in text or "不可交易" in text:
        return "科创板不可交易", "blocked"
    if "涨停" in text or "封板" in text:
        return "涨停封板", "limit"
    if "资金" in text and any(word in text for word in ("撕裂", "分歧", "流出", "一致性")):
        return "资金撕裂", "split"
    if any(word in text for word in ("非主线", "弱主线", "主题弱")):
        return "非核心主线", "off-theme"
    try:
        if float(item.get("overnight_score", 100)) < 60:
            return "分数不足", "low-score"
    except (TypeError, ValueError):
        pass
    return "等待买点", "wait"


def watch_groups(items: list[dict[str, Any]]) -> str:
    order = ["涨停封板", "科创板不可交易", "非核心主线", "资金撕裂", "分数不足", "等待买点"]
    grouped: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for item in items:
        label, kind = watch_group(item)
        grouped.setdefault(label, (kind, []))[1].append(item)
    blocks = []
    for label in order:
        if label not in grouped:
            continue
        kind, values = grouped[label]
        rows = "".join(
            f"""<tr><td class="mono">{esc(x.get('code'))}</td><td class="stock-name">{esc(x.get('name'))}</td>
            <td>{esc(x.get('primary_theme'))}</td><td>{esc(x.get('market_board'))}</td><td>{esc(x.get('overnight_score'))}</td>
            <td><span class="badge watch">暂不买入</span></td><td>{esc(x.get('key_reason'))}</td></tr>"""
            for x in values
        )
        blocks.append(
            f"""<details class="watch-group">
              <summary><span class="group-mark {kind}"></span><b>{label}</b><em>{len(values)}</em>
              <span class="representatives">{esc(' / '.join(str(x.get('name') or '') for x in values[:3]))}</span></summary>
              <div class="table-scroll"><table><thead><tr><th>代码</th><th>名称</th><th>投资主题</th><th>交易板</th><th>评分</th><th>状态</th><th>观察理由</th></tr></thead>
              <tbody>{rows}</tbody></table></div>
            </details>"""
        )
    return "".join(blocks) or '<div class="empty">观察池为空</div>'


def render(doc: dict[str, Any], mapper: dict[str, Any] | None = None) -> str:
    date = esc(doc.get("date"))
    market = doc.get("market") if isinstance(doc.get("market"), dict) else {}
    portfolio = doc.get("portfolio") if isinstance(doc.get("portfolio"), dict) else {}
    positions = [x for x in doc.get("positions", []) if isinstance(x, dict)]
    watchlist = [x for x in doc.get("watchlist", []) if isinstance(x, dict)]
    controls = portfolio.get("risk_control") if isinstance(portfolio.get("risk_control"), list) else []
    risk = risk_class(market.get("risk_severity"))
    risk_score = {"low": 1, "medium": 3, "high": 4, "critical": 5}.get(risk, 3)
    held = sum(1 for x in positions if x.get("direction") in {"持有", "持有偏多"})
    cautious = sum(1 for x in positions if x.get("direction") == "谨慎持有")
    primary_sectors = []
    for item in positions:
        sector = str(item.get("primary_theme") or "")
        if sector and sector not in primary_sectors:
            primary_sectors.append(sector)
    focus = " / ".join(primary_sectors[:3]) or "等待主线确认"
    controls_html = "".join(f"<li>{esc(value)}</li>" for value in controls)
    max_risk = controls[0] if controls else market.get("tomorrow_expectation")
    subtitle = market.get("tomorrow_expectation") or market.get("reasoning_trace")
    index_chips = market_chips(mapper)
    market_reason, market_reason_detail = split_market_reason(market.get("reasoning_trace"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>隔夜策略决策看板 · {date}</title>
  <style>
    :root{{--bg:#070B10;--bg-soft:#0B1118;--panel:#111923;--panel-2:#0E1724;--line:#243244;
      --text:#E7EDF5;--strong:#FFF;--sub:#91A1B5;--accent:#22D3EE;--blue:#60A5FA;
      --rise:#FF5C68;--rise-soft:rgba(255,92,104,.14);--fall:#32D583;--fall-soft:rgba(50,213,131,.14);
      --warn:#FDB022;--warn-soft:rgba(253,176,34,.15);--danger:#F04438;--danger-soft:rgba(240,68,56,.15);--muted:#34445A}}
    *{{box-sizing:border-box}} html{{background:var(--bg)}} body{{margin:0;color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
      background:radial-gradient(circle at 12% -8%,rgba(34,211,238,.09),transparent 28%),linear-gradient(180deg,#09111a,var(--bg) 28%)}}
    .mono,.metric strong,.card-score{{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}}
    .shell{{max-width:1680px;margin:auto;padding:0 28px 48px}} .topbar{{margin:0 -28px 24px;padding:25px 28px;border-bottom:1px solid var(--line);
      background:linear-gradient(110deg,rgba(7,11,16,.98),rgba(14,28,43,.95) 55%,rgba(7,11,16,.98))}}
    .topbar-inner{{max-width:1624px;margin:auto;display:flex;justify-content:space-between;gap:30px;align-items:flex-start}}
    h1,h2,h3,p{{margin:0}} h1{{font-size:30px;letter-spacing:.02em}} .subtitle{{max-width:900px;margin-top:7px;color:#a9b8ca}}
    .meta{{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:460px}} .meta span{{padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--sub);background:rgba(9,18,28,.8);font-size:12px}}
    .cockpit{{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:14px}} .card,.panel,.execution-card,.watch-group{{border:1px solid var(--line);border-radius:14px;
      background:linear-gradient(180deg,rgba(17,25,35,.97),rgba(10,17,26,.97));box-shadow:0 18px 44px rgba(0,0,0,.24)}}
    .cockpit-card{{min-height:235px;padding:19px;position:relative;overflow:hidden}} .cockpit-card:before{{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:2px;background:linear-gradient(90deg,var(--accent),transparent 70%)}}
    .card-label,.kicker{{color:var(--sub);font-size:12px;letter-spacing:.12em;text-transform:uppercase}} .market-call{{margin:20px 0 8px;font-size:25px;font-weight:800;color:var(--strong)}}
    .market-tag{{display:inline-flex;padding:4px 9px;border:1px solid rgba(253,176,34,.34);border-radius:6px;color:var(--warn);background:var(--warn-soft);font-weight:700}}
    .index-strip{{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}} .index-chip{{display:inline-flex;gap:5px;align-items:center;padding:4px 8px;border-radius:7px;font-size:12px;border:1px solid transparent}}
    .index-up{{color:var(--rise);background:var(--rise-soft);border-color:rgba(255,92,104,.25)}} .index-down{{color:var(--fall);background:var(--fall-soft);border-color:rgba(50,213,131,.25)}} .index-flat{{color:#c7d2e1;background:rgba(145,161,181,.12);border-color:rgba(145,161,181,.2)}}
    .market-copy{{margin-top:13px;color:#b9c6d5}} .market-detail{{margin-top:13px;color:#b9c6d5}} .market-detail summary{{cursor:pointer;list-style:none}} .market-detail summary::-webkit-details-marker{{display:none}} .market-detail .toggle-label{{display:block;margin-top:6px;color:var(--sub);font-size:12px}} .market-detail .open-label,.market-detail .market-full{{display:none}} .market-detail[open] .market-copy,.market-detail[open] .closed-label{{display:none}} .market-detail[open] .open-label{{display:block}} .market-detail[open] .market-full{{display:block;margin:8px 0 0}} .decision-layout{{margin-top:18px}}
    .big-number{{font:800 42px/1 ui-monospace,SFMono-Regular,monospace;color:var(--rise)}} .big-number small{{font:600 14px/1.2 inherit;color:var(--sub)}}
    .discipline{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:20px}}
    .discipline span{{padding:6px 8px;border-radius:6px;background:#151f2b;color:#c9d4e2;font-size:12px}}
    .risk-line{{display:flex;justify-content:space-between;align-items:end;margin:18px 0 12px}}
    .risk-value{{font-size:26px;font-weight:800;color:var(--warn)}} .risk-value small{{font-size:13px;color:var(--sub)}} .risk-meter{{display:grid;grid-template-columns:repeat(5,1fr);gap:5px}}
    .risk-meter i{{height:6px;border-radius:5px;background:#233143}} .risk-meter i.on{{background:var(--warn)}} .distribution{{display:grid;gap:8px;margin-top:19px}}
    .distribution div{{display:grid;grid-template-columns:78px 1fr 26px;gap:9px;align-items:center}} .distribution span{{color:var(--sub);font-size:12px}} .distribution i{{height:7px;border-radius:9px;background:#263548;overflow:hidden}}
    .distribution i:after{{content:"";display:block;width:var(--w);height:100%;background:var(--c)}} .distribution b{{text-align:right}}
    .section-head{{display:flex;justify-content:space-between;align-items:end;margin:30px 0 11px}} .section-head h2{{font-size:20px}} .section-head h2:before{{content:"";display:inline-block;width:4px;height:18px;margin-right:9px;vertical-align:-2px;border-radius:2px;background:var(--accent)}}
    .section-head p{{color:var(--sub);font-size:12px}} .panel{{overflow:hidden}} .table-scroll{{overflow:auto}} table{{width:100%;border-collapse:collapse}} th{{color:var(--sub);font-weight:600;background:rgba(10,17,26,.9);white-space:nowrap}}
    td,th{{padding:12px 10px;border-bottom:1px solid rgba(36,50,68,.75);text-align:left}} tbody tr:hover td{{background:rgba(96,165,250,.05)}} .stock-name{{font-weight:700;color:var(--strong);white-space:nowrap}}
    .badge{{display:inline-flex;align-items:center;justify-content:center;min-width:48px;height:24px;padding:0 9px;border-radius:7px;font-size:12px;font-weight:700;white-space:nowrap}}
    .long{{color:#fff;background:rgba(255,92,104,.78)}} .cautious{{color:#241b00;background:var(--warn)}} .watch{{color:#cbd7e4;background:var(--muted)}}
    .risk-low{{color:var(--fall);background:var(--fall-soft)}} .risk-medium{{color:var(--warn);background:var(--warn-soft)}} .risk-high,.risk-critical{{color:#ff746b;background:var(--danger-soft)}}
    .score{{min-width:82px}} .score b{{font-size:12px;color:var(--rise)}} .score span{{display:block;width:72px;height:4px;margin-top:4px;border-radius:4px;background:#263548}} .score i{{display:block;height:100%;border-radius:4px;background:var(--rise)}}
    .action,.reason{{max-width:290px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .reason{{color:#bdc9d7}}
    .execution-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}} .execution-card{{padding:17px;display:flex;flex-direction:column;min-height:410px}}
    .execution-card header{{display:flex;justify-content:space-between;gap:12px}} .execution-card h3{{font-size:18px}} .execution-card header span{{color:var(--sub);font-size:12px}}
    .card-score{{min-width:54px;text-align:right;font-size:18px;color:var(--rise)}} .card-score small{{display:block;color:var(--sub);font-size:9px;letter-spacing:.12em}}
    .card-tags{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:13px 0}} .card-tags>span:first-child{{color:var(--accent);margin-right:auto}}
    dl{{margin:10px 0 0}} dl div{{padding:9px 0;border-top:1px solid rgba(36,50,68,.7)}} dt{{color:var(--sub);font-size:11px}} dd{{margin:3px 0 0;color:#e4ebf4}} .execution-card footer{{margin-top:auto;padding-top:11px;border-top:1px solid var(--line);display:grid;gap:4px}} .execution-card footer b{{color:var(--sub);font-size:11px}} .execution-card footer span{{color:#c9d4e1}}
    .risk-panel{{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}} .risk-box{{padding:18px}} .risk-box h3{{margin-bottom:11px;font-size:15px}} .risk-box ul{{display:grid;gap:9px;margin:0;padding-left:20px;color:#cbd6e3}}
    .risk-status{{display:grid;grid-template-columns:1fr 1fr;gap:9px}} .risk-status div{{padding:11px;border:1px solid var(--line);border-radius:9px;background:#0a1420}} .risk-status small{{display:block;color:var(--sub)}} .risk-status b{{display:block;margin-top:4px;color:var(--warn)}}
    .watch-stack{{display:grid;gap:9px}} .watch-group{{overflow:hidden}} .watch-group summary{{display:flex;align-items:center;gap:10px;padding:13px 15px;cursor:pointer;list-style:none}} .watch-group summary::-webkit-details-marker{{display:none}}
    .watch-group summary em{{font-style:normal;padding:1px 7px;border-radius:999px;background:#243244;color:#cbd6e3}} .representatives{{margin-left:auto;color:var(--sub);font-size:12px}} .group-mark{{width:7px;height:25px;border-radius:4px;background:var(--blue)}} .group-mark.limit{{background:var(--rise)}} .group-mark.blocked{{background:var(--danger)}} .group-mark.off-theme{{background:#66758a}} .group-mark.split,.group-mark.low-score{{background:var(--warn)}}
    .tomorrow-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .tomorrow-grid article{{padding:15px;border:1px solid var(--line);border-radius:11px;background:var(--panel-2)}} .tomorrow-grid small{{display:block;color:var(--sub);margin-bottom:6px}} .tomorrow-grid b{{color:#eef5fc}} .tomorrow-grid .risk-note b{{color:var(--warn)}}
    .footer{{margin-top:28px;padding-top:17px;border-top:1px solid var(--line);text-align:center;color:var(--sub);font-size:12px}} .empty{{padding:28px;text-align:center;color:var(--sub)}}
    @media(max-width:1250px){{.cockpit{{grid-template-columns:1fr 1fr}}.cockpit-card:first-child{{grid-column:1/-1}}.execution-grid{{grid-template-columns:repeat(2,1fr)}}}}
    @media(max-width:760px){{.shell{{padding:0 14px 30px}}.topbar{{margin:0 -14px 18px;padding:20px 14px}}.topbar-inner,.risk-panel{{display:block}}.meta{{justify-content:flex-start;margin-top:14px}}.cockpit{{grid-template-columns:1fr}}.cockpit-card:first-child{{grid-column:auto}}.execution-grid,.tomorrow-grid{{grid-template-columns:1fr}}.risk-box+.risk-box{{margin-top:10px}}.representatives{{display:none}}h1{{font-size:25px}}}}
  </style>
</head>
<body>
<div class="shell">
  <header class="topbar"><div class="topbar-inner">
    <div><h1>隔夜策略决策看板</h1><p class="subtitle">{esc(subtitle)}</p></div>
    <div class="meta"><span>日期 {date}</span><span>更新时间 {esc(generated_time(doc.get('generated_at')))}</span><span>数据源 overnight_strategy.json / intraday_mapper.json</span></div>
  </div></header>

  <section class="cockpit">
    <article class="card cockpit-card">
      <div class="card-label">市场判断 / Market Regime</div>
      <div class="market-call">{esc(regime_label(market.get('regime_hint')))}</div>
      <span class="market-tag">{risk_label(market.get('risk_severity'))}风险 · 中性偏多</span>
      {f'<div class="index-strip">{index_chips}</div>' if index_chips else ''}
      {f'<details class="market-detail"><summary><span class="market-copy">{esc(market_reason)}</span><span class="toggle-label closed-label">查看全部判断依据</span><span class="toggle-label open-label">收起判断依据</span></summary><p class="market-full">{esc(market_reason_detail)}</p></details>' if market_reason else ''}
    </article>
    <article class="card cockpit-card">
      <div class="card-label">最终执行建议 / Execution</div>
      <div class="decision-layout"><div><div class="big-number">{len(positions)}<small> 只</small></div><p>执行隔夜策略</p></div></div>
      <div class="discipline"><span>条件确认</span><span>高开减仓</span><span>严格止损</span><span>聚焦主线</span></div>
    </article>
    <article class="card cockpit-card">
      <div class="card-label">风险与策略分布 / Risk</div>
      <div class="risk-line"><div><div class="risk-value">{risk_label(market.get('risk_severity'))}</div><small>当前风险等级</small></div><div class="risk-value">{risk_score}<small> / 5</small></div></div>
      <div class="risk-meter">{''.join('<i class="on"></i>' if i <= risk_score else '<i></i>' for i in range(1, 6))}</div>
      <div class="distribution">
        <div><span>建议买入</span><i style="--w:{held/max(1,len(positions))*100:.0f}%;--c:var(--rise)"></i><b>{held}</b></div>
        <div><span>谨慎买入</span><i style="--w:{cautious/max(1,len(positions))*100:.0f}%;--c:var(--warn)"></i><b>{cautious}</b></div>
        <div><span>暂不买入</span><i style="--w:100%;--c:var(--blue)"></i><b>{len(watchlist)}</b></div>
      </div>
    </article>
  </section>

  <div class="section-head"><h2>执行策略总览（{len(positions)}只）</h2><p>先看尾盘决策和明早动作</p></div>
  <section class="panel"><div class="table-scroll"><table>
    <thead><tr><th>尾盘决策</th><th>代码</th><th>名称</th><th>投资主题</th><th>交易板</th><th>评分</th><th>风险</th><th>开盘动作</th><th>核心理由</th></tr></thead>
    <tbody>{strategy_rows(positions)}</tbody>
  </table></div></section>

  <div class="section-head"><h2>重点个股执行计划</h2><p>指令卡仅保留仓位、动作、止盈止损</p></div>
  <section class="execution-grid">{execution_cards(positions)}</section>

  <div class="section-head"><h2>组合风控</h2><p>交易前置检查</p></div>
  <section class="risk-panel">
    <article class="card risk-box"><h3>风控规则</h3><ul>{controls_html or '<li>暂无额外风控规则</li>'}<li>竞价或开盘条件不满足时，放弃交易优先于勉强执行。</li></ul></article>
    <article class="card risk-box"><h3>当前风险状态</h3><div class="risk-status">
      <div><small>风险等级</small><b>{risk_label(market.get('risk_severity'))}</b></div>
      <div><small>风险分值</small><b>{risk_score} / 5</b></div>
      <div><small>主题集中</small><b>{len(primary_sectors)} 个方向</b></div>
    </div></article>
  </section>

  <div class="section-head"><h2>观察池（{len(watchlist)}只）</h2><p>按不执行原因分组</p></div>
  <section class="watch-stack">{watch_groups(watchlist)}</section>

  <div class="section-head"><h2>明日关键关注</h2><p>来自当前策略合同，不补造行情点位</p></div>
  <section class="tomorrow-grid">
    <article><small>主线方向</small><b>{esc(focus)}</b></article>
    <article><small>执行窗口</small><b>T+1 竞价至 10:00 动态处理</b></article>
    <article class="risk-note"><small>明日最大风险</small><b>{esc(max_risk)}</b></article>
    <article><small>操作关键词</small><b>条件确认 / 高开减仓 / 严格止损</b></article>
  </section>

  <footer class="footer">本页面为策略 JSON 的中文决策视图，仅供研究参考，不构成投资建议。Schema {esc(doc.get('schema_version'))} · 生成时间 {esc(doc.get('generated_at'))}</footer>
</div>
</body>
</html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--mapper")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = intraday_dir(args.date)
    input_path = Path(args.input) if args.input else root / "overnight_strategy.json"
    mapper_path = Path(args.mapper) if args.mapper else root / "intraday_mapper.json"
    output_path = Path(args.output) if args.output else root / "overnight_strategy.html"
    doc = json.loads(input_path.read_text(encoding="utf-8-sig"))
    mapper = json.loads(mapper_path.read_text(encoding="utf-8-sig")) if mapper_path.exists() else None
    if not isinstance(doc, dict) or doc.get("schema_version") != "intraday_overnight_strategy.v1":
        print("[ERROR] input must be intraday_overnight_strategy.v1", file=sys.stderr)
        return 1
    if doc.get("date") != args.date:
        print(f"[ERROR] input date must be {args.date}", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render(doc, mapper if isinstance(mapper, dict) else None), encoding="utf-8")
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
