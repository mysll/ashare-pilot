#!/usr/bin/env python3
"""Render daily JSON contracts as an A-share trading decision console."""

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


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def esc(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "—"
    return html.escape(str(value), quote=True)


def number(value: Any, digits: int = 1) -> str:
    try:
        text = f"{float(value):.{digits}f}"
        return text.rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return esc(value)


def value_at(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def by_code(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {str(x["code"]): x for x in items if isinstance(x, dict) and x.get("code")}


def direction_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    return {
        "bull": "看多",
        "bullish": "偏多",
        "mixed": "分歧",
        "panic": "恐慌",
        "neutral": "中性",
        "bearish": "看空",
        "unknown": "未确认",
        "看多": "看多",
        "偏多": "偏多",
        "中性": "中性",
        "看空": "看空",
    }.get(raw, "未识别")


def direction_class(value: Any) -> str:
    return {
        "看多": "rise",
        "偏多": "rise-soft",
        "分歧": "warn",
        "恐慌": "fall",
        "中性": "neutral",
        "看空": "fall",
        "未确认": "neutral",
        "未识别": "warn",
    }.get(str(value), "neutral")


def status_label(value: Any) -> str:
    return {"tradeable": "可交易", "watch": "观察", "discarded": "排除"}.get(
        str(value), str(value or "—")
    )


def status_class(value: Any) -> str:
    return {"tradeable": "rise", "watch": "warn", "discarded": "fall"}.get(
        str(value), "neutral"
    )


def regime_label(value: Any) -> str:
    return {
        "strong-sector": "强主题结构",
        "balanced": "均衡震荡",
        "weak-market": "弱势防守",
        "risk-off": "风险收缩",
        "risk-on": "风险偏好",
    }.get(str(value), str(value or "市场结构未确认"))


def profile_label(value: Any) -> str:
    return {
        "MOMENTUM": "强势接力",
        "PULLBACK": "回调布局",
        "DEFENSIVE": "防御布局",
    }.get(str(value), str(value or "—"))


def generated_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def score_value(candidate: dict[str, Any], key: str) -> Any:
    return value_at(candidate, "scores", key, "value")


def score_bar(value: Any, tone: str = "rise") -> str:
    try:
        score = max(0.0, min(100.0, float(value)))
        label = number(score)
    except (TypeError, ValueError):
        score, label = 0.0, "—"
    return f'<div class="score"><b>{label}</b><span><i class="{tone}" style="width:{score:.1f}%"></i></span></div>'


def theme_items(themes: dict[str, Any] | None, view: dict[str, Any] | None) -> list[dict[str, Any]]:
    if isinstance(themes, dict) and isinstance(themes.get("themes"), list):
        return [x for x in themes["themes"] if isinstance(x, dict)]
    if isinstance(view, dict) and isinstance(view.get("themes"), list):
        return [
            {
                "rank": x.get("rank"),
                "name": x.get("name"),
                "status": "tradeable",
                "heat": x.get("final_heat"),
            }
            for x in view["themes"]
            if isinstance(x, dict)
        ]
    return []


def render_market_chips(notes: Any) -> str:
    matches = re.findall(r"([A-Za-z0-9\u4e00-\u9fff]+)\s*([+-]\d+(?:\.\d+)?%)", str(notes or ""))
    return "".join(
        f'<span class="index-chip {"up" if change.startswith("+") else "down"}">{esc(name)} {esc(change)}</span>'
        for name, change in matches[:6]
    )


def render_theme_lens(items: list[dict[str, Any]]) -> str:
    top = sorted(items, key=lambda x: float(x.get("heat") or 0), reverse=True)[:6]
    if not top:
        return '<div class="empty">暂无主题热度数据</div>'
    colors = ["#FF5C68", "#FF7A45", "#FDB022", "#A78BFA", "#60A5FA", "#22D3EE"]
    total = sum(float(x.get("heat") or 0) for x in top) or 1
    start, segments, rows = 0.0, [], []
    maximum = max(float(x.get("heat") or 0) for x in top) or 1
    for idx, item in enumerate(top):
        heat = float(item.get("heat") or 0)
        end = start + heat / total * 360
        color = colors[idx]
        segments.append(f"{color} {start:.1f}deg {end:.1f}deg")
        rows.append(
            f"""<div class="theme-rank"><i style="background:{color}"></i><span>{esc(item.get('name'))}</span>
            <em><b style="width:{heat/maximum*100:.1f}%;background:{color}"></b></em><strong>{number(heat)}</strong></div>"""
        )
        start = end
    leader = top[0]
    return f"""<div class="theme-lens">
      <div class="donut" style="background:conic-gradient({','.join(segments)})"><div><b>{number(leader.get('heat'),0)}</b><span>{esc(leader.get('name'))}</span></div></div>
      <div class="theme-ranks">{''.join(rows)}</div>
    </div>"""


def render_direction_mix(stocks: list[dict[str, Any]]) -> str:
    labels = ("看多", "偏多", "中性", "看空")
    colors = {"看多": "#FF5C68", "偏多": "#FF7A45", "中性": "#91A1B5", "看空": "#32D583"}
    counts = {label: sum(1 for x in stocks if x.get("direction") == label) for label in labels}
    total = max(1, len(stocks))
    track = "".join(
        f'<i style="width:{counts[x]/total*100:.1f}%;background:{colors[x]}"></i>' for x in labels if counts[x]
    )
    legend = "".join(
        f'<span><b style="color:{colors[x]}">{counts[x]}</b>{x}</span>' for x in labels
    )
    return f"""<div class="direction-box"><div class="direction-total"><b>{len(stocks)}</b><span>只进入策略池</span></div>
    <div class="direction-track">{track}</div><div class="direction-legend">{legend}</div>
    <p>市场方向偏进攻，仍需区分主线核心与跟涨标的。</p></div>"""


def render_theme_rows(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in sorted(items, key=lambda x: (x.get("rank") or 999))[:20]:
        evidence = str(item.get("evidence") or "—")
        refs = [x.strip() for x in evidence.split(",") if x.strip()]
        evidence_html = "".join(f'<span class="evidence-tag">{esc(x)}</span>' for x in refs[:3]) or "—"
        rows.append(
            f"""<tr class="{'theme-top' if (item.get('rank') or 999) <= 3 else ''}">
              <td class="rank">{esc(item.get('rank'))}</td><td class="strong">{esc(item.get('name'))}</td>
              <td><span class="badge {status_class(item.get('status'))}">{status_label(item.get('status'))}</span></td>
              <td>{score_bar(item.get('heat'))}</td><td>{number(item.get('confidence'),0)}</td>
              <td><span class="badge {direction_class(direction_label(item.get('direction')))}">{esc(direction_label(item.get('direction')))}</span></td>
              <td class="theme-meaning" title="{esc(item.get('reason'))}"><span class="cell-clamp one-line">{esc(item.get('reason'))}</span></td><td>{evidence_html}</td>
            </tr>"""
        )
    return "".join(rows) or '<tr><td colspan="8" class="empty">暂无主题数据</td></tr>'


def render_strategy_rows(strategy: dict[str, Any], view: dict[str, Any] | None) -> str:
    candidates = by_code(view.get("candidates") if isinstance(view, dict) else [])
    rows = []
    for stock in strategy.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        cand = candidates.get(str(stock.get("code")), {})
        rows.append(
            f"""<tr><td><span class="badge {direction_class(stock.get('direction'))}">{esc(stock.get('direction'))}</span></td>
              <td class="mono">{esc(stock.get('code'))}</td><td class="strong">{esc(stock.get('name'))}</td><td>{esc(stock.get('sector'))}</td>
              <td class="rating">{esc(stock.get('rating'))}</td><td>{score_bar(score_value(cand,'composite'))}</td>
              <td>{number(score_value(cand,'theme_heat'))}</td><td>{esc(stock.get('entry_profile'))}</td>
              <td class="two-lines" title="{esc(stock.get('entry_trigger'))}"><span class="cell-clamp">{esc(stock.get('entry_trigger'))}</span></td>
              <td class="two-lines no-buy" title="{esc(stock.get('no_buy_condition'))}"><span class="cell-clamp">{esc(stock.get('no_buy_condition'))}</span></td></tr>"""
        )
    return "".join(rows) or '<tr><td colspan="10" class="empty">暂无策略股票</td></tr>'


def focus_cards(strategy: dict[str, Any], view: dict[str, Any] | None) -> str:
    candidates = by_code(view.get("candidates") if isinstance(view, dict) else [])
    stocks = [x for x in strategy.get("stocks", []) if isinstance(x, dict)]
    stocks.sort(
        key=lambda x: (
            int(re.search(r"\d+", str(x.get("rating") or "0")).group()) if re.search(r"\d+", str(x.get("rating") or "")) else 0,
            float(score_value(candidates.get(str(x.get("code")), {}), "composite") or 0),
        ),
        reverse=True,
    )
    cards = []
    for stock in stocks[:6]:
        cand = candidates.get(str(stock.get("code")), {})
        logic = value_at(stock, "reasoning", "direction_path") or stock.get("profile_trace")
        cards.append(
            f"""<article class="focus-card card"><header><div><h3>{esc(stock.get('name'))}</h3><span class="mono">{esc(stock.get('code'))}</span></div>
              <span class="rating">{esc(stock.get('rating'))}</span></header>
              <div class="focus-tags"><span>{esc(stock.get('sector'))}</span><span class="badge {direction_class(stock.get('direction'))}">{esc(stock.get('direction'))}</span></div>
              <div class="focus-score"><small>综合分</small>{score_bar(score_value(cand,'composite'))}</div>
              <dl><div><dt>策略</dt><dd>{esc(stock.get('entry_profile'))}</dd></div>
              <div><dt>入场条件</dt><dd>{esc(stock.get('entry_trigger'))}</dd></div>
              <div><dt>不买条件</dt><dd class="no-buy">{esc(stock.get('no_buy_condition'))}</dd></div></dl>
              <footer><b>核心逻辑</b><span>{esc(logic)}</span></footer></article>"""
        )
    return "".join(cards) or '<div class="empty">暂无重点策略</div>'


def stock_details(strategy: dict[str, Any], view: dict[str, Any] | None) -> str:
    candidates = by_code(view.get("candidates") if isinstance(view, dict) else [])
    blocks = []
    for stock in strategy.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        cand = candidates.get(str(stock.get("code")), {})
        profile = stock.get("profile") if isinstance(stock.get("profile"), dict) else {}
        reasoning = stock.get("reasoning") if isinstance(stock.get("reasoning"), dict) else {}
        inputs = cand.get("strategy_inputs") if isinstance(cand.get("strategy_inputs"), dict) else {}
        pattern = cand.get("pattern") if isinstance(cand.get("pattern"), dict) else {}
        signals = " · ".join(
            f"{key}:{value_at(pattern,key,'state') or '—'}" for key in ("heat", "leader", "auction", "rotation", "volume")
        )
        blocks.append(
            f"""<details class="detail card"><summary><span class="mono">{esc(stock.get('code'))}</span> {esc(stock.get('name'))}
              <span>{esc(stock.get('direction'))} · {esc(stock.get('rating'))} · {esc(stock.get('entry_profile'))} · {esc(stock.get('anchor'))}</span></summary>
              <div class="detail-grid">
                <section><h4>推理链路</h4><p>{esc(reasoning.get('direction_path'))}</p><p class="risk-text"><b>风险：</b>{esc(reasoning.get('risk'))}</p><p>{esc(reasoning.get('reread'))}</p></section>
                <section><h4>感知信号</h4><p>{esc(signals)}</p><p><b>异常：</b>{esc(cand.get('anomaly'))}</p><p><b>新闻：</b>{esc(cand.get('news_link'))}</p></section>
                <section><h4>策略输入</h4><p>现价 {number(inputs.get('price'),2)} · MA5 {number(inputs.get('ma5'),2)} · MA20 {number(inputs.get('ma20'),2)}</p><p>ATR% {number(inputs.get('atr_pct'),2)} · High20 {number(inputs.get('high20'),2)} · Low20 {number(inputs.get('low20'),2)}</p></section>
                <section><h4>交易画像</h4><p>{esc(stock.get('profile_trace'))}</p><p>{esc(profile_label(profile.get('playbook')))} · {esc(profile.get('entry_window'))} · {esc(profile.get('stop_policy'))}</p></section>
              </div></details>"""
        )
    return "".join(blocks) or '<div class="empty">暂无推理详情</div>'


def observation_group(item: dict[str, Any]) -> tuple[str, str]:
    text = f"{item.get('reason') or ''} {item.get('anomaly') or ''}"
    if any(x in text for x in ("tech_score", "技术")):
        return "技术分不足", "fall"
    if any(x in text for x in ("非主线", "弱主题", "theme")):
        return "非核心主线", "neutral"
    if any(x in text for x in ("回踩", "MA5", "MA20")):
        return "等待回踩", "blue"
    if any(x in text for x in ("放量", "量能")):
        return "等待放量", "blue"
    if item.get("anomaly"):
        return "负面异常", "warn"
    return "等待确认", "blue"


def observation_groups(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return '<div class="empty">观察池为空</div>'
    groups: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        label, tone = observation_group(item)
        groups.setdefault(label, (tone, []))[1].append(item)
    blocks = []
    for label, (tone, values) in groups.items():
        rows = "".join(
            f"<tr><td class='mono'>{esc(x.get('code'))}</td><td class='strong'>{esc(x.get('name'))}</td><td>{esc(x.get('theme'))}</td><td>{esc(x.get('reason'))}</td><td>{esc(x.get('anomaly'))}</td></tr>"
            for x in values
        )
        blocks.append(
            f"""<details class="pool-group card"><summary><span class="group-mark {tone}"></span><b>{label}</b><em>{len(values)}</em>
            <span>{esc(' / '.join(str(x.get('name') or '') for x in values[:3]))}</span></summary>
            <div class="table-wrap"><table><thead><tr><th>代码</th><th>名称</th><th>主题</th><th>观察原因</th><th>异常</th></tr></thead><tbody>{rows}</tbody></table></div></details>"""
        )
    return "".join(blocks)


def excluded_filter(mapper: dict[str, Any], view: dict[str, Any] | None) -> str:
    items = mapper.get("excluded_stocks") if isinstance(mapper.get("excluded_stocks"), list) else []
    summary = view.get("excluded_stocks") if isinstance(view, dict) and isinstance(view.get("excluded_stocks"), dict) else {}
    reasons = summary.get("top_reasons") if isinstance(summary.get("top_reasons"), list) else []
    stats = "".join(
        f'<article><small>{esc(x.get("reason"))}</small><b>{esc(x.get("count"))}</b></article>'
        for x in reasons
        if isinstance(x, dict)
    )
    rows = "".join(
        f"<tr><td class='mono'>{esc(x.get('code'))}</td><td>{esc(x.get('name'))}</td><td>{esc(x.get('reason'))}</td><td>{esc(x.get('source'))}</td></tr>"
        for x in items
        if isinstance(x, dict)
    )
    return f"""<div class="filter-stats">{stats or '<div class="empty">暂无排除统计</div>'}</div>
      <details class="excluded-list card"><summary>展开全部排除股票 <em>{esc(summary.get('count') or len(items))}</em></summary>
      <div class="table-wrap"><table><thead><tr><th>代码</th><th>名称</th><th>排除原因</th><th>来源</th></tr></thead><tbody>{rows}</tbody></table></div></details>"""


def read_news_refs(path: Path, refs: set[str]) -> dict[str, dict[str, str]]:
    doc = read_json(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        return {}
    wanted: dict[int, str] = {}
    for ref in refs:
        match = re.fullmatch(r"news#([1-9]\d*)", str(ref).strip())
        if match:
            wanted[int(match.group(1))] = str(ref).strip()
    result: dict[str, dict[str, str]] = {}
    for item in doc["items"]:
        if not isinstance(item, dict) or item.get("id") not in wanted:
            continue
        original_ref = wanted[item["id"]]
        result[original_ref] = {
            "title": str(item.get("title") or "").strip()[:260],
            "url": str(item.get("url") or "").strip(),
        }
    return result


def news_chain(path: Path, strategy: dict[str, Any], view: dict[str, Any] | None) -> str:
    candidates = view.get("candidates") if isinstance(view, dict) and isinstance(view.get("candidates"), list) else []
    stock_map = by_code(strategy.get("stocks"))
    links: dict[str, list[str]] = {}
    for cand in candidates:
        if not isinstance(cand, dict) or not cand.get("news_link"):
            continue
        stock = stock_map.get(str(cand.get("code")))
        label = f"{stock.get('sector')} · {stock.get('name')}" if stock else str(cand.get("name") or cand.get("code"))
        links.setdefault(str(cand["news_link"]), []).append(label)
    texts = read_news_refs(path, set(links))
    cards = "".join(
        f"""<article class="news-card card"><header><span>{esc(ref)}</span><b>{esc(' / '.join(links.get(ref,[])[:3]))}</b></header>
        <p><a href="{esc(item.get('url'))}" target="_blank" rel="noopener noreferrer">{esc(item.get('title'))}</a></p></article>"""
        for ref, item in sorted(texts.items())
    )
    return cards or '<div class="empty">暂无可解析的新闻引用</div>'


def render_report(
    date: str,
    strategy: dict[str, Any],
    view: dict[str, Any] | None,
    mapper: dict[str, Any] | None,
    themes: dict[str, Any] | None,
    news_json_path: Path,
) -> str:
    market = strategy.get("market") if isinstance(strategy.get("market"), dict) else {}
    stocks = [x for x in strategy.get("stocks", []) if isinstance(x, dict)]
    mapper = mapper if isinstance(mapper, dict) else {}
    themes_list = theme_items(themes, view)
    dominant = value_at(view, "market_state", "dominant_themes") or []
    dominant_text = " / ".join(str(x.get("name")) for x in dominant if isinstance(x, dict))
    subtitle = f"{regime_label(market.get('regime_hint'))}，今日聚焦 {dominant_text}。" if dominant_text else esc(market.get("notes"))
    generated = strategy.get("generated_at")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日交易决策总控台 · {esc(date)}</title>
<style>
:root{{color-scheme:dark;--bg:#070B10;--soft:#0B1118;--panel:#111923;--panel2:#0E1724;--panel3:#151F2B;--line:#243244;--line2:#1D2A38;--text:#E7EDF5;--strong:#FFF;--sub:#91A1B5;--accent:#22D3EE;--blue:#60A5FA;--rise:#FF5C68;--rise2:#FF7A45;--rise-soft:rgba(255,92,104,.14);--fall:#32D583;--fall-soft:rgba(50,213,131,.14);--warn:#FDB022;--warn-soft:rgba(253,176,34,.15);--danger:#F04438;--neutral:#34445A}}
*{{box-sizing:border-box}}html{{background:var(--bg)}}body{{margin:0;color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 12% -8%,rgba(34,211,238,.08),transparent 28%),linear-gradient(180deg,#09111a,var(--bg) 28%)}}
.page{{max-width:1540px;margin:auto;padding:0 30px 48px}}.topbar{{margin:0 -30px 24px;padding:25px 30px;border-bottom:1px solid var(--line);background:linear-gradient(110deg,rgba(7,11,16,.98),rgba(14,28,43,.95) 55%,rgba(7,11,16,.98))}}.topbar-inner{{max-width:1480px;margin:auto;display:flex;justify-content:space-between;gap:28px}}h1,h2,h3,p{{margin:0}}h1{{font-size:30px}}.subtitle{{margin-top:7px;color:#a9b8ca}}.meta{{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:7px;max-width:470px}}.meta span{{padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--sub);background:#0a1420;font-size:12px}}
.card,.panel{{border:1px solid var(--line);border-radius:14px;background:linear-gradient(180deg,rgba(17,25,35,.97),rgba(10,17,26,.97));box-shadow:0 18px 44px rgba(0,0,0,.24)}}.cockpit{{display:grid;grid-template-columns:1.05fr 1.5fr .95fr;gap:13px}}.cockpit-card{{min-height:235px;padding:18px;position:relative;overflow:hidden}}.cockpit-card:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}}.label{{color:var(--sub);font-size:12px;letter-spacing:.1em}}.market-state{{display:flex;align-items:center;gap:14px;margin:20px 0 13px}}.orb{{width:48px;height:48px;border-radius:50%;background:radial-gradient(circle,var(--rise),rgba(255,92,104,.18) 64%,transparent 66%);box-shadow:0 0 32px rgba(255,92,104,.3)}}.market-state h2{{font-size:25px}}.market-state p{{color:var(--sub);font-size:12px}}.chips{{display:flex;flex-wrap:wrap;gap:6px}}.index-chip{{padding:4px 8px;border-radius:7px;font-size:12px;font-weight:700}}.index-chip.up{{color:var(--rise);background:var(--rise-soft)}}.index-chip.down{{color:var(--fall);background:var(--fall-soft)}}.market-note{{margin-top:12px;color:#b8c5d5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.theme-lens{{display:grid;grid-template-columns:150px 1fr;gap:15px;align-items:center;margin-top:18px}}.donut{{width:142px;height:142px;border-radius:50%;display:grid;place-items:center}}.donut>div{{width:92px;height:92px;border-radius:50%;display:grid;place-items:center;align-content:center;text-align:center;background:var(--panel)}}.donut b{{font-size:27px}}.donut span{{color:var(--sub);font-size:12px}}.theme-ranks{{display:grid;gap:8px}}.theme-rank{{display:grid;grid-template-columns:8px 82px 1fr 30px;gap:7px;align-items:center;font-size:12px}}.theme-rank>i{{width:7px;height:7px;border-radius:50%}}.theme-rank em{{height:6px;border-radius:6px;background:#233143;overflow:hidden}}.theme-rank em b{{display:block;height:100%}}.theme-rank strong{{text-align:right}}
.direction-box{{margin-top:18px}}.direction-total b{{display:block;font:800 42px/1 ui-monospace,SFMono-Regular,monospace}}.direction-total span{{font-weight:700}}.direction-track{{display:flex;height:14px;margin:18px 0 12px;border-radius:9px;overflow:hidden;background:#233143}}.direction-track i{{height:100%}}.direction-legend{{display:grid;grid-template-columns:1fr 1fr;gap:7px;color:var(--sub);font-size:12px}}.direction-legend span{{display:flex;gap:5px}}.direction-box p{{margin-top:14px;color:#b8c5d5;font-size:12px}}
.section-head{{display:flex;justify-content:space-between;align-items:end;margin:30px 0 11px}}.section-head h2{{font-size:20px}}.section-head h2:before{{content:"";display:inline-block;width:4px;height:18px;margin-right:9px;vertical-align:-2px;border-radius:2px;background:var(--accent)}}.section-head p{{color:var(--sub);font-size:12px}}.panel{{overflow:hidden}}.table-wrap,.panel{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:1000px}}th{{position:sticky;top:0;z-index:2;color:var(--sub);background:rgba(10,17,26,.97);font-weight:600}}th,td{{padding:12px 10px;border-bottom:1px solid rgba(36,50,68,.72);text-align:left;font-size:13px;vertical-align:top}}tbody tr:hover td{{background:rgba(96,165,250,.055)}}.strong{{font-weight:700;color:var(--strong)}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#d8f3ff;white-space:nowrap}}.rank{{font-weight:800;color:var(--accent)}}.rating{{color:var(--warn);font-weight:800;white-space:nowrap}}
.badge{{display:inline-flex;align-items:center;justify-content:center;min-height:24px;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}}.rise{{color:var(--rise);background:var(--rise-soft)}}.rise-soft{{color:#ffad8b;background:rgba(255,122,69,.14)}}.fall{{color:var(--fall);background:var(--fall-soft)}}.warn{{color:var(--warn);background:var(--warn-soft)}}.neutral{{color:#c7d2e1;background:rgba(145,161,181,.14)}}.blue{{color:var(--blue);background:rgba(96,165,250,.13)}}.score{{display:grid;grid-template-columns:32px 72px;gap:7px;align-items:center}}.score span{{height:6px;border-radius:7px;background:#233143;overflow:hidden}}.score i{{display:block;height:100%;background:linear-gradient(90deg,var(--rise),var(--rise2))}}.theme-meaning{{min-width:220px;max-width:320px}}.two-lines{{min-width:210px;max-width:320px}}.cell-clamp{{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}}.cell-clamp.one-line{{-webkit-line-clamp:1}}.no-buy{{color:#ffc268}}.evidence-tag{{display:inline-block;margin:1px 3px 1px 0;padding:2px 6px;border-radius:5px;color:var(--blue);background:rgba(96,165,250,.1);font-size:11px}}.theme-top td{{background:rgba(255,92,104,.025)}}
.focus-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}}.focus-card{{padding:17px;display:flex;flex-direction:column;min-height:385px}}.focus-card header{{display:flex;justify-content:space-between}}.focus-card h3{{font-size:18px}}.focus-card header .mono{{font-size:12px}}.focus-tags{{display:flex;align-items:center;gap:7px;margin:13px 0}}.focus-tags>span:first-child{{color:var(--accent);margin-right:auto}}.focus-score{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-top:1px solid var(--line)}}.focus-score small{{color:var(--sub)}}dl{{margin:0}}dl div{{padding:8px 0;border-top:1px solid var(--line2)}}dt{{color:var(--sub);font-size:11px}}dd{{margin:3px 0 0}}.focus-card footer{{display:grid;gap:4px;margin-top:auto;padding-top:10px;border-top:1px solid var(--line)}}.focus-card footer b{{color:var(--sub);font-size:11px}}.focus-card footer span{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:#cbd6e3}}
.detail,.pool-group,.excluded-list{{margin:9px 0;overflow:hidden}}summary{{cursor:pointer;list-style:none;padding:13px 15px}}summary::-webkit-details-marker{{display:none}}.detail summary{{font-weight:700}}.detail summary>span:last-child{{float:right;color:var(--sub);font-size:12px;font-weight:500}}.detail-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;padding:0 15px 15px}}.detail-grid section{{padding-top:10px;border-top:1px solid var(--line)}}.detail-grid h4{{margin:0 0 7px;color:#c9f7ff}}.detail-grid p{{margin:6px 0;color:#c8d4e2}}.risk-text{{color:var(--warn)!important}}
.pool-stack{{display:grid;gap:9px}}.pool-group summary{{display:flex;align-items:center;gap:9px}}.pool-group summary em,.excluded-list summary em{{font-style:normal;padding:1px 7px;border-radius:999px;background:#243244}}.pool-group summary>span:last-child{{margin-left:auto;color:var(--sub);font-size:12px}}.group-mark{{width:6px;height:24px;border-radius:3px;background:var(--blue)}}.group-mark.fall{{background:var(--fall)}}.group-mark.warn{{background:var(--warn)}}.group-mark.neutral{{background:#64748b}}.filter-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}}.filter-stats article{{padding:14px;border:1px solid var(--line);border-radius:11px;background:var(--panel2)}}.filter-stats small{{display:block;color:var(--sub)}}.filter-stats b{{font:800 28px/1.2 ui-monospace,SFMono-Regular,monospace;color:var(--fall)}}.excluded-list summary{{font-weight:700}}
.news-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.news-card{{padding:14px}}.news-card header{{display:flex;gap:8px;align-items:center;margin-bottom:8px}}.news-card header span{{padding:2px 6px;border-radius:5px;color:var(--blue);background:rgba(96,165,250,.1);font-size:11px}}.news-card header b{{color:var(--accent);font-size:12px}}.news-card p{{color:#cbd6e3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.news-card a{{color:inherit;text-decoration:none}}.news-card a:hover{{color:var(--blue);text-decoration:underline}}.footer{{margin-top:27px;padding-top:16px;border-top:1px solid var(--line);text-align:center;color:var(--sub);font-size:12px}}.empty{{padding:24px;text-align:center;color:var(--sub)}}
@media(max-width:1150px){{.cockpit{{grid-template-columns:1fr 1fr}}.cockpit-card:first-child{{grid-column:1/-1}}.focus-grid{{grid-template-columns:repeat(2,1fr)}}.news-grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:760px){{.page{{padding:0 14px 30px}}.topbar{{margin:0 -14px 18px;padding:20px 14px}}.topbar-inner{{display:block}}.meta{{justify-content:flex-start;margin-top:13px}}.cockpit,.focus-grid,.news-grid,.filter-stats{{grid-template-columns:1fr}}.cockpit-card:first-child{{grid-column:auto}}.detail-grid{{grid-template-columns:1fr}}.detail summary>span:last-child,.pool-group summary>span:last-child{{display:none}}h1{{font-size:25px}}}}
</style></head><body><div class="page">
<header class="topbar"><div class="topbar-inner"><div><h1>每日交易决策总控台</h1><p class="subtitle">{esc(subtitle)}</p></div>
<div class="meta"><span>日期 {esc(date)}</span><span>生成时间 {generated_time(generated)}</span><span>JSON 决策阅读层</span></div></div></header>
<section class="cockpit">
  <article class="card cockpit-card"><div class="label">市场结构判断 / Market Structure</div><div class="market-state"><div class="orb"></div><div><h2>{esc(regime_label(market.get('regime_hint')))}</h2><p>{esc(dominant_text or '主线未确认')}</p></div></div><div class="chips">{render_market_chips(market.get('notes'))}</div><p class="market-note">{esc(market.get('notes'))}</p></article>
  <article class="card cockpit-card"><div class="label">主线热度 / Theme Heat</div>{render_theme_lens(themes_list)}</article>
  <article class="card cockpit-card"><div class="label">策略方向分布 / Direction</div>{render_direction_mix(stocks)}</article>
</section>
<div class="section-head"><h2>主线主题雷达</h2><p>交易状态、热度与证据源</p></div><section class="panel"><table><thead><tr><th>排名</th><th>主题</th><th>交易状态</th><th>热度</th><th>置信度</th><th>方向</th><th>交易意义</th><th>证据源</th></tr></thead><tbody>{render_theme_rows(themes_list)}</tbody></table></section>
<div class="section-head"><h2>策略总表（{len(stocks)}只）</h2><p>默认仅保留核心决策字段</p></div><section class="panel"><table><thead><tr><th>方向</th><th>代码</th><th>名称</th><th>板块</th><th>评级</th><th>综合分</th><th>主题热度</th><th>策略</th><th>入场条件</th><th>不买条件</th></tr></thead><tbody>{render_strategy_rows(strategy,view)}</tbody></table></section>
<div class="section-head"><h2>重点策略池</h2><p>按评级与综合分选取前六</p></div><section class="focus-grid">{focus_cards(strategy,view)}</section>
<div class="section-head"><h2>单股推理链路</h2><p>默认折叠，按需追溯</p></div>{stock_details(strategy,view)}
<div class="section-head"><h2>观察池</h2><p>按等待原因分组，默认折叠</p></div><section class="pool-stack">{observation_groups(mapper.get('observation_pool'))}</section>
<div class="section-head"><h2>风险过滤 / 排除股票</h2><p>先看聚合原因，完整名单默认折叠</p></div>{excluded_filter(mapper,view)}
<div class="section-head"><h2>新闻证据链</h2><p>仅展示策略候选真实引用</p></div><section class="news-grid">{news_chain(news_json_path,strategy,view)}</section>
<footer class="footer">数据源：strategy.json / mapper.strategy_view.json / mapper.json / themes.json / news.json · 本页面仅为中文阅读层，不构成投资建议。</footer>
</div></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render daily_report.html from JSON contracts")
    parser.add_argument("--date", required=True)
    parser.add_argument("--strategy")
    parser.add_argument("--strategy-view")
    parser.add_argument("--mapper")
    parser.add_argument("--themes")
    parser.add_argument("--news-json")
    parser.add_argument("--output")
    args = parser.parse_args()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    pdir = workspace_root() / "predict" / args.date
    strategy_path = Path(args.strategy) if args.strategy else pdir / "strategy.json"
    strategy = read_json(strategy_path)
    if not isinstance(strategy, dict):
        print(f"[ERROR] missing or invalid strategy.json: {strategy_path}", file=sys.stderr)
        return 1
    view = read_json(Path(args.strategy_view) if args.strategy_view else pdir / "mapper.strategy_view.json")
    mapper = read_json(Path(args.mapper) if args.mapper else pdir / "mapper.json")
    themes = read_json(Path(args.themes) if args.themes else pdir / "themes.json")
    news_json = Path(args.news_json) if args.news_json else pdir / "news.json"
    if not news_json.exists():
        print(f"[ERROR] missing required news.json: {news_json}", file=sys.stderr)
        return 1
    output = Path(args.output) if args.output else pdir / "daily_report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_report(
            args.date,
            strategy,
            view if isinstance(view, dict) else None,
            mapper if isinstance(mapper, dict) else None,
            themes if isinstance(themes, dict) else None,
            news_json,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
