#!/usr/bin/env python3
"""Render strategy v3 with the established A-share decision-terminal layout."""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import intraday_dir, read_json
from ashare_pilot.strategy._commands.overnight.validate import validate


def esc(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def risk_label(value: Any) -> str:
    return {
        "low": "低",
        "medium": "中等",
        "high": "高",
        "critical": "不可交易",
    }.get(str(value), "未评估")


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
    for separator in (" — ", "—", "：", ":", "。"):
        if separator in raw:
            raw = raw.split(separator, 1)[0].strip()
            break
    return raw[:18] + ("…" if len(raw) > 18 else "")


def split_market_reason(value: Any, limit: int = 90) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    if len(raw) <= limit:
        return raw, raw
    return f"{raw[:limit].rstrip()}…", raw


def direction_class(value: Any) -> str:
    return {
        "持有偏多": "long",
        "持有": "long",
        "谨慎持有": "cautious",
        "观望": "watch",
    }.get(str(value), "watch")


def direction_label(value: Any) -> str:
    return {
        "持有偏多": "持有偏多",
        "持有": "持有",
        "谨慎持有": "谨慎持有",
        "观望": "观望",
    }.get(str(value), str(value or "观望"))


def role_label(value: Any) -> str:
    return {
        "primary": "主选",
        "alternative": "备选",
        "watch": "观察",
    }.get(str(value), "确定性观察")


def posture_label(value: Any) -> str:
    return {
        "zero": "不执行",
        "very_light": "极度谨慎",
        "light": "谨慎参与",
        "normal": "常规执行",
    }.get(str(value), "未确认")


def generated_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def score_bar(value: Any) -> str:
    try:
        score = max(0.0, min(100.0, float(value)))
        label = f"{score:.1f}"
    except (TypeError, ValueError):
        score, label = 0.0, "—"
    return (
        f'<div class="score"><b>{label}</b><span>'
        f'<i style="width:{score:.1f}%"></i></span></div>'
    )


def plan_of(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("t_plus_1_plan")
    return value if isinstance(value, dict) else {}


def expert_rule_text(item: dict[str, Any]) -> str:
    rules = item.get("rules_applied")
    if not isinstance(rules, list):
        return "—"
    expert_ids = [
        value
        for value in rules
        if isinstance(value, str)
        and value.startswith("E")
        and value[1:].isdigit()
        and len(value[1:]) >= 3
    ]
    return " / ".join(expert_ids) or "—"


def shadow_text(item: dict[str, Any]) -> str:
    shadow = item.get("theme_support_shadow")
    if not isinstance(shadow, dict) or shadow.get("available") is not True:
        return "不可用"
    return (
        f"{shadow.get('primary_theme') or '—'} / "
        f"核心 {shadow.get('core_heat')} / "
        f"扩散 {shadow.get('diffusion_heat')} / "
        f"#{shadow.get('theme_rank')}"
    )


def market_chips(mapper: dict[str, Any] | None) -> str:
    market = (
        mapper.get("market")
        if isinstance(mapper, dict) and isinstance(mapper.get("market"), dict)
        else {}
    )
    indices = market.get("indices") if isinstance(market.get("indices"), list) else []
    wanted = {"sh000001", "sz399001", "sz399006", "sh000688"}
    chips = []
    for item in indices:
        if (
            not isinstance(item, dict)
            or item.get("code") not in wanted
            or not item.get("percent")
        ):
            continue
        change = str(item["percent"])
        tone = (
            "index-up"
            if change.startswith("+")
            else "index-down"
            if change.startswith("-")
            else "index-flat"
        )
        chips.append(
            f'<span class="index-chip {tone}">{esc(item.get("name"))} '
            f"<b>{esc(change)}</b></span>"
        )
    return "".join(chips)


def data_completeness(
    document: dict[str, Any],
    mapper: dict[str, Any] | None,
) -> tuple[str, str, str]:
    quality = document.get("data_quality")
    if not isinstance(quality, dict) and isinstance(mapper, dict):
        summary = mapper.get("pool_summary")
        quality = summary.get("data_quality") if isinstance(summary, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    money = quality.get("money_flow")
    money = money if isinstance(money, dict) else {}
    status = str(money.get("status") or "unknown")
    requested = money.get("requested_stock_count")
    matched = money.get("matched_stock_count")
    coverage = money.get("coverage_pct")
    pages = money.get("pages_fetched")
    failed_page = money.get("failed_page")
    if money.get("fetch_status") == "threshold_reached":
        threshold = money.get("min_main_inflow_yuan")
        threshold_wan = (
            round(float(threshold) / 10_000)
            if isinstance(threshold, (int, float))
            else "未知"
        )
        return (
            "partial",
            "资金流数据按最低额度过滤",
            f"最低额度为 {threshold_wan} 万元；覆盖 {matched}/{requested} 只"
            f"（{coverage}%），使用 {pages} 个分页后达到阈值边界并主动停止。",
        )
    if status == "complete":
        return (
            "complete",
            "资金流数据完整",
            f"分析池覆盖 {matched}/{requested} 只（{coverage}%），"
            f"共使用 {pages} 个成功分页。",
        )
    if status == "partial":
        detail = (
            f"覆盖 {matched}/{requested} 只（{coverage}%）；"
            f"已保留 {pages} 个成功分页"
        )
        if failed_page is not None:
            detail += f"，第 {failed_page} 页失败后未重新抓取"
        return "partial", "资金流数据部分完整", detail + "。"
    if status in {"unavailable", "failed"}:
        return (
            "unavailable",
            "资金流数据不可用",
            "本次不生成资金维度伪分数，相关股票进入确定性观察池。",
        )
    return (
        "unknown",
        "数据完整性未确认",
        "当前策略合同未携带完整的资金流覆盖元数据。",
    )


def strategy_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        rows.append(
            f"""<tr>
              <td><span class="badge {direction_class(item.get('direction'))}">{esc(direction_label(item.get('direction')))}</span></td>
              <td class="mono">{esc(item.get('code'))}</td>
              <td class="stock-name">{esc(item.get('name'))}</td>
              <td>{esc(item.get('primary_theme'))}</td>
              <td>{score_bar(item.get('overnight_score'))}</td>
              <td><span class="badge risk-{risk_class(item.get('risk_severity'))}">{risk_label(item.get('risk_severity'))}</span></td>
              <td class="reason" title="{esc(item.get('key_reason'))}">{esc(item.get('key_reason'))}</td>
            </tr>"""
        )
    return "".join(rows) or (
        '<tr><td colspan="7" class="empty">'
        "无合适执行候选；空执行池是正常业务结果</td></tr>"
    )


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
                <span class="badge {direction_class(item.get('direction'))}">主选 · {esc(direction_label(item.get('direction')))}</span>
                <span class="badge risk-{risk_class(item.get('risk_severity'))}">{risk_label(item.get('risk_severity'))}风险</span>
              </div>
              <dl>
                <div><dt>开盘动作</dt><dd>{esc(plan.get('open_strategy'))}</dd></div>
                <div><dt>执行条件</dt><dd>{esc(item.get('execution_condition'))}</dd></div>
                <div><dt>止损纪律</dt><dd>{esc(plan.get('stop_loss'))}</dd></div>
                <div><dt>止盈计划</dt><dd>{esc(plan.get('take_profit'))}</dd></div>
                <div><dt>Theme Shadow</dt><dd>{esc(shadow_text(item))}</dd></div>
                <div><dt>专家规则</dt><dd>{esc(expert_rule_text(item))}</dd></div>
              </dl>
              <footer><b>核心理由</b><span>{esc(item.get('key_reason'))}</span></footer>
            </article>"""
        )
    return "".join(cards) or '<div class="empty">今日无执行指令卡</div>'


def watch_group(item: dict[str, Any]) -> tuple[str, str]:
    if item.get("execution_role") == "alternative":
        return "备选（暂不执行，仅作为替代）", "threshold"
    if item.get("execution_role") == "watch":
        return "合格观察", "wait"
    reasons = item.get("observation_reasons")
    reasons = reasons if isinstance(reasons, list) else []
    text = " ".join(
        [
            *[str(reason) for reason in reasons],
            str(item.get("primary_observation_reason") or ""),
            str(item.get("key_reason") or ""),
            str(item.get("observation_summary") or ""),
        ]
    )
    if "sealed_limit_up" in text or "封板" in text or "涨停" in text:
        return "涨停封板", "limit"
    if "board_" in text or "板块排除" in text or "不可交易" in text:
        return "板块不可交易", "blocked"
    if any(word in text for word in ("unavailable", "missing", "no_data", "缺失")):
        return "关键数据缺失", "missing"
    if any(
        word in text
        for word in ("below_configured", "below_floor", "below_vwap", "i14_watch")
    ):
        return "执行门槛未通过", "threshold"
    if item.get("direction") == "观望":
        return "合格但观望", "wait"
    return "其他观察", "wait"


def watch_reason(item: dict[str, Any]) -> str:
    reason = str(
        item.get("execution_condition")
        or item.get("observation_summary")
        or item.get("key_reason")
        or item.get("primary_observation_reason")
        or "等待条件确认"
    )
    rules = expert_rule_text(item)
    return reason if rules == "—" else f"{reason} · 专家规则 {rules}"


def watch_groups(items: list[dict[str, Any]]) -> str:
    order = [
        "备选（暂不执行，仅作为替代）",
        "合格观察",
        "涨停封板",
        "板块不可交易",
        "关键数据缺失",
        "执行门槛未通过",
        "合格但观望",
        "其他观察",
    ]
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
            f"""<tr>
              <td class="mono">{esc(item.get('code'))}</td>
              <td class="stock-name">{esc(item.get('name'))}</td>
              <td>{esc(item.get('primary_theme'))}</td>
              <td>{esc(item.get('score_status'))}</td>
              <td>{esc(item.get('overnight_score'))}</td>
              <td><span class="badge watch">{esc(role_label(item.get('execution_role')))}</span></td>
              <td>{esc(watch_reason(item))}</td>
              <td>{esc(shadow_text(item))}</td>
            </tr>"""
            for item in values
        )
        names = " / ".join(str(item.get("name") or "") for item in values[:3])
        blocks.append(
            f"""<details class="watch-group">
              <summary><span class="group-mark {kind}"></span><b>{label}</b>
              <em>{len(values)}</em><span class="representatives">{esc(names)}</span></summary>
              <div class="table-scroll"><table><thead><tr>
              <th>代码</th><th>名称</th><th>投资主题</th>
              <th>评分状态</th><th>评分</th><th>状态</th><th>观察理由</th>
              <th>Theme Shadow</th></tr></thead><tbody>{rows}</tbody></table></div>
            </details>"""
        )
    return "".join(blocks) or '<div class="empty">观察池为空</div>'


def render(document: dict[str, Any], mapper: dict[str, Any] | None = None) -> str:
    date = esc(document.get("date"))
    market = (
        document.get("market_assessment")
        if isinstance(document.get("market_assessment"), dict)
        else {}
    )
    strategy = (
        document.get("strategy")
        if isinstance(document.get("strategy"), dict)
        else {}
    )
    recommendations = [
        item
        for item in document.get("recommendations", [])
        if isinstance(item, dict)
    ]
    eligible = [
        item
        for item in document.get("eligible_watchlist", [])
        if isinstance(item, dict)
    ]
    observations = [
        item
        for item in document.get("observations", [])
        if isinstance(item, dict)
    ]
    watchlist = eligible + observations
    controls = strategy.get("risk_control")
    controls = controls if isinstance(controls, list) else []
    market_risk = market.get("risk_severity") or strategy.get("risk_severity")
    risk = risk_class(market_risk)
    risk_score = {"low": 1, "medium": 3, "high": 4, "critical": 5}.get(risk, 3)
    alternatives = sum(
        item.get("execution_role") == "alternative" for item in eligible
    )
    eligible_watches = len(eligible) - alternatives
    primary_sectors = []
    for item in recommendations:
        sector = str(item.get("primary_theme") or "")
        if sector and sector not in primary_sectors:
            primary_sectors.append(sector)
    focus = " / ".join(primary_sectors[:3]) or "等待主线确认"
    controls_html = "".join(f"<li>{esc(value)}</li>" for value in controls)
    subtitle = (
        market.get("tomorrow_expectation")
        or market.get("reasoning_trace")
        or "基于双池合同的尾盘隔夜决策"
    )
    index_chips = market_chips(mapper)
    market_reason, market_reason_detail = split_market_reason(
        market.get("reasoning_trace")
    )
    quality_kind, quality_title, quality_detail = data_completeness(
        document, mapper
    )
    max_risk = (
        controls[0]
        if controls
        else market.get("tomorrow_expectation")
        or "竞价条件不满足时不执行"
    )
    regime = market.get("regime_hint") or market.get("regime")

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>隔夜策略决策看板 · {date}</title>
<style>
:root{{--bg:#070B10;--panel:#111923;--panel2:#0E1724;--line:#243244;--text:#E7EDF5;--strong:#FFF;--sub:#91A1B5;--accent:#22D3EE;--blue:#60A5FA;--rise:#FF5C68;--rise-soft:rgba(255,92,104,.14);--fall:#32D583;--fall-soft:rgba(50,213,131,.14);--warn:#FDB022;--warn-soft:rgba(253,176,34,.15);--danger:#F04438;--danger-soft:rgba(240,68,56,.15);--muted:#34445A}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 12% -8%,rgba(34,211,238,.09),transparent 28%),linear-gradient(180deg,#09111a,var(--bg) 28%)}}
.mono,.metric strong,.card-score{{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}}.shell{{max-width:1680px;margin:auto;padding:0 28px 48px}}.topbar{{margin:0 -28px 24px;padding:25px 28px;border-bottom:1px solid var(--line);background:linear-gradient(110deg,rgba(7,11,16,.98),rgba(14,28,43,.95) 55%,rgba(7,11,16,.98))}}.topbar-inner{{max-width:1624px;margin:auto;display:flex;justify-content:space-between;gap:30px;align-items:flex-start}}
h1,h2,h3,p{{margin:0}}h1{{font-size:30px;letter-spacing:.02em}}.subtitle{{max-width:900px;margin-top:7px;color:#a9b8ca}}.meta{{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:520px}}.meta span{{padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--sub);background:rgba(9,18,28,.8);font-size:12px}}
.cockpit{{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:14px}}.card,.panel,.execution-card,.watch-group{{border:1px solid var(--line);border-radius:14px;background:linear-gradient(180deg,rgba(17,25,35,.97),rgba(10,17,26,.97));box-shadow:0 18px 44px rgba(0,0,0,.24)}}.data-quality{{margin:0 0 14px;padding:12px 15px;border:1px solid var(--line);border-radius:10px;background:rgba(96,165,250,.08);color:#cbd7e4}}.data-quality b{{margin-right:10px;color:var(--blue)}}.data-quality.complete{{background:rgba(50,213,131,.09);border-color:rgba(50,213,131,.28)}}.data-quality.complete b{{color:var(--fall)}}.data-quality.partial,.data-quality.unknown{{background:var(--warn-soft);border-color:rgba(253,176,34,.34)}}.data-quality.partial b,.data-quality.unknown b{{color:var(--warn)}}.data-quality.unavailable{{background:var(--danger-soft);border-color:rgba(240,68,56,.34)}}.data-quality.unavailable b{{color:#ff746b}}
.cockpit-card{{min-height:235px;padding:19px;position:relative;overflow:hidden}}.cockpit-card:before{{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:2px;background:linear-gradient(90deg,var(--accent),transparent 70%)}}.card-label{{color:var(--sub);font-size:12px;letter-spacing:.12em;text-transform:uppercase}}.market-call{{margin:20px 0 8px;font-size:25px;font-weight:800;color:var(--strong)}}.market-tag{{display:inline-flex;padding:4px 9px;border:1px solid rgba(253,176,34,.34);border-radius:6px;color:var(--warn);background:var(--warn-soft);font-weight:700}}.index-strip{{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}}.index-chip{{display:inline-flex;gap:5px;align-items:center;padding:4px 8px;border-radius:7px;font-size:12px;border:1px solid transparent}}.index-up{{color:var(--rise);background:var(--rise-soft)}}.index-down{{color:var(--fall);background:var(--fall-soft)}}.index-flat{{color:#c7d2e1;background:rgba(145,161,181,.12)}}
.market-copy{{margin-top:13px;color:#b9c6d5}}.market-detail{{margin-top:13px;color:#b9c6d5}}.market-detail summary{{cursor:pointer;list-style:none}}.market-detail summary::-webkit-details-marker{{display:none}}.market-detail .toggle-label{{display:block;margin-top:6px;color:var(--sub);font-size:12px}}.market-detail .open-label,.market-detail .market-full{{display:none}}.market-detail[open] .market-copy,.market-detail[open] .closed-label{{display:none}}.market-detail[open] .open-label{{display:block}}.market-detail[open] .market-full{{display:block;margin:8px 0 0}}.decision-layout{{margin-top:18px}}.big-number{{font:800 42px/1 ui-monospace,SFMono-Regular,monospace;color:var(--rise)}}.big-number small{{font:600 14px/1.2 inherit;color:var(--sub)}}.discipline{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:20px}}.discipline span{{padding:6px 8px;border-radius:6px;background:#151f2b;color:#c9d4e2;font-size:12px}}
.risk-line{{display:flex;justify-content:space-between;align-items:end;margin:18px 0 12px}}.risk-value{{font-size:26px;font-weight:800;color:var(--warn)}}.risk-value small{{font-size:13px;color:var(--sub)}}.risk-meter{{display:grid;grid-template-columns:repeat(5,1fr);gap:5px}}.risk-meter i{{height:6px;border-radius:5px;background:#233143}}.risk-meter i.on{{background:var(--warn)}}.distribution{{display:grid;gap:8px;margin-top:19px}}.distribution div{{display:grid;grid-template-columns:78px 1fr 26px;gap:9px;align-items:center}}.distribution span{{color:var(--sub);font-size:12px}}.distribution i{{height:7px;border-radius:9px;background:#263548;overflow:hidden}}.distribution i:after{{content:"";display:block;width:var(--w);height:100%;background:var(--c)}}.distribution b{{text-align:right}}
.section-head{{display:flex;justify-content:space-between;align-items:end;margin:30px 0 11px}}.section-head h2{{font-size:20px}}.section-head h2:before{{content:"";display:inline-block;width:4px;height:18px;margin-right:9px;vertical-align:-2px;border-radius:2px;background:var(--accent)}}.section-head p{{color:var(--sub);font-size:12px}}.panel{{overflow:hidden}}.table-scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th{{color:var(--sub);font-weight:600;background:rgba(10,17,26,.9);white-space:nowrap}}td,th{{padding:12px 10px;border-bottom:1px solid rgba(36,50,68,.75);text-align:left}}tbody tr:hover td{{background:rgba(96,165,250,.05)}}.stock-name{{font-weight:700;color:var(--strong);white-space:nowrap}}
.badge{{display:inline-flex;align-items:center;justify-content:center;min-width:48px;height:24px;padding:0 9px;border-radius:7px;font-size:12px;font-weight:700;white-space:nowrap}}.long{{color:#fff;background:rgba(255,92,104,.78)}}.cautious{{color:#241b00;background:var(--warn)}}.watch{{color:#cbd7e4;background:var(--muted)}}.risk-low{{color:var(--fall);background:var(--fall-soft)}}.risk-medium{{color:var(--warn);background:var(--warn-soft)}}.risk-high,.risk-critical{{color:#ff746b;background:var(--danger-soft)}}.score{{min-width:82px}}.score b{{font-size:12px;color:var(--rise)}}.score span{{display:block;width:72px;height:4px;margin-top:4px;border-radius:4px;background:#263548}}.score i{{display:block;height:100%;border-radius:4px;background:var(--rise)}}.action,.reason{{max-width:290px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.overview-table .reason{{max-width:520px}}.reason{{color:#bdc9d7}}
.execution-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}}.execution-card{{padding:17px;display:flex;flex-direction:column;min-height:410px}}.execution-card header{{display:flex;justify-content:space-between;gap:12px}}.execution-card h3{{font-size:18px}}.execution-card header span{{color:var(--sub);font-size:12px}}.card-score{{min-width:54px;text-align:right;font-size:18px;color:var(--rise)}}.card-score small{{display:block;color:var(--sub);font-size:9px;letter-spacing:.12em}}.card-tags{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:13px 0}}.card-tags>span:first-child{{color:var(--accent);margin-right:auto}}dl{{margin:10px 0 0}}dl div{{padding:9px 0;border-top:1px solid rgba(36,50,68,.7)}}dt{{color:var(--sub);font-size:11px}}dd{{margin:3px 0 0;color:#e4ebf4}}.execution-card footer{{margin-top:auto;padding-top:11px;border-top:1px solid var(--line);display:grid;gap:4px}}.execution-card footer b{{color:var(--sub);font-size:11px}}.execution-card footer span{{color:#c9d4e1}}
.risk-panel{{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}}.risk-box{{padding:18px}}.risk-box h3{{margin-bottom:11px;font-size:15px}}.risk-box ul{{display:grid;gap:9px;margin:0;padding-left:20px;color:#cbd6e3}}.risk-status{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.risk-status div{{padding:11px;border:1px solid var(--line);border-radius:9px;background:#0a1420}}.risk-status small{{display:block;color:var(--sub)}}.risk-status b{{display:block;margin-top:4px;color:var(--warn)}}
.watch-stack{{display:grid;gap:9px}}.watch-group{{overflow:hidden}}.watch-group summary{{display:flex;align-items:center;gap:10px;padding:13px 15px;cursor:pointer;list-style:none}}.watch-group summary::-webkit-details-marker{{display:none}}.watch-group summary em{{font-style:normal;padding:1px 7px;border-radius:999px;background:#243244;color:#cbd6e3}}.representatives{{margin-left:auto;color:var(--sub);font-size:12px}}.group-mark{{width:7px;height:25px;border-radius:4px;background:var(--blue)}}.group-mark.limit{{background:var(--rise)}}.group-mark.blocked{{background:var(--danger)}}.group-mark.missing{{background:#a78bfa}}.group-mark.threshold{{background:var(--warn)}}.tomorrow-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.tomorrow-grid article{{padding:15px;border:1px solid var(--line);border-radius:11px;background:var(--panel2)}}.tomorrow-grid small{{display:block;color:var(--sub);margin-bottom:6px}}.tomorrow-grid b{{color:#eef5fc}}.tomorrow-grid .risk-note b{{color:var(--warn)}}.footer{{margin-top:28px;padding-top:17px;border-top:1px solid var(--line);text-align:center;color:var(--sub);font-size:12px}}.empty{{padding:28px;text-align:center;color:var(--sub)}}
@media(max-width:1250px){{.cockpit{{grid-template-columns:1fr 1fr}}.cockpit-card:first-child{{grid-column:1/-1}}.execution-grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:760px){{.shell{{padding:0 14px 30px}}.topbar{{margin:0 -14px 18px;padding:20px 14px}}.topbar-inner,.risk-panel{{display:block}}.meta{{justify-content:flex-start;margin-top:14px}}.cockpit{{grid-template-columns:1fr}}.cockpit-card:first-child{{grid-column:auto}}.execution-grid,.tomorrow-grid{{grid-template-columns:1fr}}.risk-box+.risk-box{{margin-top:10px}}.representatives{{display:none}}h1{{font-size:25px}}}}
</style></head><body><div class="shell">
<header class="topbar"><div class="topbar-inner">
<div><h1>隔夜策略决策看板</h1><p class="subtitle">{esc(subtitle)}</p></div>
<div class="meta"><span>日期 {date}</span><span>更新时间 {esc(generated_time(document.get('generated_at')))}</span><span>数据源 overnight_strategy.json / intraday_mapper.json</span></div>
</div></header>
<aside class="data-quality {esc(quality_kind)}"><b>数据完整性 · {esc(quality_title)}</b><span>{esc(quality_detail)}</span></aside>
<section class="cockpit">
<article class="card cockpit-card"><div class="card-label">市场判断 / Market Regime</div>
<div class="market-call">{esc(regime_label(regime))}</div>
<span class="market-tag">{risk_label(market_risk)}风险 · 条件执行</span>
{f'<div class="index-strip">{index_chips}</div>' if index_chips else ''}
{f'<details class="market-detail"><summary><span class="market-copy">{esc(market_reason)}</span><span class="toggle-label closed-label">查看全部判断依据</span><span class="toggle-label open-label">收起判断依据</span></summary><p class="market-full">{esc(market_reason_detail)}</p></details>' if market_reason else ''}
</article>
<article class="card cockpit-card"><div class="card-label">最终执行建议 / Execution</div>
<div class="decision-layout"><div class="big-number">{len(recommendations)}<small> 只</small></div><p>执行隔夜策略</p></div>
<div class="discipline"><span>条件确认</span><span>高开减仓</span><span>严格止损</span><span>聚焦主线</span></div></article>
<article class="card cockpit-card"><div class="card-label">风险与策略分布 / Risk</div>
<div class="risk-line"><div><div class="risk-value">{risk_label(market_risk)}</div><small>当前风险等级</small></div><div class="risk-value">{risk_score}<small> / 5</small></div></div>
<div class="risk-meter">{''.join('<i class="on"></i>' if index <= risk_score else '<i></i>' for index in range(1, 6))}</div>
<div class="distribution"><div><span>主选</span><i style="--w:100%;--c:var(--rise)"></i><b>{len(recommendations)}</b></div>
<div><span>备选</span><i style="--w:100%;--c:var(--warn)"></i><b>{alternatives}</b></div>
<div><span>观察</span><i style="--w:100%;--c:var(--blue)"></i><b>{eligible_watches + len(observations)}</b></div></div></article>
</section>
<div class="section-head"><h2>执行策略总览（{len(recommendations)}只）</h2><p>先看尾盘决策和明早动作</p></div>
<section class="panel"><div class="table-scroll"><table class="overview-table"><thead><tr><th>尾盘决策</th><th>代码</th><th>名称</th><th>投资主题</th><th>评分</th><th>风险</th><th>核心理由</th></tr></thead><tbody>{strategy_rows(recommendations)}</tbody></table></div></section>
<div class="section-head"><h2>重点个股执行计划</h2><p>指令卡保留动作、止盈止损与 Theme Shadow</p></div>
<section class="execution-grid">{execution_cards(recommendations)}</section>
<div class="section-head"><h2>组合风控</h2><p>交易前置检查</p></div>
<section class="risk-panel"><article class="card risk-box"><h3>风控规则</h3><ul>{controls_html or '<li>暂无额外风控规则</li>'}<li>竞价或开盘条件不满足时，放弃交易优先于勉强执行。</li></ul></article>
<article class="card risk-box"><h3>当前风险状态</h3><div class="risk-status"><div><small>风险等级</small><b>{risk_label(market_risk)}</b></div><div><small>风险分值</small><b>{risk_score} / 5</b></div><div><small>主题集中</small><b>{len(primary_sectors)} 个方向</b></div><div><small>风险姿态</small><b>{esc(posture_label(strategy.get('risk_posture')))}</b></div></div><p class="market-copy">{esc(strategy.get('execution_principle'))}</p></article></section>
<div class="section-head"><h2>观察池（{len(watchlist)}只）</h2><p>{len(eligible)} 只合格但观望 / {len(observations)} 只确定性观察，按不执行原因分组</p></div>
<section class="watch-stack">{watch_groups(watchlist)}</section>
<div class="section-head"><h2>明日关键关注</h2><p>来自当前策略合同，不补造行情点位</p></div>
<section class="tomorrow-grid"><article><small>主线方向</small><b>{esc(focus)}</b></article><article><small>执行窗口</small><b>T+1 竞价至 10:00 动态处理</b></article><article class="risk-note"><small>明日最大风险</small><b>{esc(max_risk)}</b></article><article><small>操作关键词</small><b>条件确认 / 高开减仓 / 严格止损</b></article></section>
<footer class="footer">本页面为策略 JSON 的中文决策视图，仅供研究参考，不构成投资建议。Schema {esc(document.get('schema_version'))} · 生成时间 {esc(document.get('generated_at'))}</footer>
</div></body></html>"""


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
