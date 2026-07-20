#!/usr/bin/env python3
"""Render operation decision + snapshot as Bloomberg × IC memo × A-share board HTML."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def valid_run_manifest(operation_dir: Path, manifest: Any) -> bool:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "intraday_operation_run_manifest.v1":
        return False
    for name_key, hash_key in (
        ("snapshot", "snapshot_sha256"),
        ("decision", "decision_sha256"),
        ("html", "html_sha256"),
    ):
        name = manifest.get(name_key)
        expected = manifest.get(hash_key)
        path = operation_dir / name if isinstance(name, str) else None
        if path is None or not path.exists() or not isinstance(expected, str):
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def latest_run_manifest(operation_dir: Path) -> dict[str, Any] | None:
    manifests = []
    for path in operation_dir.glob("operation_run_*.json"):
        manifest = read_json(path)
        if valid_run_manifest(operation_dir, manifest):
            manifests.append(manifest)
    if manifests:
        return sorted(manifests, key=lambda item: str(item.get("generated_at") or ""))[-1]
    projected = read_json(operation_dir / "operation_run.latest.json")
    return projected if valid_run_manifest(operation_dir, projected) else None


def esc(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "—"
    return html.escape(str(value), quote=True)


def number(value: Any, digits: int = 2) -> str:
    try:
        text = f"{float(value):.{digits}f}"
        return text.rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return esc(value)


def pct(value: Any, digits: int = 2) -> str:
    try:
        v = float(value)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.{digits}f}%"
    except (TypeError, ValueError):
        return esc(value)


def money_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return esc(value)


def generated_time(value: Any) -> str:
    try:
        return (
            datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            .astimezone()
            .strftime("%H:%M")
        )
    except (TypeError, ValueError):
        return "—"


def class_label(value: Any) -> str:
    return {
        "A": "现在可参与",
        "B": "等确认",
        "C": "只观察",
        "D": "放弃/回避",
    }.get(str(value), str(value or "—"))


def class_css(value: Any) -> str:
    return {
        "A": "cls-a",
        "B": "cls-b",
        "C": "cls-c",
        "D": "cls-d",
    }.get(str(value), "cls-c")


def action_label(value: Any) -> str:
    return {
        "NORMAL": "正常参与",
        "SELECTIVE": "精选参与",
        "WAIT": "等待确认",
        "NO_NEW_BUY": "禁止新开仓",
    }.get(str(value), str(value or "—"))


def action_css(value: Any) -> str:
    return {
        "NORMAL": "rise",
        "SELECTIVE": "warn",
        "WAIT": "blue",
        "NO_NEW_BUY": "fall",
    }.get(str(value), "neutral")


def regime_label(value: Any) -> str:
    return {
        "strong": "强势",
        "risk_on": "风险偏好",
        "balanced": "均衡",
        "neutral": "中性",
        "weak": "弱势",
        "risk_off": "风险收缩",
        "panic": "恐慌",
    }.get(str(value), str(value or "未确认"))


def delivery_label(value: Any) -> str:
    return {
        "EVALUATE": "可评估执行",
        "WAIT_SECOND_CONFIRMATION": "等待二次确认",
        "OBSERVE_ONLY": "仅观察",
    }.get(str(value), str(value or "—"))


def flag_chip(ok_text: str, bad_text: str, ok: bool | None) -> str:
    """Green = condition passed; red = failed; gray = unknown. Not price up/down."""
    if ok is True:
        return f'<span class="flag ok" title="信号通过">{esc(ok_text)}</span>'
    if ok is False:
        return f'<span class="flag bad" title="信号未通过">{esc(bad_text)}</span>'
    return f'<span class="flag mute" title="数据不足">{esc(ok_text)}·未知</span>'


def by_code(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {str(x["code"]): x for x in items if isinstance(x, dict) and x.get("code")}


def index_name(code: str) -> str:
    return {
        "sh000001": "上证",
        "sz399001": "深证",
        "sh000688": "科创50",
        "sz399006": "创业板",
    }.get(code, code)


def reason_zh(reason: Any) -> str:
    mapping = {
        "global_no_new_buy": "全局禁止新开仓",
        "global_wait": "全局等待确认",
        "global_selective": "全局精选模式",
        "price_action_not_clean": "价格行为不干净",
        "volume_not_confirmed": "量能未确认",
        "theme_failed": "主题确认失败",
        "theme_fading": "主题转弱",
        "theme_narrow": "主题窄幅确认",
        "theme_confirmation_unknown": "主题确认未知",
        "extended_from_anchor": "偏离锚点过远",
        "below_vwap": "现价低于VWAP",
        "high_open_fade": "高开回落",
        "first_bar_red_flag": "首根5分钟大阴线",
        "data_warning": "数据告警",
        "hard_block": "硬性拦截",
        "delivery_wait_second": "等待二次确认交付",
        "delivery_observe_only": "迟到交付仅观察",
        "sz_below_-0.5": "深证跌幅>0.5%",
        "regime_weak": "实时regime弱势",
        "market_breadth_unavailable": "市场宽度不可用",
    }
    text = str(reason or "")
    return mapping.get(text, text)


def signal_line(snap: dict[str, Any] | None) -> str:
    if not isinstance(snap, dict):
        return "—"
    signals = snap.get("signals") if isinstance(snap.get("signals"), dict) else {}
    quote = snap.get("quote") if isinstance(snap.get("quote"), dict) else {}
    dist = snap.get("dist_atr") if isinstance(snap.get("dist_atr"), dict) else {}
    strategy = snap.get("strategy") if isinstance(snap.get("strategy"), dict) else {}
    anchor = strategy.get("anchor") or "MA5"
    anchor_key = "ma5" if "MA5" in str(anchor).upper() else "ma20" if "MA20" in str(anchor).upper() else "ma5"
    parts = [
        f"现价 {number(quote.get('price'), 2)} ({pct(quote.get('percent'))})",
        f"锚点{anchor} 距 {number(dist.get(anchor_key), 2)}ATR",
        "站上MA5" if signals.get("above_ma5") else "低于MA5",
        "站上MA20" if signals.get("above_ma20") else "低于MA20",
        "低于VWAP" if signals.get("below_vwap") else "站上VWAP",
    ]
    if signals.get("volume_confirmed") is True:
        parts.append("5分钟放量确认")
    elif signals.get("volume_confirmed") is False:
        parts.append("5分钟量能未确认")
    if signals.get("price_strength_confirmed") is True:
        parts.append("价格强度确认")
    elif signals.get("price_strength_confirmed") is False:
        parts.append("价格强度未确认")
    if signals.get("first_bar_red_flag"):
        parts.append("首根大阴线")
    if signals.get("high_open_fade"):
        parts.append("高开回落")
    if signals.get("extended_from_anchor"):
        parts.append("偏离锚点")
    return " · ".join(parts)


def merge_rows(decision: dict[str, Any], snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    snap_map = by_code(snapshot.get("stocks") if isinstance(snapshot, dict) else [])
    rows: list[dict[str, Any]] = []
    for item in decision.get("stocks", []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        snap = snap_map.get(code, {})
        strategy = snap.get("strategy") if isinstance(snap.get("strategy"), dict) else {}
        quote = snap.get("quote") if isinstance(snap.get("quote"), dict) else {}
        theme = snap.get("theme_confirmation") if isinstance(snap.get("theme_confirmation"), dict) else {}
        transition = snap.get("transition") if isinstance(snap.get("transition"), dict) else {}
        t1 = item.get("t1_controls") if isinstance(item.get("t1_controls"), dict) else {}
        exit_plan = t1.get("t1_exit_plan") if isinstance(t1.get("t1_exit_plan"), dict) else {}
        reasons = [reason_zh(x) for x in (item.get("class_reasons") or [])]
        rows.append(
            {
                "code": code,
                "name": item.get("name") or strategy.get("name") or code,
                "final_class": item.get("final_class"),
                "mechanical_class": item.get("mechanical_class"),
                "max_allowed_class": item.get("max_allowed_class"),
                "final_position_max": item.get("final_position_max"),
                "trigger": item.get("trigger"),
                "reasons": reasons,
                "hard_blocks": item.get("hard_blocks") or [],
                "sector": strategy.get("sector"),
                "direction": strategy.get("direction"),
                "rating": strategy.get("rating"),
                "entry_profile": strategy.get("entry_profile") or strategy.get("profile"),
                "anchor": strategy.get("anchor"),
                "entry_trigger": strategy.get("entry_trigger") or strategy.get("trigger"),
                "no_buy": strategy.get("no_buy_condition") or strategy.get("no_buy"),
                "morning_budget": strategy.get("position_budget") or strategy.get("position"),
                "price": quote.get("price"),
                "percent": quote.get("percent"),
                "vwap": quote.get("vwap_est"),
                "theme": theme.get("theme") or strategy.get("sector"),
                "theme_state": theme.get("theme_state"),
                "transition": transition.get("transition"),
                "prev_class": transition.get("previous_class"),
                "signals": snap.get("signals") if isinstance(snap.get("signals"), dict) else {},
                "signal_text": signal_line(snap if snap else None),
                "pre_entry": t1.get("pre_entry_invalidation"),
                "t_risk": t1.get("post_entry_t_risk_alert"),
                "gap_up": exit_plan.get("gap_up_action"),
                "flat_open": exit_plan.get("flat_open_action"),
                "gap_down": exit_plan.get("gap_down_action"),
                "overnight_risk": exit_plan.get("overnight_risk"),
            }
        )
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    rows.sort(key=lambda x: (order.get(str(x.get("final_class")), 9), str(x.get("code"))))
    return rows


def render_index_chips(market: dict[str, Any]) -> str:
    indices = market.get("indices") if isinstance(market.get("indices"), dict) else {}
    chips = []
    for code in ("sh000001", "sz399001", "sh000688", "sz399006"):
        item = indices.get(code)
        if not isinstance(item, dict) or item.get("current_pct") is None:
            continue
        change = float(item["current_pct"])
        tone = "up" if change > 0 else "down" if change < 0 else "flat"
        chips.append(
            f'<span class="index-chip {tone}">{esc(index_name(code))} <b>{esc(pct(change))}</b></span>'
        )
    return "".join(chips) or '<span class="index-chip flat">指数数据不可用</span>'


def render_class_mix(counts: dict[str, int], total: int) -> str:
    colors = {"A": "#FF5C68", "B": "#FDB022", "C": "#60A5FA", "D": "#64748B"}
    labels = {"A": "可参与", "B": "等确认", "C": "只观察", "D": "放弃"}
    track = "".join(
        f'<i style="width:{counts[k]/max(1,total)*100:.1f}%;background:{colors[k]}"></i>'
        for k in ("A", "B", "C", "D")
        if counts[k]
    )
    legend = "".join(
        f'<span><b style="color:{colors[k]}">{counts[k]}</b>{labels[k]}</span>'
        for k in ("A", "B", "C", "D")
    )
    return f"""<div class="mix-box">
      <div class="mix-total"><b>{total}</b><span>策略池</span></div>
      <div class="mix-track">{track or '<i style="width:100%;background:#233143"></i>'}</div>
      <div class="mix-legend">{legend}</div>
    </div>"""


def pct_tone(value: Any) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return ""


def overview_rows(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        reason = " / ".join(row["reasons"][:3]) if row["reasons"] else "—"
        body.append(
            f"""<tr>
              <td><span class="badge {class_css(row.get('final_class'))}">{esc(row.get('final_class'))}</span></td>
              <td class="mono">{esc(row.get('code'))}</td>
              <td class="strong">{esc(row.get('name'))}</td>
              <td>{esc(row.get('sector'))}</td>
              <td>{esc(row.get('direction'))} · {esc(row.get('rating'))}</td>
              <td class="mono">{esc(number(row.get('price'), 2))} <span class="{pct_tone(row.get('percent'))}">{esc(pct(row.get('percent')))}</span></td>
              <td class="mono">{esc(money_pct(row.get('final_position_max')))}</td>
              <td class="clamp" title="{esc(row.get('trigger'))}">{esc(row.get('trigger'))}</td>
              <td class="clamp muted" title="{esc(reason)}">{esc(reason)}</td>
            </tr>"""
        )
    return "".join(body) or '<tr><td colspan="9" class="empty">暂无标的</td></tr>'


def execution_cards(rows: list[dict[str, Any]], classes: set[str]) -> str:
    cards = []
    selected = [x for x in rows if str(x.get("final_class")) in classes]
    for row in selected:
        cls = str(row.get("final_class"))
        signals = row.get("signals") or {}
        vwap_ok = None
        if signals.get("below_vwap") is True:
            vwap_ok = False
        elif signals.get("below_vwap") is False:
            vwap_ok = True
        flags = "".join(
            [
                flag_chip("站上MA5", "低于MA5", signals.get("above_ma5")),
                flag_chip("站上MA20", "低于MA20", signals.get("above_ma20")),
                flag_chip("站上VWAP", "低于VWAP", vwap_ok),
                flag_chip("量能确认", "量能未确认", signals.get("volume_confirmed")),
                flag_chip("价格偏强", "价格偏弱", signals.get("price_strength_confirmed")),
            ]
        )
        if cls == "A":
            action = f"现在可参与 · 仓位上限 {money_pct(row.get('final_position_max'))}"
            focus_label, focus_value = "买入前失效", row.get("pre_entry")
            secondary_label, secondary_value = "T+1退出", f"高开: {row.get('gap_up')} / 平开: {row.get('flat_open')} / 低开: {row.get('gap_down')}"
        elif cls == "B":
            action = f"等确认后参与 · 触发前仓位 0%"
            focus_label, focus_value = "触发条件", row.get("trigger")
            secondary_label, secondary_value = "不买条件", row.get("no_buy")
        else:
            action = class_label(cls)
            focus_label, focus_value = "原因", " / ".join(row["reasons"][:4]) if row["reasons"] else row.get("trigger")
            secondary_label, secondary_value = "早盘不买", row.get("no_buy")
        cards.append(
            f"""<article class="exec-card {class_css(cls)}">
              <header>
                <div>
                  <div class="card-kicker">{esc(cls)} · {esc(class_label(cls))}</div>
                  <h3>{esc(row.get('name'))}</h3>
                  <span class="mono">{esc(row.get('code'))}</span>
                </div>
                <div class="card-side">
                  <span class="badge {class_css(cls)}">{esc(cls)}</span>
                  <b>{esc(money_pct(row.get('final_position_max')))}</b>
                  <small>仓位上限</small>
                </div>
              </header>
              <div class="card-tags">
                <span>{esc(row.get('sector'))}</span>
                <span>{esc(row.get('direction'))}</span>
                <span>{esc(row.get('rating'))}</span>
                <span>{esc(row.get('entry_profile'))}</span>
                <span class="theme">{esc(row.get('theme'))} · {esc(row.get('theme_state') or '—')}</span>
              </div>
              <div class="flag-row">{flags}</div>
              <dl>
                <div><dt>早盘意图</dt><dd>{esc(row.get('direction'))} / {esc(row.get('rating'))} / {esc(row.get('entry_profile'))} · 锚点 {esc(row.get('anchor'))}</dd></div>
                <div><dt>当前信号</dt><dd>{esc(row.get('signal_text'))}</dd></div>
                <div><dt>操作</dt><dd class="action-line">{esc(action)}</dd></div>
                <div><dt>{esc(focus_label)}</dt><dd>{esc(focus_value)}</dd></div>
                <div><dt>{esc(secondary_label)}</dt><dd>{esc(secondary_value)}</dd></div>
              </dl>
              <footer>
                <b>备注</b>
                <span>{esc(row.get('t_risk') if cls == 'A' else (row.get('transition') or '按机械分类执行'))}</span>
              </footer>
            </article>"""
        )
    if not cards:
        return f'<div class="empty">{" / ".join(sorted(classes))} 类为空</div>'
    return "".join(cards)


def theme_rows(snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return '<tr><td colspan="5" class="empty">无主题确认数据</td></tr>'
    themes = snapshot.get("theme_confirmations")
    if not isinstance(themes, dict) or not themes:
        return '<tr><td colspan="5" class="empty">无主题确认数据</td></tr>'
    rows = []
    for name, item in themes.items():
        if not isinstance(item, dict):
            continue
        state = item.get("theme_state")
        tone = {
            "CONFIRMED": "rise",
            "NARROW": "warn",
            "FADING": "warn",
            "FAILED": "fall",
            "UNKNOWN": "neutral",
        }.get(str(state), "neutral")
        rows.append(
            f"""<tr>
              <td class="strong">{esc(name)}</td>
              <td><span class="badge {tone}">{esc(state)}</span></td>
              <td class="mono">{esc(number(item.get('member_advance_ratio'), 2))}</td>
              <td class="mono">{esc(number(item.get('member_above_vwap_ratio'), 2))}</td>
              <td class="mono">{esc(item.get('valid_member_n'))}/{esc(item.get('expected_member_n'))}</td>
            </tr>"""
        )
    return "".join(rows) or '<tr><td colspan="5" class="empty">无主题确认数据</td></tr>'


def risk_list(decision: dict[str, Any], snapshot: dict[str, Any] | None, counts: dict[str, int]) -> str:
    market = decision.get("market_confirmation") if isinstance(decision.get("market_confirmation"), dict) else {}
    delivery = decision.get("delivery_confirmation") if isinstance(decision.get("delivery_confirmation"), dict) else {}
    portfolio = decision.get("portfolio") if isinstance(decision.get("portfolio"), dict) else {}
    allocation = portfolio.get("allocation") if isinstance(portfolio.get("allocation"), dict) else {}
    limits = allocation.get("limits") if isinstance(allocation.get("limits"), dict) else {}
    items = [
        f"全局动作 {action_label(decision.get('global_action'))}（{decision.get('global_action')}）",
        f"交付状态 {delivery_label(delivery.get('execution_action'))}",
        f"今日可买总仓位 {money_pct(portfolio.get('actionable_exposure'))} / 上限 {money_pct(limits.get('max_new_exposure'))}",
        f"单票上限 {money_pct(limits.get('max_single_stock'))} · 单主题上限 {money_pct(limits.get('max_theme_exposure'))}",
        f"分类分布 A{counts['A']} / B{counts['B']} / C{counts['C']} / D{counts['D']}",
    ]
    for reason in market.get("reasons") or []:
        items.append(f"市场原因：{reason_zh(reason)}")
    for warn in market.get("data_warnings") or []:
        items.append(f"数据告警：{reason_zh(warn)}")
    if isinstance(snapshot, dict):
        for warn in snapshot.get("transition_warnings") or []:
            items.append(f"状态转换：{warn}")
    return "".join(f"<li>{esc(x)}</li>" for x in items)


def memo_bullets(decision: dict[str, Any], rows: list[dict[str, Any]], counts: dict[str, int]) -> str:
    market = decision.get("market_confirmation") if isinstance(decision.get("market_confirmation"), dict) else {}
    a_names = [f"{x['name']}" for x in rows if x.get("final_class") == "A"][:4]
    b_names = [f"{x['name']}" for x in rows if x.get("final_class") == "B"][:4]
    bullets = [
        f"投委会结论：{action_label(decision.get('global_action'))}；实时结构 {regime_label(market.get('regime_confirmed') or market.get('regime_live'))}。",
        f"仓位决议：今日可买总仓位 {money_pct((decision.get('portfolio') or {}).get('actionable_exposure'))}（A类仓位合计）；A类 {counts['A']} 只，B类 {counts['B']} 只。",
    ]
    if a_names:
        bullets.append(f"现在可买：{' / '.join(a_names)}。")
    else:
        bullets.append("现在可买：无。今日没有 A 类指令。")
    if b_names:
        bullets.append(f"等确认再买：{' / '.join(b_names)}；触发前不要下单。")
    else:
        bullets.append("等确认再买：无。")
    bullets.append("纪律：类别与仓位以 decision 为准，不得上调；A 股当日买进不能卖，失效只记 T+1 风险。")
    return "".join(f"<li>{esc(x)}</li>" for x in bullets)


def render(decision: dict[str, Any], snapshot: dict[str, Any] | None) -> str:
    date = str(decision.get("date") or "")
    slot = str(decision.get("snapshot_slot") or "—")
    market = decision.get("market_confirmation") if isinstance(decision.get("market_confirmation"), dict) else {}
    delivery = decision.get("delivery_confirmation") if isinstance(decision.get("delivery_confirmation"), dict) else {}
    portfolio = decision.get("portfolio") if isinstance(decision.get("portfolio"), dict) else {}
    allocation = portfolio.get("allocation") if isinstance(portfolio.get("allocation"), dict) else {}
    limits = allocation.get("limits") if isinstance(allocation.get("limits"), dict) else {}
    rows = merge_rows(decision, snapshot)
    counts = {k: sum(1 for x in rows if x.get("final_class") == k) for k in ("A", "B", "C", "D")}
    total = len(rows)
    exposure = portfolio.get("actionable_exposure") or 0
    regime = regime_label(market.get("regime_confirmed") or market.get("regime_live"))
    action = decision.get("global_action")
    subtitle = (
        f"{regime} · {action_label(action)} · 槽位 {slot} · "
        f"交付 {delivery_label(delivery.get('execution_action'))}"
    )
    reasons = " / ".join(reason_zh(x) for x in (market.get("reasons") or [])[:4]) or "无额外市场原因"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>盘中操作总控台 · {esc(date)} {esc(slot)}</title>
  <style>
    :root{{color-scheme:dark;--bg:#070B10;--soft:#0B1118;--panel:#111923;--panel2:#0E1724;--line:#243244;--text:#E7EDF5;--strong:#FFF;--sub:#91A1B5;--accent:#22D3EE;--blue:#60A5FA;--rise:#FF5C68;--rise2:#FF7A45;--rise-soft:rgba(255,92,104,.14);--fall:#32D583;--fall-soft:rgba(50,213,131,.14);--warn:#FDB022;--warn-soft:rgba(253,176,34,.15);--danger:#F04438;--muted:#34445A}}
    *{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 12% -8%,rgba(34,211,238,.08),transparent 28%),linear-gradient(180deg,#09111a,var(--bg) 28%)}}
    .page{{max-width:1600px;margin:auto;padding:0 28px 48px}}.topbar{{margin:0 -28px 22px;padding:24px 28px;border-bottom:1px solid var(--line);background:linear-gradient(110deg,rgba(7,11,16,.98),rgba(14,28,43,.95) 55%,rgba(7,11,16,.98))}}.topbar-inner{{max-width:1544px;margin:auto;display:flex;justify-content:space-between;gap:24px}}h1,h2,h3,p{{margin:0}}h1{{font-size:28px;letter-spacing:.02em}}.subtitle{{margin-top:7px;color:#a9b8ca}}.meta{{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;max-width:480px}}.meta span{{padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--sub);background:#0a1420;font-size:12px}}
    .card,.panel,.exec-card{{border:1px solid var(--line);border-radius:14px;background:linear-gradient(180deg,rgba(17,25,35,.97),rgba(10,17,26,.97));box-shadow:0 18px 44px rgba(0,0,0,.24)}}
    .cockpit{{display:grid;grid-template-columns:1.15fr 1fr .95fr;gap:13px}}.cockpit-card{{min-height:250px;padding:18px;position:relative;overflow:hidden}}.cockpit-card:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}}
    .label{{color:var(--sub);font-size:11px;letter-spacing:.12em;text-transform:uppercase}}.market-call{{margin:16px 0 8px;font-size:26px;font-weight:800;color:var(--strong)}}.market-tag{{display:inline-flex;padding:4px 9px;border-radius:6px;font-weight:700}}.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}}.index-chip{{padding:4px 8px;border-radius:7px;font-size:12px;font-weight:700;border:1px solid transparent}}.index-chip.up{{color:var(--rise);background:var(--rise-soft);border-color:rgba(255,92,104,.25)}}.index-chip.down{{color:var(--fall);background:var(--fall-soft);border-color:rgba(50,213,131,.25)}}.index-chip.flat{{color:#c7d2e1;background:rgba(145,161,181,.12)}}.market-note{{margin-top:12px;color:#b8c5d5;font-size:12px}}
    .big-number{{font:800 42px/1 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--rise)}}.big-number small{{font:600 14px/1 inherit;color:var(--sub)}}.kpi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:16px}}.kpi-grid div{{padding:10px;border:1px solid var(--line);border-radius:9px;background:#0a1420}}.kpi-grid small{{display:block;color:var(--sub);font-size:11px}}.kpi-grid b{{display:block;margin-top:3px;color:var(--strong)}}
    .mix-box{{margin-top:12px}}.mix-total b{{display:block;font:800 40px/1 ui-monospace,SFMono-Regular,monospace}}.mix-total span{{color:var(--sub);font-size:12px}}.mix-track{{display:flex;height:12px;margin:16px 0 10px;border-radius:8px;overflow:hidden;background:#233143}}.mix-track i{{height:100%}}.mix-legend{{display:grid;grid-template-columns:1fr 1fr;gap:6px;color:var(--sub);font-size:12px}}.mix-legend span{{display:flex;gap:5px}}
    .memo{{margin-top:14px;padding:16px 18px}}.memo h2{{font-size:15px;margin-bottom:8px}}.memo h2:before{{content:"";display:inline-block;width:4px;height:14px;margin-right:8px;vertical-align:-2px;border-radius:2px;background:var(--accent)}}.memo ol,.memo ul,.risk-box ul{{margin:0;padding-left:18px;color:#cbd6e3}}.memo li,.risk-box li{{margin:6px 0}}
    .section-head{{display:flex;justify-content:space-between;align-items:end;margin:28px 0 10px}}.section-head h2{{font-size:19px}}.section-head h2:before{{content:"";display:inline-block;width:4px;height:17px;margin-right:8px;vertical-align:-2px;border-radius:2px;background:var(--accent)}}.section-head p{{color:var(--sub);font-size:12px}}
    .panel{{overflow:hidden}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:980px}}th{{position:sticky;top:0;z-index:1;color:var(--sub);background:rgba(10,17,26,.97);font-weight:600}}th,td{{padding:11px 10px;border-bottom:1px solid rgba(36,50,68,.72);text-align:left;font-size:13px;vertical-align:top}}tbody tr:hover td{{background:rgba(96,165,250,.05)}}.strong{{font-weight:700;color:var(--strong)}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#d8f3ff;white-space:nowrap}}.muted{{color:#9aabbd}}.clamp{{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.up{{color:var(--rise)}}.down{{color:var(--fall)}}
    .badge{{display:inline-flex;align-items:center;justify-content:center;min-height:24px;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}}.cls-a,.rise{{color:var(--rise);background:var(--rise-soft)}}.cls-b,.warn{{color:var(--warn);background:var(--warn-soft)}}.cls-c,.blue{{color:var(--blue);background:rgba(96,165,250,.13)}}.cls-d,.neutral{{color:#c7d2e1;background:rgba(145,161,181,.14)}}.fall{{color:var(--fall);background:var(--fall-soft)}}.market-tag.rise,.market-tag.warn,.market-tag.blue,.market-tag.fall,.market-tag.neutral{{border:1px solid transparent}}
    .exec-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.exec-card{{padding:16px;display:flex;flex-direction:column;min-height:390px;border-top:2px solid transparent}}.exec-card.cls-a{{border-top-color:var(--rise)}}.exec-card.cls-b{{border-top-color:var(--warn)}}.exec-card.cls-c{{border-top-color:var(--blue)}}.exec-card.cls-d{{border-top-color:#64748b}}
    .exec-card header{{display:flex;justify-content:space-between;gap:12px}}.card-kicker{{color:var(--sub);font-size:11px;letter-spacing:.08em}}.exec-card h3{{font-size:18px;margin-top:4px}}.card-side{{text-align:right}}.card-side b{{display:block;margin-top:8px;font:800 18px/1 ui-monospace,SFMono-Regular,monospace;color:var(--rise)}}.card-side small{{color:var(--sub);font-size:11px}}
    .card-tags{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 8px}}.card-tags span{{padding:3px 7px;border-radius:999px;background:#15202c;color:#c9d6e5;font-size:11px}}.card-tags .theme{{color:var(--accent)}}
    .flag-row{{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px}}.flag{{padding:2px 7px;border-radius:5px;font-size:11px;font-weight:700}}.flag.ok{{color:var(--rise);background:var(--rise-soft)}}.flag.bad{{color:var(--fall);background:var(--fall-soft)}}.flag.mute{{color:#9aabbd;background:rgba(145,161,181,.12)}}
    dl{{margin:0}}dl div{{padding:8px 0;border-top:1px solid rgba(36,50,68,.7)}}dt{{color:var(--sub);font-size:11px}}dd{{margin:3px 0 0;color:#e4ebf4}}.action-line{{color:#fff;font-weight:700}}.exec-card footer{{margin-top:auto;padding-top:10px;border-top:1px solid var(--line);display:grid;gap:3px}}.exec-card footer b{{color:var(--sub);font-size:11px}}.exec-card footer span{{color:#c9d4e1;font-size:12px}}
    .split{{display:grid;grid-template-columns:1.1fr .9fr;gap:13px}}.risk-box{{padding:16px}}.risk-box h3{{margin-bottom:10px;font-size:15px}}.risk-kpis{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}.risk-kpis div{{padding:10px;border:1px solid var(--line);border-radius:9px;background:#0a1420}}.risk-kpis small{{display:block;color:var(--sub)}}.risk-kpis b{{color:var(--warn)}}
    .footer{{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);text-align:center;color:var(--sub);font-size:12px}}.empty{{padding:24px;text-align:center;color:var(--sub)}}
    @media(max-width:1200px){{.cockpit,.exec-grid,.split{{grid-template-columns:1fr 1fr}}.cockpit-card:first-child{{grid-column:1/-1}}}}
    @media(max-width:760px){{.page{{padding:0 14px 30px}}.topbar{{margin:0 -14px 16px;padding:18px 14px}}.topbar-inner{{display:block}}.meta{{justify-content:flex-start;margin-top:12px}}.cockpit,.exec-grid,.split,.kpi-grid,.risk-kpis{{grid-template-columns:1fr}}.cockpit-card:first-child{{grid-column:auto}}h1{{font-size:24px}}}}
  </style>
</head>
<body>
<div class="page">
  <header class="topbar"><div class="topbar-inner">
    <div>
      <h1>盘中操作总控台</h1>
      <p class="subtitle">{esc(subtitle)}</p>
    </div>
    <div class="meta">
      <span>日期 {esc(date)}</span>
      <span>槽位 {esc(slot)}</span>
      <span>生成 {esc(generated_time(decision.get('generated_at')))}</span>
      <span>Bloomberg × 投委会 × 量化看板</span>
    </div>
  </div></header>

  <section class="cockpit">
    <article class="card cockpit-card">
      <div class="label">市场确认 / Market Regime</div>
      <div class="market-call">{esc(regime)}</div>
      <span class="market-tag {action_css(action)}">{esc(action_label(action))} · prior {esc(regime_label(market.get('regime_prior')))} → live {esc(regime_label(market.get('regime_live')))}</span>
      <div class="chips">{render_index_chips(market)}</div>
      <p class="market-note">{esc(reasons)}</p>
    </article>
    <article class="card cockpit-card">
      <div class="label">执行决议 / Portfolio Call</div>
      <div class="big-number">{esc(money_pct(exposure))}<small> 今日可买总仓位</small></div>
      <div class="kpi-grid">
        <div><small>A 可参与</small><b>{counts['A']} 只</b></div>
        <div><small>B 等确认</small><b>{counts['B']} 只</b></div>
        <div><small>C 只观察</small><b>{counts['C']} 只</b></div>
        <div><small>D 放弃</small><b>{counts['D']} 只</b></div>
      </div>
    </article>
    <article class="card cockpit-card">
      <div class="label">分类分布 / Class Mix</div>
      {render_class_mix(counts, total)}
      <p class="market-note">交付：{esc(delivery_label(delivery.get('execution_action')))} · 单票上限 {esc(money_pct(limits.get('max_single_stock')))}</p>
    </article>
  </section>

  <section class="card memo">
    <h2>投委会纪要 / Investment Committee Memo</h2>
    <ol>{memo_bullets(decision, rows, counts)}</ol>
  </section>

  <div class="section-head"><h2>一句话操作总表（{total}只）</h2><p>以 decision 合同 final_class / final_position_max 为准</p></div>
  <section class="panel"><div class="table-wrap"><table>
    <thead><tr>
      <th>类别</th><th>代码</th><th>名称</th><th>板块</th><th>早盘</th><th>现价</th><th>仓位上限</th><th>操作/触发</th><th>原因</th>
    </tr></thead>
    <tbody>{overview_rows(rows)}</tbody>
  </table></div></section>

  <div class="section-head"><h2>A / B 执行卡片</h2><p>标签色：红=条件满足 · 绿=条件不满足 · 灰=数据未知（A股红涨绿跌习惯）</p></div>
  <section class="exec-grid">{execution_cards(rows, {"A", "B"})}</section>

  <div class="section-head"><h2>C / D 观察与回避</h2><p>不形成新买入；仅保留原因与早盘约束</p></div>
  <section class="exec-grid">{execution_cards(rows, {"C", "D"})}</section>

  <div class="section-head"><h2>主题确认雷达</h2><p>来自 snapshot.theme_confirmations</p></div>
  <section class="panel"><div class="table-wrap"><table>
    <thead><tr><th>主题</th><th>状态</th><th>上涨占比</th><th>站上VWAP占比</th><th>有效成员</th></tr></thead>
    <tbody>{theme_rows(snapshot)}</tbody>
  </table></div></section>

  <div class="section-head"><h2>风控与交付</h2><p>仅展示 JSON 可观察事实</p></div>
  <section class="split">
    <article class="card risk-box">
      <h3>风险清单</h3>
      <ul>{risk_list(decision, snapshot, counts)}</ul>
    </article>
    <article class="card risk-box">
      <h3>组合限额</h3>
      <div class="risk-kpis">
        <div><small>今日新开仓上限</small><b>{esc(money_pct(limits.get('max_new_exposure')))}</b></div>
        <div><small>单主题仓位上限</small><b>{esc(money_pct(limits.get('max_theme_exposure')))}</b></div>
        <div><small>单只股票上限</small><b>{esc(money_pct(limits.get('max_single_stock')))}</b></div>
        <div><small>同主题最多只数</small><b>{esc(limits.get('max_correlated_names'))}</b></div>
      </div>
      <ul>
        <li>A 股新开仓当日不可卖出；失效条件仅用于买入前撤单与 T+1 风险标记。</li>
        <li>禁止上调 final_class 超过 max_allowed_class；禁止超过 final_position_max。</li>
        <li>本页为中文阅读层，不构成投资建议，不下单。</li>
      </ul>
    </article>
  </section>

  <footer class="footer">数据源：operation_decision.json / operation_snapshot.json · Schema {esc(decision.get('schema_version'))} · 生成时间 {esc(decision.get('generated_at'))} · 风格：Bloomberg Terminal × 投委会 Memo × A股量化策略看板</footer>
</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render operation_guide.html from decision/snapshot")
    parser.add_argument("--date", required=True)
    parser.add_argument("--decision")
    parser.add_argument("--snapshot")
    parser.add_argument("--output")
    args = parser.parse_args()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    root = workspace_root()
    odir = root / "operation" / args.date
    manifest = latest_run_manifest(odir)
    if args.decision:
        decision_path = Path(args.decision)
    elif manifest and isinstance(manifest.get("decision"), str):
        decision_path = odir / manifest["decision"]
    else:
        decision_path = odir / "operation_decision.latest.json"
    if not decision_path.exists():
        for candidate in sorted(odir.glob("operation_decision_*.json"), reverse=True):
            decision_path = candidate
            break
    snapshot_path = Path(args.snapshot) if args.snapshot else None
    if snapshot_path is None:
        if manifest and isinstance(manifest.get("snapshot"), str):
            snapshot_path = odir / manifest["snapshot"]
        else:
            decision = read_json(decision_path)
            source = decision.get("source_snapshot") if isinstance(decision, dict) else None
            if source:
                snapshot_path = Path(source)
                if not snapshot_path.is_absolute():
                    snapshot_path = root / snapshot_path
            else:
                snapshot_path = odir / "operation_snapshot.latest.json"

    if manifest and not args.decision and not args.snapshot:
        for key, path in (("decision_sha256", decision_path), ("snapshot_sha256", snapshot_path)):
            expected = manifest.get(key)
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None
            if expected != actual:
                print(f"[ERROR] run manifest {key} mismatch", file=sys.stderr)
                return 1

    decision = read_json(decision_path)
    if not isinstance(decision, dict):
        print(f"[ERROR] missing or invalid decision: {decision_path}", file=sys.stderr)
        return 1
    if decision.get("schema_version") != "intraday_operation_decision.v1":
        print("[ERROR] decision schema must be intraday_operation_decision.v1", file=sys.stderr)
        return 1
    if decision.get("date") != args.date:
        print(f"[ERROR] decision date must be {args.date}", file=sys.stderr)
        return 1

    snapshot = read_json(snapshot_path) if snapshot_path else None
    if snapshot is not None and not isinstance(snapshot, dict):
        print(f"[ERROR] invalid snapshot: {snapshot_path}", file=sys.stderr)
        return 1
    if isinstance(snapshot, dict):
        if decision.get("generated_at") != snapshot.get("generated_at"):
            print("[ERROR] decision and snapshot generated_at differ", file=sys.stderr)
            return 1
        expected_hash = decision.get("source_snapshot_sha256")
        actual_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest() if snapshot_path else None
        if expected_hash != actual_hash:
            print("[ERROR] decision source snapshot hash mismatch", file=sys.stderr)
            return 1

    output = Path(args.output) if args.output else odir / "operation_guide.html"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(decision, snapshot if isinstance(snapshot, dict) else None), encoding="utf-8", newline="\n")
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
