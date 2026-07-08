#!/usr/bin/env python3
"""Render predict/{date}/daily_report.html from daily JSON contracts."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def predict_dir(date: str) -> Path:
    return workspace_root() / "predict" / date


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def esc(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value)
    if text in {"", "None", "null"}:
        return "-"
    return html.escape(text, quote=True)


def num(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return esc(value)
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return esc(value)


def value_at(obj: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def score_value(candidate: dict[str, Any], key: str) -> Any:
    return value_at(candidate, "scores", key, "value")


def score_conf(candidate: dict[str, Any], key: str) -> Any:
    return value_at(candidate, "scores", key, "confidence")


def by_code(items: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                result[item["code"]] = item
    return result


def list_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value) if value is not None else "-"


def css_class_token(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "none")).strip("-").lower()
    return text or "none"


def direction_class(value: Any) -> str:
    return {
        "看多": "bull",
        "偏多": "bullish",
        "中性": "neutral",
        "看空": "bear",
    }.get(str(value), "none")


def status_label(value: Any) -> str:
    return {
        "tradeable": "可交易",
        "watch": "观察",
        "discarded": "剔除",
    }.get(str(value or "tradeable"), str(value or "可交易"))


def theme_items(themes_doc: dict[str, Any] | None, strategy_view: dict[str, Any] | None) -> list[dict[str, Any]]:
    if isinstance(themes_doc, dict) and isinstance(themes_doc.get("themes"), list):
        return [item for item in themes_doc["themes"] if isinstance(item, dict)]
    if isinstance(strategy_view, dict) and isinstance(strategy_view.get("themes"), list):
        return [
            {
                "rank": item.get("rank"),
                "name": item.get("name"),
                "status": "tradeable",
                "heat": item.get("final_heat"),
                "confidence": None,
                "direction": None,
                "reason": None,
                "evidence": None,
            }
            for item in strategy_view["themes"]
            if isinstance(item, dict)
        ]
    return []


def market_tone(market: dict[str, Any]) -> str:
    text = f"{market.get('regime_hint') or ''} {market.get('notes') or ''}"
    if any(token in text for token in ("bear", "weak", "risk-off", "下跌", "走弱", "承压")):
        return "bad"
    if any(token in text for token in ("strong", "bull", "risk-on", "强", "走强", "偏强")):
        return "good"
    return "warn"


def regime_label(value: Any) -> str:
    return {
        "strong-sector": "强主题结构",
        "balanced": "均衡震荡",
        "weak-market": "弱势防守",
        "risk-off": "风险收缩",
        "risk-on": "风险偏好",
    }.get(str(value or ""), str(value or "未确认"))


def display_market_note(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "strong-sector": "强主题结构",
        "balanced": "均衡震荡",
        "weak-market": "弱势防守",
        "risk-off": "风险收缩",
        "risk-on": "风险偏好",
    }
    for raw, label in replacements.items():
        text = text.replace(raw, label)
    return text


def render_market_chips(notes: Any) -> str:
    text = str(notes or "")
    matches = re.findall(r"([A-Za-z0-9\u4e00-\u9fff]+)\s*([+-]\d+(?:\.\d+)?%)", text)
    chips = []
    for name, change in matches[:6]:
        cls = "pos" if change.startswith("+") else "neg"
        chips.append(f'<span class="market-chip {cls}">{esc(name)} {esc(change)}</span>')
    return "".join(chips) or '<span class="muted">暂无指数涨跌拆分</span>'


def render_theme_lens(themes_doc: dict[str, Any] | None, strategy_view: dict[str, Any] | None) -> str:
    colors = ["#ff4d4f", "#ff7a45", "#fdb022", "#f97316", "#f43f5e", "#a78bfa"]
    items = sorted(theme_items(themes_doc, strategy_view), key=lambda item: parse_heat(item), reverse=True)[:6]
    if not items:
        return '<div class="muted">暂无主题热度数据</div>'
    total = sum(parse_heat(item) for item in items) or 1
    start = 0.0
    segments = []
    legend = []
    max_heat = max(parse_heat(item) for item in items) or 1
    for idx, item in enumerate(items):
        heat = parse_heat(item)
        end = start + (heat / total) * 360
        color = colors[idx % len(colors)]
        segments.append(f"{color} {start:.1f}deg {end:.1f}deg")
        width = max(6, min(100, heat / max_heat * 100))
        legend.append(
            f"""
            <div class="theme-rank-row">
              <span class="theme-dot" style="background:{color}"></span>
              <span class="theme-name">{esc(item.get("name"))}</span>
              <span class="theme-bar"><i style="width:{width:.1f}%; background:{color}"></i></span>
              <span class="theme-heat">{num(heat)}</span>
            </div>
            """
        )
        start = end
    gradient = ", ".join(segments)
    leader = items[0]
    return f"""
      <div class="theme-lens">
        <div class="donut" style="background:conic-gradient({gradient})">
          <div><b>{num(parse_heat(leader), 0)}</b><span>{esc(leader.get("name"))}</span></div>
        </div>
        <div class="theme-ranks">{"".join(legend)}</div>
      </div>
    """


def parse_heat(item: dict[str, Any]) -> float:
    value = parse_float(item.get("heat") if item.get("heat") is not None else item.get("final_heat"))
    return value if value is not None else 0.0


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_direction_mix(directions: dict[str, int], stocks: list[dict[str, Any]]) -> str:
    total = max(1, sum(directions.values()))
    segments = [
        ("看多", "bull", "#ff4d4f"),
        ("偏多", "bullish", "#ff7a45"),
        ("中性", "neutral", "#91a1b5"),
        ("看空", "bear", "#32d583"),
    ]
    bars = []
    labels = []
    for label, cls, color in segments:
        count = directions.get(label, 0)
        width = count / total * 100
        if count:
            bars.append(f'<i class="{cls}" style="width:{width:.1f}%; background:{color}"></i>')
        labels.append(f'<span><b style="color:{color}">{count}</b>{label}</span>')
    active = sum(1 for stock in stocks if float(stock.get("position_budget") or 0) > 0)
    return f"""
      <div class="direction-mix">
        <div class="direction-total"><b>{len(stocks)}</b><span>策略标的</span><em>{active} 只计划参与</em></div>
        <div class="direction-track">{"".join(bars) or '<i style="width:100%; background:#283648"></i>'}</div>
        <div class="direction-labels">{"".join(labels)}</div>
      </div>
    """


def read_news_refs(path: Path, refs: set[str]) -> dict[str, str]:
    if not path.exists() or not refs:
        return {}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    result: dict[str, str] = {}
    for ref in refs:
        match = re.search(r"#(\d+)$", ref)
        if not match:
            continue
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(lines):
            text = lines[idx].strip()
            if text:
                result[ref] = text[:240]
    return result


def card(title: str, value: str, note: str = "") -> str:
    return f"""
      <section class="metric">
        <div class="metric-title">{esc(title)}</div>
        <div class="metric-value">{esc(value)}</div>
        <div class="metric-note">{esc(note)}</div>
      </section>
    """


def render_theme_cards(themes_doc: dict[str, Any] | None, strategy_view: dict[str, Any] | None) -> str:
    themes = theme_items(themes_doc, strategy_view)
    rows = []
    for theme in sorted(themes, key=lambda x: (x.get("status") != "tradeable", x.get("rank") or 999)):
        rows.append(
            f"""
            <tr>
              <td>{esc(theme.get("rank"))}</td>
              <td class="strong">{esc(theme.get("name"))}</td>
              <td><span class="pill status-{css_class_token(theme.get("status"))}">{esc(status_label(theme.get("status")))}</span></td>
              <td>{num(theme.get("heat") or theme.get("final_heat"))}</td>
              <td>{num(theme.get("confidence"), 0)}</td>
              <td>{esc(theme.get("direction"))}</td>
              <td>{esc(theme.get("reason"))}</td>
              <td>{esc(theme.get("evidence"))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="8" class="muted">暂无主题数据</td></tr>'


def render_stock_rows(strategy: dict[str, Any], strategy_view: dict[str, Any] | None) -> str:
    candidates = by_code(strategy_view.get("candidates") if isinstance(strategy_view, dict) else [])
    rows = []
    for stock in strategy.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = stock.get("code")
        cand = candidates.get(code, {})
        direction = stock.get("direction")
        risk = value_at(cand, "risk_type")
        profile = stock.get("profile") if isinstance(stock.get("profile"), dict) else {}
        rows.append(
            f"""
            <tr>
              <td class="code">{esc(code)}</td>
              <td class="strong">{esc(stock.get("name"))}</td>
              <td>{esc(stock.get("sector"))}</td>
              <td><span class="pill direction-{direction_class(direction)}">{esc(direction)}</span></td>
              <td>{esc(stock.get("rating"))}</td>
              <td>{pct(stock.get("position_budget"))}</td>
              <td>{num(score_value(cand, "composite"))}<span class="sub"> / {num(score_conf(cand, "composite"), 0)}</span></td>
              <td>{num(score_value(cand, "theme_heat"))}</td>
              <td>{num(score_value(cand, "news_impact"))}</td>
              <td>{num(score_value(cand, "tech"))}</td>
              <td>{esc(stock.get("entry_profile"))}</td>
              <td>{esc(stock.get("anchor"))}</td>
              <td>{esc(stock.get("entry_trigger"))}</td>
              <td>{esc(stock.get("no_buy_condition"))}</td>
              <td>{esc(profile.get("invalidation"))}</td>
              <td>{esc(list_text(stock.get("rules_applied")))}</td>
              <td>{esc(list_text(risk))}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="17" class="muted">暂无策略股票</td></tr>'


def render_stock_details(strategy: dict[str, Any], strategy_view: dict[str, Any] | None) -> str:
    candidates = by_code(strategy_view.get("candidates") if isinstance(strategy_view, dict) else [])
    blocks = []
    for stock in strategy.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = stock.get("code")
        cand = candidates.get(code, {})
        profile = stock.get("profile") if isinstance(stock.get("profile"), dict) else {}
        reasoning = stock.get("reasoning") if isinstance(stock.get("reasoning"), dict) else {}
        inputs = cand.get("strategy_inputs") if isinstance(cand.get("strategy_inputs"), dict) else {}
        pattern = cand.get("pattern") if isinstance(cand.get("pattern"), dict) else {}
        pattern_bits = []
        for key in ("heat", "leader", "auction", "rotation", "volume"):
            item = pattern.get(key) if isinstance(pattern.get(key), dict) else {}
            pattern_bits.append(f"{key}:{item.get('state', '-')}/{item.get('confidence', '-')}")
        blocks.append(
            f"""
            <details class="stock-detail">
              <summary><span class="code">{esc(code)}</span> {esc(stock.get("name"))} · {esc(stock.get("direction"))} · {esc(stock.get("entry_profile"))}</summary>
              <div class="detail-grid">
                <section>
                  <h4>推理链路</h4>
                  <p><b>方向路径：</b>{esc(reasoning.get("direction_path"))}</p>
                  <p><b>风险判断：</b>{esc(reasoning.get("risk"))}</p>
                  <p><b>复核结论：</b>{esc(reasoning.get("reread"))}</p>
                  <p><b>覆盖项：</b>{esc(reasoning.get("override"))}</p>
                </section>
                <section>
                  <h4>感知信号</h4>
                  <p><b>盘口结构：</b>{esc("; ".join(pattern_bits))}</p>
                  <p><b>重大事件：</b>{esc(value_at(cand, "major_event", "polarity"))}/{esc(value_at(cand, "major_event", "confidence"))}</p>
                  <p><b>异常提示：</b>{esc(cand.get("anomaly"))}</p>
                  <p><b>新闻引用：</b>{esc(cand.get("news_link"))}</p>
                </section>
                <section>
                  <h4>策略输入</h4>
                  <p>现价 {num(inputs.get("price"), 2)} · MA5 {num(inputs.get("ma5"), 2)} · MA20 {num(inputs.get("ma20"), 2)}</p>
                  <p>ATR {num(inputs.get("atr"), 2)} · ATR% {num(inputs.get("atr_pct"), 2, "%")} · High20 {num(inputs.get("high20"), 2)} · Low20 {num(inputs.get("low20"), 2)}</p>
                </section>
                <section>
                  <h4>交易画像</h4>
                  <p>{esc(stock.get("profile_trace"))}</p>
                  <p><b>打法：</b>{esc(profile.get("playbook"))} · <b>止损：</b>{esc(profile.get("stop_policy"))} · <b>窗口：</b>{esc(profile.get("entry_window"))}</p>
                  <p><b>备注：</b>{esc(profile.get("note"))}</p>
                </section>
              </div>
            </details>
            """
        )
    return "\n".join(blocks) or '<p class="muted">暂无单股详情</p>'


def render_pool_rows(items: Any, columns: list[tuple[str, str]]) -> str:
    if not isinstance(items, list) or not items:
        return f'<tr><td colspan="{len(columns)}" class="muted">暂无数据</td></tr>'
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cells = "".join(f"<td>{esc(item.get(key))}</td>" for key, _ in columns)
        rows.append(f"<tr>{cells}</tr>")
    return "\n".join(rows) or f'<tr><td colspan="{len(columns)}" class="muted">暂无数据</td></tr>'


def render_report(date: str, strategy: dict[str, Any], strategy_view: dict[str, Any] | None, mapper: dict[str, Any] | None, themes: dict[str, Any] | None, news_path: Path) -> str:
    market = strategy.get("market") if isinstance(strategy.get("market"), dict) else {}
    stocks = [s for s in strategy.get("stocks", []) if isinstance(s, dict)]
    directions = {name: sum(1 for s in stocks if s.get("direction") == name) for name in ("看多", "偏多", "中性", "看空")}
    dominant = value_at(strategy_view or {}, "market_state", "dominant_themes") or []
    dominant_text = " / ".join(f"{item.get('name')} {num(item.get('heat'))}" for item in dominant if isinstance(item, dict))
    refs = {s.get("news_link") for s in (strategy_view or {}).get("candidates", []) if isinstance(s, dict) and s.get("news_link")}
    news_refs = read_news_refs(news_path, {str(r) for r in refs})
    mapper = mapper if isinstance(mapper, dict) else {}
    generated = esc(strategy.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    tone = market_tone(market)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(date)} 每日交易报告</title>
  <style>
    :root {{ color-scheme: dark; --bg:#080d12; --panel:#111923; --panel-2:#151f2b; --ink:#e7edf5; --muted:#91a1b5; --line:#283648; --line-soft:#1d2a38; --accent:#22d3ee; --good:#32d583; --warn:#fdb022; --bad:#ff6b6b; --blue:#60a5fa; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", Arial, sans-serif; background:linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(180deg, #0a1017 0%, var(--bg) 52%, #070b10 100%); background-size:32px 32px, 32px 32px, auto; color:var(--ink); }}
    header {{ padding:30px 32px 20px; background:linear-gradient(135deg, rgba(13,22,32,.96), rgba(9,16,24,.92)); border-bottom:1px solid var(--line); box-shadow:0 18px 55px rgba(0,0,0,.32); }}
    header h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; color:#f8fbff; }}
    header p {{ margin:0; color:#b8c5d6; }}
    main {{ padding:22px 32px 40px; }}
    h2 {{ margin:28px 0 12px; font-size:20px; color:#f4f8ff; }}
    h2::before {{ content:""; display:inline-block; width:7px; height:18px; margin-right:10px; vertical-align:-3px; border-radius:2px; background:linear-gradient(var(--accent), var(--blue)); box-shadow:0 0 18px rgba(34,211,238,.55); }}
    h3 {{ margin:20px 0 10px; font-size:16px; }}
    .top-grid {{ display:grid; grid-template-columns: minmax(260px, 1.05fr) minmax(340px, 1.55fr) minmax(260px, .95fr); gap:12px; align-items:stretch; }}
    .top-card, .panel, details {{ background:rgba(17,25,35,.92); border:1px solid var(--line); border-radius:8px; box-shadow:0 0 0 1px rgba(34,211,238,.04), 0 16px 42px rgba(0,0,0,.24); }}
    .top-card {{ padding:16px; min-height:178px; position:relative; overflow:hidden; }}
    .top-card::after {{ content:""; position:absolute; left:0; right:0; top:0; height:2px; background:linear-gradient(90deg, var(--accent), transparent); opacity:.75; }}
    .top-label {{ color:var(--muted); font-size:12px; margin-bottom:10px; }}
    .market-state {{ display:flex; align-items:center; gap:14px; margin-bottom:12px; }}
    .state-orb {{ width:46px; height:46px; border-radius:50%; border:1px solid rgba(255,255,255,.18); box-shadow:0 0 28px rgba(34,211,238,.24); }}
    .tone-good .state-orb {{ background:radial-gradient(circle, rgba(255,107,107,.95), rgba(255,107,107,.18) 64%, transparent 66%); box-shadow:0 0 34px rgba(255,107,107,.34); }}
    .tone-warn .state-orb {{ background:radial-gradient(circle, rgba(253,176,34,.95), rgba(253,176,34,.18) 64%, transparent 66%); box-shadow:0 0 34px rgba(253,176,34,.28); }}
    .tone-bad .state-orb {{ background:radial-gradient(circle, rgba(50,213,131,.95), rgba(50,213,131,.18) 64%, transparent 66%); box-shadow:0 0 34px rgba(50,213,131,.28); }}
    .state-main {{ font-size:25px; font-weight:800; color:#fff; line-height:1.1; }}
    .state-sub {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .market-chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }}
    .market-chip {{ display:inline-flex; align-items:center; min-height:24px; padding:3px 8px; border-radius:999px; font-size:12px; border:1px solid rgba(255,255,255,.1); background:#1d2939; }}
    .market-chip.pos {{ color:var(--bad); border-color:rgba(255,107,107,.3); background:rgba(255,107,107,.1); }}
    .market-chip.neg {{ color:var(--good); border-color:rgba(50,213,131,.3); background:rgba(50,213,131,.1); }}
    .market-note {{ color:#b8c5d6; font-size:13px; line-height:1.48; margin:0; }}
    .theme-lens {{ display:grid; grid-template-columns:150px minmax(0, 1fr); gap:16px; align-items:center; }}
    .donut {{ width:142px; height:142px; border-radius:50%; display:grid; place-items:center; box-shadow:0 0 28px rgba(34,211,238,.16); }}
    .donut > div {{ width:92px; height:92px; border-radius:50%; display:grid; place-items:center; align-content:center; padding:8px; text-align:center; background:#101923; border:1px solid var(--line); }}
    .donut b {{ font-size:26px; color:#fff; line-height:1; }}
    .donut span {{ margin-top:6px; color:var(--muted); font-size:12px; line-height:1.25; }}
    .theme-ranks {{ display:grid; gap:8px; }}
    .theme-rank-row {{ display:grid; grid-template-columns:10px minmax(72px, 96px) minmax(80px, 1fr) 34px; gap:8px; align-items:center; font-size:12px; }}
    .theme-dot {{ width:8px; height:8px; border-radius:50%; box-shadow:0 0 10px currentColor; }}
    .theme-name {{ color:#dbe4f0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .theme-bar {{ height:7px; border-radius:999px; overflow:hidden; background:#233143; }}
    .theme-bar i {{ display:block; height:100%; border-radius:999px; }}
    .theme-heat {{ color:#f8fbff; text-align:right; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .direction-mix {{ display:grid; align-content:center; gap:14px; min-height:128px; }}
    .direction-total b {{ display:block; font-size:42px; line-height:1; color:#fff; }}
    .direction-total span {{ color:#dbe4f0; font-weight:700; }}
    .direction-total em {{ display:block; color:var(--muted); font-style:normal; font-size:12px; margin-top:5px; }}
    .direction-track {{ display:flex; height:16px; overflow:hidden; border-radius:999px; background:#233143; border:1px solid rgba(255,255,255,.08); }}
    .direction-track i {{ display:block; height:100%; }}
    .direction-labels {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; color:var(--muted); font-size:12px; }}
    .direction-labels span {{ display:flex; gap:5px; align-items:baseline; }}
    .panel {{ padding:14px; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:960px; }}
    th, td {{ border-bottom:1px solid var(--line-soft); padding:9px 8px; text-align:left; vertical-align:top; font-size:13px; }}
    th {{ color:#cdd8e6; background:#182332; position:sticky; top:0; }}
    td {{ color:#dbe4f0; }}
    tr:hover td {{ background:rgba(34,211,238,.055); }}
    .strong {{ font-weight:700; }}
    .code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space:nowrap; color:#d8f3ff; }}
    .muted, .sub {{ color:var(--muted); }}
    .pill {{ display:inline-block; padding:3px 8px; border-radius:999px; font-size:12px; font-weight:700; background:#1d2939; color:#d7e5f5; border:1px solid rgba(255,255,255,.1); white-space:nowrap; }}
    .direction-bull {{ background:rgba(255,107,107,.13); color:var(--bad); border-color:rgba(255,107,107,.38); }}
    .direction-bullish {{ background:rgba(255,122,69,.14); color:#ffb199; border-color:rgba(255,122,69,.38); }}
    .direction-neutral {{ background:rgba(145,161,181,.14); color:#c7d2e1; }}
    .direction-bear {{ background:rgba(50,213,131,.13); color:var(--good); border-color:rgba(50,213,131,.34); }}
    .status-tradeable {{ background:rgba(255,107,107,.13); color:var(--bad); border-color:rgba(255,107,107,.38); }}
    .status-watch {{ background:rgba(253,176,34,.13); color:var(--warn); border-color:rgba(253,176,34,.36); }}
    .status-discarded {{ background:rgba(50,213,131,.13); color:var(--good); border-color:rgba(50,213,131,.34); }}
    details {{ margin:10px 0; padding:0; }}
    summary {{ cursor:pointer; padding:12px 14px; font-weight:700; color:#f3f7fd; }}
    .detail-grid {{ display:grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap:12px; padding:0 14px 14px; }}
    .detail-grid section {{ border-top:1px solid var(--line); padding-top:10px; }}
    .detail-grid h4 {{ margin:0 0 8px; color:#c9f7ff; }}
    .detail-grid p {{ margin:7px 0; color:#cbd7e6; line-height:1.45; }}
    .news-list {{ margin:0; padding-left:18px; }}
    .news-list li {{ margin:8px 0; line-height:1.45; }}
    @media (max-width: 1100px) {{ .top-grid {{ grid-template-columns:1fr; }} .theme-lens {{ grid-template-columns:150px minmax(0, 1fr); }} }}
    @media (max-width: 900px) {{ main, header {{ padding-left:16px; padding-right:16px; }} .detail-grid {{ grid-template-columns:1fr; }} }}
    @media (max-width: 560px) {{ .theme-lens {{ grid-template-columns:1fr; }} .donut {{ margin:auto; }} .theme-rank-row {{ grid-template-columns:10px minmax(72px, 1fr) minmax(72px, 1fr) 34px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>每日交易报告 · {esc(date)}</h1>
    <p>生成时间：{generated} · 数据源：strategy.json / mapper.strategy_view.json / mapper.json · 本页面仅作为中文阅读层</p>
  </header>
  <main>
    <section class="top-grid">
      <section class="top-card tone-{tone}">
        <div class="top-label">市场状态</div>
        <div class="market-state">
          <div class="state-orb"></div>
          <div>
            <div class="state-main">{esc(regime_label(market.get("regime_hint")))}</div>
            <div class="state-sub">{esc(dominant_text or "主线未确认")}</div>
          </div>
        </div>
        <div class="market-chips">{render_market_chips(market.get("notes"))}</div>
        <p class="market-note">{esc(display_market_note(market.get("notes")))}</p>
      </section>
      <section class="top-card">
        <div class="top-label">主题热度分布</div>
        {render_theme_lens(themes, strategy_view)}
      </section>
      <section class="top-card">
        <div class="top-label">策略方向分布</div>
        {render_direction_mix(directions, stocks)}
      </section>
    </section>

    <h2>主题热力图</h2>
    <section class="panel">
      <table>
        <thead><tr><th>序号</th><th>主题</th><th>状态</th><th>热度</th><th>置信</th><th>方向</th><th>理由</th><th>证据</th></tr></thead>
        <tbody>{render_theme_cards(themes, strategy_view)}</tbody>
      </table>
    </section>

    <h2>策略总表</h2>
    <section class="panel">
      <table>
        <thead>
          <tr><th>代码</th><th>名称</th><th>板块</th><th>方向</th><th>评级</th><th>仓位</th><th>综合/置信</th><th>主题热度</th><th>新闻影响</th><th>技术分</th><th>交易策略</th><th>锚点</th><th>入场条件</th><th>不买条件</th><th>失效条件</th><th>规则</th><th>风险</th></tr>
        </thead>
        <tbody>{render_stock_rows(strategy, strategy_view)}</tbody>
      </table>
    </section>

    <h2>单股推理详情</h2>
    {render_stock_details(strategy, strategy_view)}

    <h2>观察池</h2>
    <section class="panel">
      <table>
        <thead><tr><th>代码</th><th>名称</th><th>原因</th><th>主题</th><th>异常</th></tr></thead>
        <tbody>{render_pool_rows(mapper.get("observation_pool"), [("code","Code"),("name","Name"),("reason","Reason"),("theme","Theme"),("anomaly","Anomaly")])}</tbody>
      </table>
    </section>

    <h2>排除股票</h2>
    <section class="panel">
      <table>
        <thead><tr><th>代码</th><th>名称</th><th>原因</th><th>来源</th></tr></thead>
        <tbody>{render_pool_rows(mapper.get("excluded_stocks"), [("code","Code"),("name","Name"),("reason","Reason"),("source","Source")])}</tbody>
      </table>
    </section>

    <h2>引用新闻</h2>
    <section class="panel">
      <ol class="news-list">
        {"".join(f"<li><b>{esc(ref)}</b>: {esc(text)}</li>" for ref, text in sorted(news_refs.items())) or '<li class="muted">暂无可解析的新闻引用</li>'}
      </ol>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render daily_report.html from JSON contracts")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--strategy", help="Path to strategy.json; default predict/{date}/strategy.json")
    parser.add_argument("--strategy-view", help="Path to mapper.strategy_view.json; default predict/{date}/mapper.strategy_view.json")
    parser.add_argument("--mapper", help="Path to mapper.json; default predict/{date}/mapper.json")
    parser.add_argument("--themes", help="Path to themes.json; default predict/{date}/themes.json")
    parser.add_argument("--news", help="Path to news.md; default predict/{date}/news.md")
    parser.add_argument("--output", help="Path to output HTML; default predict/{date}/daily_report.html")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    pdir = predict_dir(args.date)
    strategy_path = Path(args.strategy) if args.strategy else pdir / "strategy.json"
    strategy_view_path = Path(args.strategy_view) if args.strategy_view else pdir / "mapper.strategy_view.json"
    mapper_path = Path(args.mapper) if args.mapper else pdir / "mapper.json"
    themes_path = Path(args.themes) if args.themes else pdir / "themes.json"
    news_path = Path(args.news) if args.news else pdir / "news.md"
    output_path = Path(args.output) if args.output else pdir / "daily_report.html"

    strategy = read_json(strategy_path)
    if not isinstance(strategy, dict):
        print(f"[ERROR] missing or invalid strategy.json: {strategy_path}", file=sys.stderr)
        return 1

    strategy_view = read_json(strategy_view_path)
    mapper = read_json(mapper_path)
    themes = read_json(themes_path)
    html_text = render_report(args.date, strategy, strategy_view if isinstance(strategy_view, dict) else None, mapper if isinstance(mapper, dict) else None, themes if isinstance(themes, dict) else None, news_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8", newline="\n")
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
