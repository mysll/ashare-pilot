#!/usr/bin/env python3
"""Fetch market breadth data from East Money.

Shows: up/down/flat counts, limit-up/limit-down counts,
up ratio, average change.

Usage:
    python fetch_market_breadth.py
    python fetch_market_breadth.py --json
    python fetch_market_breadth.py --json -o breadth.json
    python fetch_market_breadth.py --cache-dir intraday/2026-06-30 --json
"""

import argparse
import json
import os
import sys

from pathlib import Path


from ashare_pilot.market_data._datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch market breadth data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--cache-dir", metavar="DIR", help="Use cached all_stocks data from directory")
    args = parser.parse_args(argv)

    result = _ds.fetch_market_breadth(cache_dir=args.cache_dir)

    if args.json:
        output_str = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        if "error" in result:
            output_str = f"Error: {result['error']}"
        else:
            lines = []
            lines.append("=== Market Breadth ===")
            lines.append(f"Total stocks:     {result['total']}")
            lines.append(f"Up:               {result['up_count']} ({result['up_ratio']}%)")
            lines.append(f"Down:             {result['down_count']}")
            lines.append(f"Flat:             {result['flat_count']}")
            lines.append(f"Limit-Up:         {result['limit_up_count']}")
            lines.append(f"Limit-Down:       {result['limit_down_count']}")
            lines.append(f"Avg Change:       {result['avg_change']}%")
            lines.append(f"Time:             {result['timestamp']}")
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
