#!/usr/bin/env python3
"""Build multi-dimensional concept dashboard for intraday overnight pipeline.

Replaces single-dimension concept_ranking.json with a structured Dashboard
containing 4 ranking dimensions (Performance, Capital, Breadth, Momentum)
and a weighted Composite score.

Dimensions:
    Performance  — sort by change_pct (today's market recognition)
    Capital      — sort by net_inflow (sustained buying pressure)
    Breadth      — sort by up_count (sector resonance vs single-stock)
    Momentum     — sort by limit_up count (strengthening vs fading)
    Composite    — weighted percentile blend (Capital 35%, Breadth 25%,
                    Momentum 25%, Performance 15%)

Usage:
    python build_concept_dashboard.py
    python build_concept_dashboard.py --top 100
    python build_concept_dashboard.py --json -o concept_dashboard.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
THEME_INDEX = PROJECT_ROOT / ".opencode" / "skills" / "theme-library" / "index"

sys.path.insert(0, str(PROJECT_ROOT / ".opencode" / "skills" / "stock-analysis" / "scripts"))
from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()

WEIGHTS = {
    "capital": 0.35,
    "breadth": 0.25,
    "momentum": 0.25,
    "performance": 0.15,
}


def load_concept_to_stock() -> dict:
    index_file = THEME_INDEX / "concept_to_stock.json"
    if not index_file.exists():
        return {}
    with open(index_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_lianban_set(concept_to_stock: dict) -> set:
    stocks = concept_to_stock.get("昨日连板", [])
    stocks += concept_to_stock.get("昨日连板_含一字", [])
    return set(stocks)


def parse_change_pct(value: str) -> float:
    if not value or value == "-":
        return 0.0
    return float(value.replace("%", "").replace("+", ""))


def parse_net_inflow(value: str) -> float:
    if not value or value == "-":
        return 0.0
    return float(value)


def percentile_rank(values: list, ascending: bool = True) -> list:
    """Compute percentile rank (0-100) for each value in list.
    
    ascending=True: higher value → higher rank (e.g. net_inflow)
    ascending=False: lower = better (unused currently, kept for symmetry)
    """
    if not values:
        return []
    n = len(values)
    indexed = [(v, i) for i, v in enumerate(values)]
    indexed.sort(key=lambda x: x[0], reverse=ascending)
    ranks = [0.0] * n
    for rank_pos, (_, original_idx) in enumerate(indexed):
        ranks[original_idx] = round((1.0 - rank_pos / n) * 100, 1)
    return ranks


def ordinal_rank(values: list, ascending: bool = True) -> list:
    """Compute ordinal rank (1-based) with tie handling (min-rank method).
    
    Tied values share the same rank. E.g. [10, 10, 5, 3] → [1, 1, 3, 4].
    """
    if not values:
        return []
    n = len(values)
    indexed = [(v, i) for i, v in enumerate(values)]
    indexed.sort(key=lambda x: x[0], reverse=ascending)
    ranks = [0] * n
    prev_val = None
    prev_rank = 0
    for pos, (val, orig_idx) in enumerate(indexed):
        if val != prev_val:
            prev_rank = pos + 1
            prev_val = val
        ranks[orig_idx] = prev_rank
    return ranks


def fetch_limit_up_stocks(top: int = 500, all_stocks: list = None) -> set:
    """Fetch today's limit-up stock codes."""
    limit_up_pool = _ds.fetch_limit_up_pool(top=top, all_stocks=all_stocks)
    return {s["code"] for s in limit_up_pool}


def compute_momentum(concepts: list, concept_to_stock: dict, lianban_set: set, all_stocks: list = None) -> list:
    """Compute Momentum dimension per concept board.

    For each concept:
      limit_up_stocks = today's limit_up ∩ concept_members
      涨停_count = len(limit_up_stocks)
      连板_count = len(limit_up_stocks ∩ 昨日连板)
      首板_count = 涨停_count - 连板_count
      momentum_raw = 涨停 × 0.5 + 首板 × 0.3 + 连板 × 0.2
    """
    limit_up_codes = fetch_limit_up_stocks(all_stocks=all_stocks)
    momentum_list = []

    for concept in concepts:
        name = concept["name"]
        member_stocks = set(concept_to_stock.get(name, []))
        limit_up_in = limit_up_codes & member_stocks
        zt_count = len(limit_up_in)
        lb_count = len(limit_up_in & lianban_set)
        fb_count = zt_count - lb_count
        raw = zt_count * 0.5 + fb_count * 0.3 + lb_count * 0.2
        momentum_list.append({
            "raw": round(raw, 2),
            "limit_up": zt_count,
            "first_board": fb_count,
            "continued_board": lb_count,
            "member_count": len(member_stocks),
        })

    return momentum_list


