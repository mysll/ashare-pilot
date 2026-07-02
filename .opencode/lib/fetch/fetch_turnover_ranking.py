#!/usr/bin/env python3
"""Fetch top stocks by turnover (成交额) ranking.

Usage:
    python fetch_turnover_ranking.py
    python fetch_turnover_ranking.py --top 100
    python fetch_turnover_ranking.py --json
    python fetch_turnover_ranking.py --csv -o turnover.csv
"""

import argparse
import csv
import io
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "code", "name", "price", "change_pct",
        "amount", "turnover", "volume_ratio", "total_mv",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch turnover ranking")
    parser.add_argument("--top", type=int, default=100, help="Number of stocks (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    results = _ds.fetch_turnover_ranking(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = []
            lines.append(f"Turnover Top {len(results)}")
            lines.append(
                f"{'Code':<12} {'Name':<10} {'Price':>8} {'Change':>8} "
                f"{'Amount':>14} {'Turnover':>8}"
            )
            lines.append("-" * 72)
            for r in results:
                lines.append(
                    f"{r['code']:<12} {r['name']:<10} {r['price']:>8} "
                    f"{r['change_pct']:>8} {r['amount']:>14} {r['turnover']:>8}"
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
