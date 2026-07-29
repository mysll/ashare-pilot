#!/usr/bin/env python3
"""Query theme library.

Usage:
    python query_theme.py theme AI算力
    python query_theme.py concept 算力概念
    python query_theme.py stock sz000977
    python query_theme.py keyword GPU
    python query_theme.py list --top 20
    python query_theme.py stats
    python query_theme.py leaders AI算力 [--top N]
    python query_theme.py pure AI算力 [--top N]
    python query_theme.py candidates AI算力 [--top N]
    python query_theme.py market AI算力 [--top N]
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

from ashare_pilot.themes.runtime import theme_cache_path, theme_data_path

CACHE_DIR = theme_cache_path()
STOCKS_CACHE_DIR = CACHE_DIR / "stocks"
THEMES_DIR = theme_data_path("themes")
CONCEPTS_DIR = theme_data_path("concepts")
STOCKS_DIR = theme_data_path("stocks")
ALIASES_DIR = theme_data_path("aliases")
INDEX_DIR = theme_data_path("index")
METADATA_DIR = theme_data_path("metadata")


def load_json(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_index(filename):
    return load_json(INDEX_DIR / filename) or {}


def _safe_filename(name):
    return re.sub(r'[<>:"/\\|?*()]', '_', name)


def load_theme_file(theme_name):
    safe_name = _safe_filename(theme_name)
    path = THEMES_DIR / f"{safe_name}.json"
    data = load_json(path)
    if data and data.get("name"):
        return data
    return None


def load_concept_file(concept_name):
    safe_name = _safe_filename(concept_name)
    path = CONCEPTS_DIR / f"{safe_name}.json"
    data = load_json(path)
    if data and data.get("name"):
        return data
    return None


def load_stock_file(stock_code):
    safe_code = stock_code.lower()
    return load_json(STOCKS_DIR / f"{safe_code}.json")


def load_theme_aliases():
    data = load_json(ALIASES_DIR / "theme_aliases.json")
    return data if isinstance(data, dict) else {}


def _resolve_theme(name):
    theme_data = load_theme_file(name)
    if theme_data:
        return theme_data

    alias_map = load_theme_aliases()
    for theme, aliases in alias_map.items():
        if name in aliases or name.lower() in [a.lower() for a in aliases]:
            theme_data = load_theme_file(theme)
            if theme_data:
                return theme_data

    k2t = load_index("keyword_to_theme.json")
    if name in k2t:
        theme_data = load_theme_file(k2t[name])
        if theme_data:
            return theme_data
    for k, t in k2t.items():
        if name.lower() in k.lower() or k.lower() in name.lower():
            theme_data = load_theme_file(t)
            if theme_data:
                return theme_data

    t2c = load_index("theme_to_concept.json")
    for t_name in t2c:
        if name.lower() in t_name.lower():
            theme_data = load_theme_file(t_name)
            if theme_data:
                return theme_data

    return None


def _resolve_concept(name):
    concept_data = load_concept_file(name)
    if concept_data:
        return concept_data

    c2s = load_index("concept_to_stock.json")
    for c_name in c2s:
        if name.lower() in c_name.lower():
            concept_data = load_concept_file(c_name)
            if concept_data:
                return concept_data

    return None


def query_theme(name):
    theme_data = _resolve_theme(name)
    if not theme_data:
        print(f"Theme not found: {name}")
        return None
    return theme_data


def query_concept(name):
    concept_data = _resolve_concept(name)
    if not concept_data:
        print(f"Concept not found: {name}")
        return None
    return concept_data


def query_stock(code):
    stock_data = load_stock_file(code)
    if stock_data:
        return stock_data

    s2t = load_index("stock_to_theme.json")
    for s_code in s2t:
        if code.lower() in s_code.lower():
            stock_data = load_stock_file(s_code)
            if stock_data:
                return stock_data

    if not stock_data:
        print(f"Stock not found: {code}")
        return None

    return stock_data


def query_keyword(keyword):
    k2t = load_index("keyword_to_theme.json")

    if keyword in k2t:
        return keyword, k2t[keyword], "theme"

    for k, theme in k2t.items():
        if keyword.lower() in k.lower() or k.lower() in keyword.lower():
            return k, theme, "theme"

    alias_map = load_theme_aliases()
    for theme, aliases in alias_map.items():
        if keyword in aliases or keyword.lower() in [a.lower() for a in aliases]:
            return keyword, theme, "theme"

    c2s = load_index("concept_to_stock.json")
    for c_name in c2s:
        if keyword.lower() in c_name.lower() or c_name.lower() in keyword.lower():
            return keyword, c_name, "concept"

    return keyword, None, None


def list_themes(top=0):
    t2s = load_index("theme_to_stock.json")
    sorted_themes = sorted(t2s.items(), key=lambda x: len(x[1]), reverse=True)
    if top > 0:
        sorted_themes = sorted_themes[:top]
    return sorted_themes


def show_stats():
    t2c = load_index("theme_to_concept.json")
    t2s = load_index("theme_to_stock.json")
    c2s = load_index("concept_to_stock.json")
    s2t = load_index("stock_to_theme.json")
    s2c = load_index("stock_to_concept.json")
    k2t = load_index("keyword_to_theme.json")

    return {
        "themes": len(t2c),
        "concepts_themed": len(set(c for cs in t2c.values() for c in cs)),
        "concepts_total": len(c2s),
        "stocks": len(s2t),
        "keywords": len(k2t),
    }


def _load_concept_cache_snapshot():
    """遍历 cache/stocks/*.json，构建 {code: {name, change_pct, amount, turnover, volume_ratio}} 快照"""
    snapshot = {}
    if not STOCKS_CACHE_DIR.exists():
        return snapshot

    for f in STOCKS_CACHE_DIR.glob("*.json"):
        data = load_json(f)
        if not data:
            continue
        fetch_time = data.get("fetch_time", "")
        for s in data.get("stocks", []):
            code = s.get("code", "")
            if not code:
                continue
            name = s.get("name", "")
            if name.startswith("ST") or name.startswith("*ST"):
                continue
            change_pct = s.get("change_pct")
            try:
                change_pct = float(change_pct) if change_pct is not None else 0.0
            except (ValueError, TypeError):
                change_pct = 0.0
            try:
                amount = float(s.get("amount", 0) or 0)
            except (ValueError, TypeError):
                amount = 0.0
            try:
                turnover = float(s.get("turnover", 0) or 0)
            except (ValueError, TypeError):
                turnover = 0.0
            try:
                volume_ratio = float(s.get("volume_ratio", 0) or 0)
            except (ValueError, TypeError):
                volume_ratio = 0.0
            snapshot[code] = {
                "name": name,
                "change_pct": change_pct,
                "amount": amount,
                "turnover": turnover,
                "volume_ratio": volume_ratio,
                "fetch_time": fetch_time,
            }
    return snapshot


def _compute_market_view(theme_data, top=10, snapshot=None):
    """从 theme_data 的 stocks 列表匹配缓存快照，计算 market 视图"""
    stocks = theme_data.get("stocks", []) or []
    if snapshot is None:
        snapshot = _load_concept_cache_snapshot()

    # 构建 industry_score 映射（来自 industry_leaders + candidate_stocks）
    industry_scores = {}
    for il in (theme_data.get("industry_leaders") or []):
        code = il.get("code", "")
        if code:
            industry_scores[code] = il.get("industry_score", 0)
    for cs in (theme_data.get("candidate_stocks") or []):
        code = cs.get("code", "")
        if code and code not in industry_scores:
            ind = round(
                cs.get("purity_score", 0) * 0.40 +
                cs.get("liquidity_score", 0) * 0.35 +
                cs.get("market_cap_score", 0) * 0.25, 1
            )
            industry_scores[code] = ind

    matched = []
    fetch_times = set()
    for code in stocks:
        snap = snapshot.get(code)
        if snap:
            matched.append({
                "code": code,
                "name": snap["name"],
                "change_pct": snap["change_pct"],
                "amount": snap["amount"],
                "turnover": snap["turnover"],
                "volume_ratio": snap["volume_ratio"],
                "industry_score": industry_scores.get(code),
            })
            if snap["fetch_time"]:
                fetch_times.add(snap["fetch_time"])

    if not matched:
        return {"data_time": "", "top_gainers": [], "top_amount": [],
                "top_turnover": [], "top_vr": [], "market_attention": [],
                "cross_rank_highlights": [], "threshold_gainers": [],
                "threshold_attention": []}

    N = len(matched)

    top_gainers = sorted(matched, key=lambda x: x["change_pct"], reverse=True)[:top]
    top_amount = sorted(matched, key=lambda x: x["amount"], reverse=True)[:top]
    top_turnover = sorted(matched, key=lambda x: x["turnover"], reverse=True)[:top]
    top_vr = sorted(matched, key=lambda x: x["volume_ratio"], reverse=True)[:top]

    # 综合排名：market_attention_score = 0.6 * amount_rank + 0.25 * turnover_rank + 0.15 * volume_ratio_rank
    by_amount = sorted(matched, key=lambda x: x["amount"], reverse=True)
    by_turnover = sorted(matched, key=lambda x: x["turnover"], reverse=True)
    by_vr = sorted(matched, key=lambda x: x["volume_ratio"], reverse=True)

    rank_amount = {}
    rank_turnover = {}
    rank_vr = {}
    for i, s in enumerate(by_amount):
        rank_amount[s["code"]] = i + 1
    for i, s in enumerate(by_turnover):
        rank_turnover[s["code"]] = i + 1
    for i, s in enumerate(by_vr):
        rank_vr[s["code"]] = i + 1

    for s in matched:
        amount_pctile = 100 * (N - rank_amount[s["code"]] + 1) / N
        turnover_pctile = 100 * (N - rank_turnover[s["code"]] + 1) / N
        vr_pctile = 100 * (N - rank_vr[s["code"]] + 1) / N
        s["attention_score"] = round(0.6 * amount_pctile + 0.25 * turnover_pctile + 0.15 * vr_pctile, 1)
        s["amount_rank"] = rank_amount[s["code"]]
        s["turnover_rank"] = rank_turnover[s["code"]]
        s["vr_rank"] = rank_vr[s["code"]]

    market_attention = sorted(matched, key=lambda x: x["attention_score"], reverse=True)[:top]
    threshold_attention = [
        s for s in sorted(matched, key=lambda x: x["attention_score"], reverse=True)
        if s["attention_score"] >= 80
    ]
    threshold_gainers = [
        s for s in sorted(matched, key=lambda x: x["change_pct"], reverse=True)
        if s["change_pct"] >= 3
    ]

    # 热点交集：同时出现在多个 top-N 列表中的股票
    by_gainers = sorted(matched, key=lambda x: x["change_pct"], reverse=True)
    gainer_set = {s["code"] for s in top_gainers}
    amount_set = {s["code"] for s in top_amount}
    turnover_set = {s["code"] for s in top_turnover}
    vr_set = {s["code"] for s in top_vr}
    attention_set = {s["code"] for s in market_attention}

    cross_rank_highlights = []
    for s in matched:
        hits = 0
        if s["code"] in gainer_set:
            hits += 1
        if s["code"] in amount_set:
            hits += 1
        if s["code"] in turnover_set:
            hits += 1
        if s["code"] in vr_set:
            hits += 1
        if s["code"] in attention_set:
            hits += 1
        if hits >= 2:
            gainer_rank = next((i+1 for i, x in enumerate(by_gainers) if x["code"] == s["code"]), N)
            cross_rank_highlights.append({
                "code": s["code"],
                "name": s["name"],
                "change_pct": s["change_pct"],
                "attention_score": s.get("attention_score", 0),
                "industry_score": s.get("industry_score"),
                "hits": hits,
                "gainer_rank": gainer_rank,
                "amount_rank": rank_amount.get(s["code"], N),
                "turnover_rank": rank_turnover.get(s["code"], N),
                "vr_rank": rank_vr.get(s["code"], N),
                "attention_rank": next((i+1 for i, x in enumerate(market_attention) if x["code"] == s["code"]), len(market_attention)+1),
            })
    cross_rank_highlights.sort(key=lambda x: (-x["hits"], x["attention_rank"]))
    cross_rank_highlights = cross_rank_highlights[:top]

    # 最新数据时间
    data_time = max(fetch_times) if fetch_times else "unknown"

    return {
        "data_time": data_time,
        "top_gainers": top_gainers,
        "top_amount": top_amount,
        "top_turnover": top_turnover,
        "top_vr": top_vr,
        "market_attention": market_attention,
        "cross_rank_highlights": cross_rank_highlights,
        "threshold_gainers": threshold_gainers,
        "threshold_attention": threshold_attention,
    }


def _print_market(data, top=10):
    """打印 market 视图"""
    theme_name = data.get("name", "-")
    industry_leaders = data.get("industry_leaders", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")

    view = _compute_market_view(data, top)

    print(f"Theme: {theme_name}")
    print(f"Stocks: {qualified}/{total} qualified  |  Data Time: {view['data_time']}")
    print()

    # 热点交集（最重要，放最前面）
    if view["cross_rank_highlights"]:
        print(f"--- 热点交集 (Cross-Rank Highlights, Top {len(view['cross_rank_highlights'])}) ---")
        print(f"  同时出现在多个 Top {top} 榜单的股票  |  Atn=关注度  Ind=代表分")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<10} {'涨幅':>8} {'Atn':>6} {'Ind':>5} {'Hits':>4}  Tags")
        print(f"  {'--':>2}  {'----':<10} {'----':<10} {'--------':>8} {'---':>6} {'---':>5} {'----':>4}  ----")
        for i, s in enumerate(view["cross_rank_highlights"], 1):
            gr = s["gainer_rank"]
            ar = s["amount_rank"]
            tr = s["turnover_rank"]
            vr = s["vr_rank"]
            atr = s["attention_rank"]
            ranks = []
            if gr <= top: ranks.append(f"涨{gr}")
            if ar <= top: ranks.append(f"额{ar}")
            if tr <= top: ranks.append(f"换{tr}")
            if vr <= top: ranks.append(f"量{vr}")
            if atr <= top: ranks.append(f"关{atr}")
            atn_str = f"{s['attention_score']:>6.1f}"
            ind_str = f"{s['industry_score']:>5.0f}" if s.get('industry_score') is not None else "   --"
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<10} {s['change_pct']:>+7.2f}% {atn_str} {ind_str} {s['hits']:>4}  {'+'.join(ranks)}")
        print()

    # 主题代表股
    if industry_leaders:
        print(f"--- 主题代表股 (Theme Representatives, Top {min(len(industry_leaders), top)}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Industry':>8}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'--------':>8}")
        for i, il in enumerate(industry_leaders[:top], 1):
            print(f"  {i:>2}  {il.get('code',''):<10} {il.get('name',''):<12} {il.get('industry_score',0):>8.1f}")
        print()

    # 今日强势股（全市场，不限 qualified）
    if view["top_gainers"]:
        print(f"--- 今日强势股 (Today's Strongest, Top {len(view['top_gainers'])}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'涨幅':>8} {'Ind':>5}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'--------':>8} {'---':>5}")
        for i, s in enumerate(view["top_gainers"], 1):
            ind_str = f"{s['industry_score']:>5.0f}" if s.get('industry_score') is not None else "   --"
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<12} {s['change_pct']:>+7.2f}% {ind_str}")
        print()

    # 成交额龙头
    if view["top_amount"]:
        print(f"--- 成交额龙头 (Turnover Leaders, Top {len(view['top_amount'])}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'成交额(亿)':>10}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'----------':>10}")
        for i, s in enumerate(view["top_amount"], 1):
            amount_yi = s["amount"] / 1e8
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<12} {amount_yi:>10.2f}")
        print()

    # 换手龙头
    if view["top_turnover"]:
        print(f"--- 换手龙头 (Turnover Rate Leaders, Top {len(view['top_turnover'])}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'换手率':>8}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'--------':>8}")
        for i, s in enumerate(view["top_turnover"], 1):
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<12} {s['turnover']:>8.2f}%")
        print()

    # 放量观察
    if view["top_vr"]:
        print(f"--- 放量观察 (Volume Expansion, Top {len(view['top_vr'])}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'量比':>6}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'------':>6}")
        for i, s in enumerate(view["top_vr"], 1):
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<12} {s['volume_ratio']:>6.2f}")
        print(f"  (量比仅作观察指标，不直接等同于资金龙头)")
        print()

    # 市场关注股（综合排名）
    if view["market_attention"]:
        print(f"--- 市场关注股 (Market Attention, Top {len(view['market_attention'])}) ---")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Atn':>7} {'Ind':>5} {'AmtRk':>5} {'TrnRk':>5} {'VRRk':>5}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'---':>7} {'---':>5} {'-----':>5} {'-----':>5} {'-----':>5}")
        for i, s in enumerate(view["market_attention"], 1):
            ind_str = f"{s['industry_score']:>5.0f}" if s.get('industry_score') is not None else "   --"
            print(f"  {i:>2}  {s['code']:<10} {s['name']:<12} {s['attention_score']:>7.1f} {ind_str} {s['amount_rank']:>5} {s['turnover_rank']:>5} {s['vr_rank']:>5}")
        print()


def _print_theme(data):
    print(f"Theme: {data.get('name', '-')}")
    concepts = data.get('concepts', [])
    concept_weights = data.get('concept_weights', []) or []
    if concept_weights:
        print(f"Concepts ({len(concept_weights)}):")
        for cw in concept_weights:
            print(f"  {cw.get('name',''):<20} weight: {cw.get('weight',0):.2f}")
    elif concepts:
        print(f"Concepts ({len(concepts)}): {', '.join(concepts)}")
    print(f"Stock Count: {data.get('stock_count', '-')}")
    aliases = data.get('aliases', []) or []
    if aliases:
        print(f"Aliases: {', '.join(str(a) for a in aliases)}")
    keywords = data.get('keywords', []) or []
    if keywords:
        print(f"Keywords: {', '.join(str(k) for k in keywords)}")

    qualified = data.get('qualified_stock_count')
    total = data.get('stock_count', '?')
    if qualified is not None:
        print(f"Qualified: {qualified}/{total} stocks")

    anchors = data.get('anchors', []) or []
    if anchors:
        print(f"Anchors: {', '.join(anchors)}")

    pure = data.get('pure_stocks', []) or []
    if pure:
        show_pure = pure[:10]
        print(f"\nPure Stocks (Top {len(show_pure)}){'  ... and ' + str(len(pure) - 10) + ' more' if len(pure) > 10 else ''}:")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Purity':>7}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'-------':>7}")
        for i, p in enumerate(show_pure, 1):
            print(f"  {i:>2}  {p.get('code',''):<10} {p.get('name',''):<12} {p.get('purity_score',0):>7.1f}")

    industry_leaders = data.get('industry_leaders', []) or []
    if industry_leaders:
        has_anchor = any(l.get('anchor') for l in industry_leaders)
        anchor_hdr = " Anc" if has_anchor else ""
        print(f"\nIndustry Leaders (Top {len(industry_leaders)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Industry':>8} {'Purity':>7} {'Liq':>5} {'MCap':>5}{anchor_hdr}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'--------':>8} {'-------':>7} {'---':>5} {'----':>5}{'-' * len(anchor_hdr)}")
        for i, l in enumerate(industry_leaders, 1):
            anchor_mark = " *" if l.get('anchor') else ""
            print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('industry_score',0):>8.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")

    candidate_stocks = data.get('candidate_stocks', []) or []
    if candidate_stocks:
        print(f"\nCandidate Stocks (Top {len(candidate_stocks)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Cand':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'----':>7} {'-------':>7} {'---':>5} {'----':>5}")
        for i, c in enumerate(candidate_stocks, 1):
            print(f"  {i:>2}  {c.get('code',''):<10} {c.get('name',''):<12} {c.get('candidate_score',0):>7.1f} {c.get('purity_score',0):>7.1f} {c.get('liquidity_score',0):>5.1f} {c.get('market_cap_score',0):>5.1f}")

    stocks = data.get('stocks', []) or []
    print(f"\nAll Stocks ({len(stocks)}): {', '.join(stocks[:20])}")
    if len(stocks) > 20:
        print(f"  ... and {len(stocks) - 20} more")
    print(f"Last Update: {data.get('last_update', '-')}")


def _print_concept(data):
    print(f"Concept: {data.get('name', '-')}")
    print(f"ID: {data.get('id', '-')}")
    source = data.get('source', {})
    if isinstance(source, dict):
        print(f"Source: {source.get('provider', '-')} ({source.get('concept_code', '-')})")
    else:
        print(f"Source: {source}")
    print(f"Stock Count: {data.get('stock_count', '-')}")
    aliases = data.get('aliases', []) or []
    if aliases:
        print(f"Aliases: {', '.join(str(a) for a in aliases)}")
    core = data.get('core_stocks', []) or []
    if core:
        print(f"Core Stocks: {', '.join(core)}")
    stocks = data.get('stocks', []) or []
    print(f"All Stocks ({len(stocks)}): {', '.join(stocks[:20])}")
    if len(stocks) > 20:
        print(f"  ... and {len(stocks) - 20} more")
    print(f"Last Update: {data.get('last_update', '-')}")

    t2c = load_index("theme_to_concept.json")
    for theme_name, concepts in t2c.items():
        if data.get('name') in concepts:
            print(f"Belongs to Theme: {theme_name}")
            break


def _extract_roles(stock_data):
    themes = stock_data.get("themes", []) or []
    tags = []
    for t in themes:
        if isinstance(t, dict):
            if t.get("anchor"):
                tags.append("Anchor")
            if (t.get("industry_score") or 0) >= 50:
                tags.append("IndustryLeader")
            if (t.get("candidate_score") or 0) >= 60:
                tags.append("Candidate")
    if len(themes) >= 2:
        tags.append("MultiTheme")
    seen = set()
    tags = [x for x in tags if not (x in seen or seen.add(x))]
    return {
        "code": stock_data.get("code"),
        "name": stock_data.get("name"),
        "theme_count": len(themes),
        "tags": tags,
    }


def _print_stock_batch(results, roles=False):
    if roles:
        print(f"{'Code':<12} {'Name':<12} {'ThemeCount':>11}  Tags")
        print(f"{'----':<12} {'----':<12} {'-----------':>11}  ----")
        for r in results.values():
            tags = ",".join(r["tags"]) if r["tags"] else "-"
            print(f"{r['code']:<12} {r['name']:<12} {r['theme_count']:>11}  {tags}")
    else:
        for r in results.values():
            _print_stock(r)


def _print_stock(data):
    print(f"Stock: {data.get('code', '')} {data.get('name', '')}")
    print(f"Market: {data.get('market', '-')}")
    print(f"Core Theme: {data.get('core_theme', '-')}")
    print(f"Core Concept: {data.get('core_concept', '-')}")
    themes = data.get('themes', []) or []
    if themes:
        print("\nThemes:")
        for t in themes:
            name = t.get('name', '') if isinstance(t, dict) else str(t)
            weight = t.get('weight', 0) if isinstance(t, dict) else 0
            purity = t.get('purity_score') if isinstance(t, dict) else None
            industry = t.get('industry_score') if isinstance(t, dict) else None
            candidate = t.get('candidate_score') if isinstance(t, dict) else None
            anchor = t.get('anchor') if isinstance(t, dict) else None
            bar = "█" * max(1, int(weight))
            parts = [f"weight:{weight:>5.1f}", bar]
            if purity is not None:
                parts.append(f"pur:{purity:.1f}")
            if industry is not None:
                parts.append(f"ind:{industry:.1f}")
            if candidate is not None:
                parts.append(f"cnd:{candidate:.1f}")
            anchor_str = " [ANCHOR]" if anchor else ""
            print(f"  {name:<20} {' '.join(parts)}{anchor_str}")
    concepts = data.get('concepts', []) or []
    if concepts:
        print(f"\nConcepts ({len(concepts)}):")
        for c in concepts:
            name = c.get('name', '') if isinstance(c, dict) else str(c)
            weight = c.get('weight', 0) if isinstance(c, dict) else 0
            bar = "█" * max(1, int(weight))
            print(f"  {name:<20} weight:{weight:>5.1f} {bar}")
    print(f"\nLast Update: {data.get('last_update', '-')}")


def _print_leaders(data):
    theme_name = data.get("name", "-")
    leaders = data.get("industry_leaders", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")
    anchors = data.get("anchors", []) or []

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")
    if anchors:
        print(f"Anchors: {', '.join(anchors)}")

    if not leaders:
        print("No industry leaders above threshold.")
        return

    print(f"\nIndustry Leaders (Top {len(leaders)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Industry':>8} {'Purity':>7} {'Liq':>5} {'MCap':>5} {'Anc':>3}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'--------':>8} {'-------':>7} {'---':>5} {'----':>5} {'---':>3}")
    for i, l in enumerate(leaders, 1):
        anchor_mark = " *" if l.get("anchor") else ""
        print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('industry_score',0):>8.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")


def _print_pure(data):
    theme_name = data.get("name", "-")
    pure = data.get("pure_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")

    if not pure:
        print("No pure stocks above threshold.")
        return

    print(f"\nPure Stocks (Top {len(pure)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Purity':>7}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'-------':>7}")
    for i, p in enumerate(pure, 1):
        print(f"  {i:>2}  {p.get('code',''):<10} {p.get('name',''):<12} {p.get('purity_score',0):>7.1f}")


def _print_candidates(data):
    theme_name = data.get("name", "-")
    candidates = data.get("candidate_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")

    if not candidates:
        print("No candidate stocks above threshold.")
        return

    print(f"\nCandidate Stocks (Top {len(candidates)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Cand':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'----':>7} {'-------':>7} {'---':>5} {'----':>5}")
    for i, c in enumerate(candidates, 1):
        print(f"  {i:>2}  {c.get('code',''):<10} {c.get('name',''):<12} {c.get('candidate_score',0):>7.1f} {c.get('purity_score',0):>7.1f} {c.get('liquidity_score',0):>5.1f} {c.get('market_cap_score',0):>5.1f}")


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Query theme library")
    subparsers = parser.add_subparsers(dest="command")

    theme_p = subparsers.add_parser("theme", help="Query theme details")
    theme_p.add_argument("name", help="Theme name")
    theme_p.add_argument("--json", action="store_true")

    concept_p = subparsers.add_parser("concept", help="Query concept details")
    concept_p.add_argument("name", help="Concept name")
    concept_p.add_argument("--json", action="store_true")

    stock_p = subparsers.add_parser("stock", help="Query stock themes and concepts")
    stock_p.add_argument("code", help="Stock code(s), comma-separated (e.g., sz000977 or sz002371,sz300604,sh601869)")
    stock_p.add_argument("--json", action="store_true")
    stock_p.add_argument("--roles", action="store_true", help="Output compact role tags only (batch mode by default)")

    kw_p = subparsers.add_parser("keyword", help="Query keyword mapping")
    kw_p.add_argument("word", help="Keyword to search")
    kw_p.add_argument("--json", action="store_true")

    list_p = subparsers.add_parser("list", help="List all themes")
    list_p.add_argument("--top", type=int, default=0, help="Limit results")
    list_p.add_argument("--json", action="store_true")

    stats_p = subparsers.add_parser("stats", help="Show library statistics")
    stats_p.add_argument("--json", action="store_true")

    leaders_p = subparsers.add_parser("leaders", help="Top industry leaders for a theme")
    leaders_p.add_argument("name", help="Theme name")
    leaders_p.add_argument("--top", type=int, default=0, help="Limit results")
    leaders_p.add_argument("--json", action="store_true")

    pure_p = subparsers.add_parser("pure", help="Top pure stocks for a theme")
    pure_p.add_argument("name", help="Theme name")
    pure_p.add_argument("--top", type=int, default=0, help="Limit results")
    pure_p.add_argument("--json", action="store_true")

    candidates_p = subparsers.add_parser("candidates", help="Top candidate stocks for a theme")
    candidates_p.add_argument("name", help="Theme name")
    candidates_p.add_argument("--top", type=int, default=0, help="Limit results")
    candidates_p.add_argument("--json", action="store_true")

    market_p = subparsers.add_parser("market", help="Show market observation view for a theme")
    market_p.add_argument("name", help="Theme name")
    market_p.add_argument("--top", type=int, default=10, help="Limit results per section")
    market_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "theme":
        data = query_theme(args.name)
        if data:
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_theme(data)

    elif args.command == "concept":
        data = query_concept(args.name)
        if data:
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_concept(data)

    elif args.command == "stock":
        codes = [c.strip() for c in args.code.split(",") if c.strip()]

        if len(codes) == 1 and not args.roles:
            data = query_stock(codes[0])
            if data:
                if args.json:
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    _print_stock(data)
        else:
            results = {}
            for code in codes:
                data = query_stock(code)
                if data:
                    if args.roles:
                        results[code] = _extract_roles(data)
                    else:
                        results[code] = data
            if results:
                if args.json:
                    print(json.dumps(results, ensure_ascii=False, indent=2))
                else:
                    _print_stock_batch(results, roles=args.roles)

    elif args.command == "keyword":
        kw, target, level = query_keyword(args.word)
        if args.json:
            print(json.dumps({"keyword": kw, "target": target, "level": level}, ensure_ascii=False, indent=2))
        else:
            if target:
                print(f"Keyword: {kw}")
                print(f"{'Theme' if level == 'theme' else 'Concept'}: {target}")
            else:
                print(f"Keyword not found: {kw}")

    elif args.command == "list":
        themes = list_themes(args.top)
        if args.json:
            print(json.dumps([{"name": n, "stock_count": len(s)} for n, s in themes], ensure_ascii=False, indent=2))
        else:
            print(f"{'Theme':<25} {'Concepts':>10} {'Stocks':>8}")
            print("-" * 45)
            t2c = load_index("theme_to_concept.json")
            for name, stocks in themes:
                concepts = t2c.get(name, [])
                print(f"{name:<25} {len(concepts):>10} {len(stocks):>8}")
            print(f"\nTotal: {len(themes)} themes")

    elif args.command == "stats":
        stats = show_stats()
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print("Theme Library Statistics:")
            print(f"  Themes:            {stats['themes']}")
            print(f"  Concepts (themed): {stats['concepts_themed']}")
            print(f"  Concepts (total):  {stats['concepts_total']}")
            print(f"  Stocks:            {stats['stocks']}")
            print(f"  Keywords:          {stats['keywords']}")

    elif args.command == "leaders":
        data = query_theme(args.name)
        if data:
            leaders = data.get("industry_leaders", []) or []
            if args.top > 0:
                leaders = leaders[:args.top]
                data = dict(data)
                data["industry_leaders"] = leaders
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_leaders(data)

    elif args.command == "pure":
        data = query_theme(args.name)
        if data:
            pure = data.get("pure_stocks", []) or []
            if args.top > 0:
                pure = pure[:args.top]
                data = dict(data)
                data["pure_stocks"] = pure
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_pure(data)

    elif args.command == "candidates":
        data = query_theme(args.name)
        if data:
            candidates = data.get("candidate_stocks", []) or []
            if args.top > 0:
                candidates = candidates[:args.top]
                data = dict(data)
                data["candidate_stocks"] = candidates
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_candidates(data)

    elif args.command == "market":
        data = query_theme(args.name)
        if data:
            if args.json:
                view = _compute_market_view(data, args.top)
                data = dict(data)
                data["market_view"] = view
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_market(data, args.top)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
