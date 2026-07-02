#!/usr/bin/env python3
"""Compute Theme Ranking from Compute Pool via theme library lookups.

Implements the V1 Theme Heat formula (intraday-stock-discovery SKILL.md):
    Heat = Breadth(20%) + Leader(30%) + Capital(25%) + Momentum(15%) + Continuation(10%)

Usage:
    python compute_theme_ranking.py compute_pool_enriched.json -o theme_ranking.md
    python compute_theme_ranking.py compute_pool_enriched.json --json -o theme_ranking.json
    python compute_theme_ranking.py compute_pool_enriched.json --pool-cutoff 50 --top-n 20
"""

import argparse
import json
import sys
from pathlib import Path

_OPN_CODE = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_OPN_CODE / "skills" / "theme-library" / "scripts"))

from query_theme import query_stock  # noqa: E402


def compute_theme_ranking(input_data: dict, pool_cutoff: int = 40) -> list:
    pool = input_data.get("compute_pool", input_data)
    if not isinstance(pool, list):
        pool = []
    if not pool:
        return []

    pool.sort(
        key=lambda x: x.get("quick_score", 0) or x.get("overnight_score", 0) or 0,
        reverse=True,
    )
    top = pool[:pool_cutoff]

    all_themes = {}
    for stk in top:
        code = stk["code"]
        name = stk.get("name", "")

        cp = stk.get("change_pct", "0%")
        change_val = float(str(cp).replace("+", "").replace("%", ""))

        enriched = stk.get("enriched", {})
        mf = enriched.get("money_flow", {})
        try:
            inflow = float(mf.get("main_net_inflow", "0.00"))
        except (ValueError, TypeError):
            inflow = 0.0

        stock_data = query_stock(code)
        if not stock_data:
            continue

        for t in stock_data.get("themes", []):
            tn = t.get("name", "") if isinstance(t, dict) else str(t)
            if not tn:
                continue
            if tn not in all_themes:
                all_themes[tn] = []
            all_themes[tn].append({
                "code": code, "name": name,
                "change_pct": change_val,
                "main_net_inflow": inflow,
            })

    scores = []
    for theme, stocks in all_themes.items():
        n = len(stocks)
        lc = max(s["change_pct"] for s in stocks)
        ls = max(stocks, key=lambda s: s["change_pct"])
        ti = sum(s["main_net_inflow"] for s in stocks)
        ac = sum(s["change_pct"] for s in stocks) / n if n > 0 else 0.0
        scores.append({
            "theme": theme, "count": n,
            "leader_change": lc, "leader_code": ls["code"],
            "leader_name": ls["name"], "total_inflow": ti,
            "avg_change": ac,
        })

    if not scores:
        return []

    max_count = max(s["count"] for s in scores) or 1
    max_lc = max(abs(s["leader_change"]) for s in scores) or 1
    max_ti = max(abs(s["total_inflow"]) for s in scores) or 1
    min_ac = min(s["avg_change"] for s in scores)
    max_ac = max(s["avg_change"] for s in scores)
    ac_range = max_ac - min_ac or 1

    for s in scores:
        bn = s["count"] / max_count
        ln = abs(s["leader_change"]) / max_lc
        cn = abs(s["total_inflow"]) / max_ti
        mn = (s["avg_change"] - min_ac) / ac_range
        s["heat"] = bn * 20 + ln * 30 + cn * 25 + mn * 15 + 10

    scores.sort(key=lambda x: x["heat"], reverse=True)
    return scores


def format_markdown(scores: list, top_n: int = 15, date: str = "") -> str:
    top = scores[:top_n]
    lines = []
    header = f"## Theme Ranking ({date} 14:30)" if date else "## Theme Ranking"
    lines.append(header)
    lines.append("")
    lines.append("基于ComputePool个股的Bottom-Up统计聚合（股票→主题），各维度热度排名")
    lines.append("")

    lines.append("| # | 主题 | 热度 | 池内个股数 | 平均涨幅 | 领涨股 | 领涨涨幅 | 主力净流入(亿) |")
    lines.append("|---|------|------|-----------|---------|--------|---------|---------------|")
    for i, s in enumerate(top):
        lines.append(
            f"| {i+1} | {s['theme']} | {s['heat']:.1f} | {s['count']} | "
            f"{s['avg_change']:+.2f}% | {s['leader_name']} | "
            f"{s['leader_change']:+.2f}% | {s['total_inflow']:+.2f} |"
        )

    if not scores:
        return "\n".join(lines)

    _max_count = max(s["count"] for s in scores) or 1
    _max_lc = max(abs(s["leader_change"]) for s in scores) or 1
    _max_ti = max(abs(s["total_inflow"]) for s in scores) or 1
    _min_ac = min(s["avg_change"] for s in scores)
    _max_ac = max(s["avg_change"] for s in scores)
    _ac_range = _max_ac - _min_ac or 1

    lines.append("")
    lines.append("### 热度分项构成")
    lines.append("")
    lines.append("| # | 主题 | 总热度 | 广度(20%) | 领涨力(30%) | 资金(25%) | 动量(15%) | 持续性(10%) |")
    lines.append("|---|------|--------|----------|------------|----------|----------|------------|")
    for i, s in enumerate(top):
        bn_pct = (s["count"] / _max_count) * 20
        ln_pct = (abs(s["leader_change"]) / _max_lc) * 30
        cn_pct = (abs(s["total_inflow"]) / _max_ti) * 25
        mn_pct = ((s["avg_change"] - _min_ac) / _ac_range) * 15
        lines.append(
            f"| {i+1} | {s['theme']} | {s['heat']:.1f} | "
            f"{bn_pct:.1f} | {ln_pct:.1f} | {cn_pct:.1f} | {mn_pct:.1f} | 10.0 |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*本文件为Perception层输出，不含交易推荐*")
    return "\n".join(lines)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Compute Theme Ranking from Compute Pool via theme library"
    )
    parser.add_argument("input", help="Path to compute_pool_enriched.json")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--pool-cutoff", type=int, default=40,
                        help="Top N stocks from pool to analyze (default: 40)")
    parser.add_argument("--top-n", type=int, default=15,
                        help="Top N themes to output (default: 15)")
    parser.add_argument("--date", help="Date string for markdown header")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    scores = compute_theme_ranking(data, pool_cutoff=args.pool_cutoff)

    if args.json:
        result_top = scores[:args.top_n] if args.top_n else scores
        output = json.dumps({
            "theme_ranking": result_top,
            "total_themes": len(scores),
        }, ensure_ascii=False, indent=2)
    else:
        date = args.date or ""
        output = format_markdown(scores, top_n=args.top_n, date=date)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
