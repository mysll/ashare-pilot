#!/usr/bin/env python3
"""Fetch concept board real-time ranking from East Money.

Usage:
    python fetch_concept_ranking.py
    python fetch_concept_ranking.py --top 50
    python fetch_concept_ranking.py --json
    python fetch_concept_ranking.py --csv -o concepts.csv
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
        "code", "name", "change_pct", "up_count", "down_count",
        "lead_stock", "lead_change", "net_inflow", "turnover",
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

    parser = argparse.ArgumentParser(description="Fetch concept board ranking")
    parser.add_argument("--top", type=int, default=50, help="Number of concepts (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args(argv)

    results = _ds.fetch_concept_ranking(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = []
            lines.append(f"Concept Ranking Top {len(results)}")
            lines.append(
                f"{'Name':<16} {'Change':>8} {'Up/Down':>10} "
                f"{'NetFlow(亿)':>12} {'Lead':<10}"
            )
            lines.append("-" * 72)
            for r in results:
                updown = f"{r.get('up_count', 0)}/{r.get('down_count', 0)}"
                lines.append(
                    f"{r['name']:<16} {r['change_pct']:>8} {updown:>10} "
                    f"{r.get('net_inflow', '-'):>12} {r.get('lead_stock', ''):<10}"
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
