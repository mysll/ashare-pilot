#!/usr/bin/env python3
"""Fetch board-level money flow data from East Money.

Supports concept board (概念板块) and industry sector (行业板块) money flow
via the bkzj/getbkzj API. Default field is f174.

Usage:
    python fetch_board_money_flow.py concept                    # Concept board f174 flow, top 10
    python fetch_board_money_flow.py concept --field f62        # 主力净流入
    python fetch_board_money_flow.py industry --top 20          # Industry top 20
    python fetch_board_money_flow.py concept --json             # JSON output
    python fetch_board_money_flow.py industry --csv -o flow.csv # CSV to file
"""

import argparse
import csv
import io
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.datasources import EastMoneyDataSource

_ds = EastMoneyDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = ["code", "name", "value", "field", "board_type"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch board-level money flow")
    parser.add_argument(
        "board", choices=["concept", "industry"],
        help="Board type: concept (概念板块) or industry (行业板块)",
    )
    parser.add_argument(
        "--field", default="f174",
        help="Sort field (default: f174; f62=主力净流入)",
    )
    parser.add_argument("--top", type=int, default=20, help="Number of results (default: 20)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    results = _ds.fetch_board_money_flow_by_field(
        field=args.field, board_type=args.board, top=args.top,
    )

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No data."
        else:
            label = "Concept Board" if args.board == "concept" else "Industry Sector"
            lines = []
            lines.append(f"{label} Money Flow (field={args.field}, top {len(results)})")
            lines.append(f"{'Name':<20} {'Code':<10} {'Flow(亿)':>10}")
            lines.append("-" * 44)
            for r in results:
                lines.append(
                    f"{r['name']:<20} {r['code']:<10} {r['value']:>10}"
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
