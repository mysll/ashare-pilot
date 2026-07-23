#!/usr/bin/env python3
"""Fetch limit-up stock pool from East Money.

Shows stocks that hit their daily limit-up with market data.

Usage:
    python fetch_limit_up_pool.py
    python fetch_limit_up_pool.py --top 50
    python fetch_limit_up_pool.py --json
    python fetch_limit_up_pool.py --json -o limit_up.json
"""

import argparse
import csv
import io
import json
import sys

from pathlib import Path


from ashare_pilot.market_data._datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "code", "name", "price", "change_pct", "turnover",
        "volume_ratio", "amount", "board", "total_mv",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch limit-up stock pool")
    parser.add_argument("--top", type=int, default=50, help="Number of stocks (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args(argv)

    results = _ds.fetch_limit_up_pool(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No limit-up stocks found."
        else:
            lines = []
            lines.append(f"Limit-Up Pool ({len(results)} stocks)")
            lines.append(
                f"{'Code':<12} {'Name':<10} {'Price':>8} {'Change':>8} {'Turnover':>8} {'Board':<8}"
            )
            lines.append("-" * 65)
            for r in results:
                lines.append(
                    f"{r['code']:<12} {r['name']:<10} {r['price']:>8} "
                    f"{r['change_pct']:>8} {r['turnover']:>8} {r['board']:<8}"
                )
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
