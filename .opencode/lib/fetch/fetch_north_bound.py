#!/usr/bin/env python3
"""Fetch north-bound capital flow (北向资金) from East Money.

Shows Shanghai-HK Stock Connect and Shenzhen-HK Stock Connect net flows.

Usage:
    python fetch_north_bound.py
    python fetch_north_bound.py --json
    python fetch_north_bound.py --json -o north.json
"""

import argparse
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch north-bound capital flow")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    result = _ds.fetch_north_bound()

    if args.json:
        output_str = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        if "error" in result:
            output_str = f"Error: {result['error']}"
        else:
            lines = []
            lines.append("=== North-Bound Capital (北向资金) ===")
            lines.append(f"沪股通 Buy:     {result['hgt_buy']}亿")
            lines.append(f"沪股通 Sell:    {result['hgt_sell']}亿")
            lines.append(f"沪股通 Net:     {result['hgt_net']}亿")
            lines.append(f"深股通 Buy:     {result['sgt_buy']}亿")
            lines.append(f"深股通 Sell:    {result['sgt_sell']}亿")
            lines.append(f"深股通 Net:     {result['sgt_net']}亿")
            lines.append("---")
            lines.append(f"Total Net:      {result['total_net']}亿")
            lines.append(f"Time:           {result['timestamp']}")
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