def build_dashboard(top: int = 100, cache_dir: str = None) -> dict:
    concepts = _ds.fetch_concept_ranking(top=top)
    if not concepts:
        return {"error": "No concept data", "themes": {}, "rankings": {}}

    all_stocks = None
    if cache_dir:
        all_stocks = _ds.fetch_all_astocks(cache_dir=cache_dir)

    concept_to_stock = load_concept_to_stock()
    lianban_set = load_lianban_set(concept_to_stock)

    momentum_data = compute_momentum(concepts, concept_to_stock, lianban_set, all_stocks=all_stocks)

    perf_values = [parse_change_pct(c["change_pct"]) for c in concepts]
    capit_values = [parse_net_inflow(c["net_inflow"]) for c in concepts]
    breadth_values = [c.get("up_count", 0) for c in concepts]
    moment_values = [m["raw"] for m in momentum_data]

    perf_ranks = ordinal_rank(perf_values)
    capit_ranks = ordinal_rank(capit_values)
    breadth_ranks = ordinal_rank(breadth_values)
    moment_ranks = ordinal_rank(moment_values)

    perf_pct = percentile_rank(perf_values)
    capit_pct = percentile_rank(capit_values)
    breadth_pct = percentile_rank(breadth_values)
    moment_pct = percentile_rank(moment_values)

    composite_scores = []
    for i in range(len(concepts)):
        score = (
            capit_pct[i] * WEIGHTS["capital"]
            + breadth_pct[i] * WEIGHTS["breadth"]
            + moment_pct[i] * WEIGHTS["momentum"]
            + perf_pct[i] * WEIGHTS["performance"]
        )
        composite_scores.append(round(score, 1))

    composite_ranks = ordinal_rank(composite_scores)

    themes = {}
    for i, c in enumerate(concepts):
        md = momentum_data[i]
        themes[c["code"]] = {
            "code": c["code"],
            "name": c["name"],
            "performance": {"rank": perf_ranks[i], "value": c["change_pct"]},
            "capital": {"rank": capit_ranks[i], "value": c["net_inflow"]},
            "breadth": {"rank": breadth_ranks[i], "value": c["up_count"]},
            "momentum": {
                "rank": moment_ranks[i],
                "value": md["raw"],
                "limit_up": md["limit_up"],
                "first_board": md["first_board"],
                "continued_board": md["continued_board"],
            },
            "composite": {"rank": composite_ranks[i], "score": composite_scores[i]},
            "details": {
                "change_pct": c["change_pct"],
                "change_amt": c.get("change_amt", "-"),
                "net_inflow": c["net_inflow"],
                "up_count": c["up_count"],
                "down_count": c["down_count"],
                "lead_stock": c.get("lead_stock", ""),
                "lead_change": c.get("lead_change", ""),
                "turnover": c.get("turnover", "-"),
                "total_mv": c.get("total_mv", "-"),
            },
        }

    def build_sorted_list(field: str, key: str = None):
        items = []
        for i, c in enumerate(concepts):
            entry = {
                "code": c["code"],
                "name": c["name"],
                "rank": themes[c["code"]][field]["rank"],
                "value": themes[c["code"]][field]["value"],
            }
            items.append(entry)
        items.sort(key=lambda x: x["rank"])
        return items

    rankings = {
        "performance": build_sorted_list("performance"),
        "capital": build_sorted_list("capital"),
        "breadth": build_sorted_list("breadth"),
        "momentum": build_sorted_list("momentum"),
        "composite": [
            {
                "code": c["code"],
                "name": c["name"],
                "rank": themes[c["code"]]["composite"]["rank"],
                "score": themes[c["code"]]["composite"]["score"],
            }
            for c in sorted(concepts, key=lambda x: themes[x["code"]]["composite"]["rank"])
        ],
    }

    return {
        "meta": {
            "ranking_count": len(concepts),
            "weights": dict(WEIGHTS),
            "timestamp": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "themes": themes,
        "rankings": rankings,
    }


def to_table(results: dict, top_n: int = 15) -> str:
    themes = results.get("themes", {})
    comp_sorted = results.get("rankings", {}).get("composite", [])
    lines = []
    lines.append(f"{'Theme':<16} {'Perf':>5} {'Capital':>8} {'Breadth':>8} {'Momentum':>9} {'Composite':>10}")
    lines.append("-" * 62)
    for entry in comp_sorted[:top_n]:
        code = entry["code"]
        t = themes.get(code, {})
        p_rank = t.get("performance", {}).get("rank", "-")
        c_rank = t.get("capital", {}).get("rank", "-")
        b_rank = t.get("breadth", {}).get("rank", "-")
        m_rank = t.get("momentum", {}).get("rank", "-")
        comp = t.get("composite", {})
        lines.append(
            f"{entry['name']:<16} {str(p_rank):>5} {str(c_rank):>8} "
            f"{str(b_rank):>8} {str(m_rank):>9} "
            f"{comp.get('rank','-')}({comp.get('score','-')})"
        )
    return "\n".join(lines)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build concept dashboard with multi-dimension rankings")
    parser.add_argument("--top", type=int, default=100, help="Number of concepts to rank (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--cache-dir", metavar="DIR", help="Use cached all_stocks data from directory")
    args = parser.parse_args()

    results = build_dashboard(top=args.top, cache_dir=args.cache_dir)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        output_str = to_table(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
