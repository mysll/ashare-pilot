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
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
THEMES_DIR = SKILL_DIR / "themes"
CONCEPTS_DIR = SKILL_DIR / "concepts"
STOCKS_DIR = SKILL_DIR / "stocks"
ALIASES_DIR = SKILL_DIR / "aliases"
INDEX_DIR = SKILL_DIR / "index"
METADATA_DIR = SKILL_DIR / "metadata"


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

    leader_stocks = data.get('leader_stocks', []) or []
    if leader_stocks:
        has_anchor = any(l.get('anchor') for l in leader_stocks)
        anchor_hdr = " Anc" if has_anchor else ""
        print(f"\nLeader Stocks (Top {len(leader_stocks)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Leader':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5}{anchor_hdr}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'------':>7} {'-------':>7} {'---':>5} {'----':>5}{'-' * len(anchor_hdr)}")
        for i, l in enumerate(leader_stocks, 1):
            anchor_mark = " *" if l.get('anchor') else ""
            print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('leader_score',0):>7.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")

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
            leader = t.get('leader_score') if isinstance(t, dict) else None
            candidate = t.get('candidate_score') if isinstance(t, dict) else None
            anchor = t.get('anchor') if isinstance(t, dict) else None
            bar = "█" * max(1, int(weight))
            parts = [f"weight:{weight:>5.1f}", bar]
            if purity is not None:
                parts.append(f"pur:{purity:.1f}")
            if leader is not None:
                parts.append(f"ldr:{leader:.1f}")
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
    leaders = data.get("leader_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")
    anchors = data.get("anchors", []) or []

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")
    if anchors:
        print(f"Anchors: {', '.join(anchors)}")

    if not leaders:
        print("No leader stocks above threshold.")
        return

    print(f"\nLeader Stocks (Top {len(leaders)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Leader':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5} {'Anc':>3}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'------':>7} {'-------':>7} {'---':>5} {'----':>5} {'---':>3}")
    for i, l in enumerate(leaders, 1):
        anchor_mark = " *" if l.get("anchor") else ""
        print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('leader_score',0):>7.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")


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


def main():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(description="Query theme library")
    subparsers = parser.add_subparsers(dest="command")

    theme_p = subparsers.add_parser("theme", help="Query theme details")
    theme_p.add_argument("name", help="Theme name")
    theme_p.add_argument("--json", action="store_true")

    concept_p = subparsers.add_parser("concept", help="Query concept details")
    concept_p.add_argument("name", help="Concept name")
    concept_p.add_argument("--json", action="store_true")

    stock_p = subparsers.add_parser("stock", help="Query stock themes and concepts")
    stock_p.add_argument("code", help="Stock code (e.g., sz000977)")
    stock_p.add_argument("--json", action="store_true")

    kw_p = subparsers.add_parser("keyword", help="Query keyword mapping")
    kw_p.add_argument("word", help="Keyword to search")
    kw_p.add_argument("--json", action="store_true")

    list_p = subparsers.add_parser("list", help="List all themes")
    list_p.add_argument("--top", type=int, default=0, help="Limit results")
    list_p.add_argument("--json", action="store_true")

    stats_p = subparsers.add_parser("stats", help="Show library statistics")
    stats_p.add_argument("--json", action="store_true")

    leaders_p = subparsers.add_parser("leaders", help="Top leader stocks for a theme")
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

    args = parser.parse_args()

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
        data = query_stock(args.code)
        if data:
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_stock(data)

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
            leaders = data.get("leader_stocks", []) or []
            if args.top > 0:
                leaders = leaders[:args.top]
                data = dict(data)
                data["leader_stocks"] = leaders
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

    else:
        parser.print_help()


if __name__ == "__main__":
    main()