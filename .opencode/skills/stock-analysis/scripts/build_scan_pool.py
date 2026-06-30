#!/usr/bin/env python3
"""Build Scan Pool from multiple sources and produce QuickScore.

Pipeline:
    1. Fetch from 4 sources (limit-up, turnover, gain range, concept leads)
    2. Merge + deduplicate → Scan Pool (300-500)
    3. Compute QuickScore → top N → Compute Pool candidates (80-150)

Usage:
    python build_scan_pool.py --json -o scan_pool.json
    python build_scan_pool.py --compute-pool-size 120 --json
"""

import argparse
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def build_scan_pool() -> list:
    seen = set()
    pool = []

    def add_stocks(stocks, source_label):
        for s in stocks:
            code = s.get("code", "")
            if not code or code in seen:
                continue
            seen.add(code)
            s["source_pool"] = source_label
            pool.append(s)

    limit_up = _ds.fetch_limit_up_pool(top=100)
    add_stocks(limit_up, "limit_up")

    turnover = _ds.fetch_turnover_ranking(top=200)
    add_stocks(turnover, "turnover")

    all_gainers = _ds.fetch_scan_stocks(top=500)
    for s in all_gainers:
        change_str = s.get("change_pct", "0%")
        try:
            chg = float(change_str.replace("%", "").replace("+", ""))
        except (ValueError, TypeError):
            chg = 0.0
        if 2.0 <= chg <= 9.0:
            if s.get("code") not in seen:
                s["source_pool"] = "gain_range"
                add_stocks([s], "gain_range")

    return pool


def compute_quick_score(pool: list) -> list:
    scored = []
    for s in pool:
        change_str = s.get("change_pct", "0%")
        try:
            chg = float(change_str.replace("%", "").replace("+", ""))
        except (ValueError, TypeError):
            chg = 0.0

        amount_str = s.get("amount", "0")
        try:
            amt = float(amount_str)
        except (ValueError, TypeError):
            amt = 0.0

        turnover_str = s.get("turnover", "0%")
        try:
            tn = float(str(turnover_str).replace("%", ""))
        except (ValueError, TypeError):
            tn = 0.0

        vol_ratio_str = s.get("volume_ratio", "0")
        try:
            vr = float(vol_ratio_str)
        except (ValueError, TypeError):
            vr = 1.0

        market_align = 0.40
        if s.get("source_pool") == "limit_up":
            market_align = 1.0
        elif s.get("source_pool") == "turnover":
            market_align = 0.7
        elif s.get("source_pool") == "gain_range":
            market_align = 0.5

        cap_score = min(tn / 20.0, 1.0)

        if 2.0 <= chg <= 5.0:
            momentum = 1.0
        elif 5.0 < chg <= 7.0:
            momentum = 0.8
        elif 0 < chg < 2.0:
            momentum = 0.5
        else:
            momentum = 0.3

        tail_bonus = min(vr / 3.0, 1.0) if vr > 1.0 else 0.5

        quick_score = round(
            market_align * 35 + cap_score * 25 + momentum * 25 + tail_bonus * 15, 1
        )
        s["quick_score"] = quick_score
        scored.append(s)

    scored.sort(key=lambda x: x.get("quick_score", 0), reverse=True)
    return scored


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build Scan Pool and Compute Pool")
    parser.add_argument(
        "--compute-pool-size", type=int, default=120,
        help="Compute Pool size (default: 120)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    print("Building Scan Pool from multiple sources...", file=sys.stderr)
    scan_pool = build_scan_pool()
    print(f"Scan Pool: {len(scan_pool)} stocks", file=sys.stderr)

    print("Computing QuickScore...", file=sys.stderr)
    scored = compute_quick_score(scan_pool)

    compute_pool = scored[:args.compute_pool_size]
    print(f"Compute Pool: {len(compute_pool)} stocks", file=sys.stderr)

    output = {
        "scan_pool_size": len(scan_pool),
        "compute_pool_size": len(compute_pool),
        "compute_pool": compute_pool,
    }

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
