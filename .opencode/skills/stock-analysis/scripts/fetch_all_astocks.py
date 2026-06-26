#!/usr/bin/env python3
"""Fetch all A stock real-time data from Chinese financial APIs.

Supports two data sources:
1. Eastmoney (default) - includes volume ratio (量比)
2. Sina Finance (fallback) - no volume ratio

Usage:
    python fetch_all_astocks.py                      # Table output (Eastmoney)
    python fetch_all_astocks.py -o stocks.csv        # Save as CSV (default)
    python fetch_all_astocks.py -o stocks.json --json-output  # Save as JSON
    python fetch_all_astocks.py --json               # Print JSON to stdout
    python fetch_all_astocks.py --source sina        # Force use Sina source
"""

import argparse
import csv
import io
import json
import sys

from datasources import SinaDataSource, EastMoneyDataSource


_sina = SinaDataSource()
_eastmoney = EastMoneyDataSource()


def fetch_all_astocks(source: str = "eastmoney") -> list:
    if source == "sina":
        print("Fetching from Sina (no volume ratio)...")
        results = _sina.fetch_all_stocks()
        print(f"Fetched {len(results)} stocks from Sina")
    else:
        print("Fetching from Eastmoney (with volume ratio)...")
        results = _eastmoney.fetch_all_stocks()
        if len(results) < 1000:
            print(
                f"Eastmoney returned only {len(results)} stocks, falling back to Sina..."
            )
            results = _sina.fetch_all_stocks()
            print(f"Fetched {len(results)} stocks from Sina (fallback)")
        else:
            print(f"Fetched {len(results)} stocks from Eastmoney")
    return results


def print_summary(results: list) -> None:
    if not results:
        print("No data fetched.")
        return
    up = sum(1 for r in results if r.get("percent", "").startswith("+"))
    down = sum(1 for r in results if r.get("percent", "").startswith("-"))
    flat = len(results) - up - down
    avg_percent = 0
    try:
        percents = [
            float(r.get("percent", "0%").replace("%", "").replace("+", ""))
            for r in results
        ]
        avg_percent = sum(percents) / len(percents) if percents else 0
    except:
        pass
    print(f"\n{'=' * 60}")
    print(f"全A股实时行情 ({len(results)} 只)")
    print(f"{'=' * 60}")
    print(f"上涨: {up} 下跌: {down} 平盘: {flat}")
    print(f"平均涨跌幅: {avg_percent:+.2f}%")
    print(f"{'=' * 60}\n")
    valid_results = [
        r
        for r in results
        if r.get("percent") and r["percent"] not in ("0.00%", "-0.00%")
    ]
    sorted_by_pct = sorted(
        valid_results,
        key=lambda x: float(x.get("percent", "0%").replace("%", "").replace("+", "")),
        reverse=True,
    )
    print("涨幅前10:")
    print("-" * 50)
    for r in sorted_by_pct[:10]:
        print(f"{r['code']} {r['name']}: {r['percent']} ({r['updown']})")
    print("\n跌幅前10:")
    print("-" * 50)
    for r in sorted_by_pct[-10:]:
        print(f"{r['code']} {r['name']}: {r['percent']} ({r['updown']})")


def save_csv(results: list, filepath: str) -> None:
    if not results:
        return
    fieldnames = [
        "code",
        "name",
        "price",
        "yestclose",
        "updown",
        "percent",
        "high",
        "low",
        "open",
        "volume",
        "amount",
        "turnover",
        "volume_ratio",
        "swing",
        "pe",
        "pb",
        "total_mv",
        "float_mv",
        "market",
        "source",
    ]
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch all A stock real-time data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "-o", "--output", metavar="FILE", help="Save to file (CSV by default)"
    )
    parser.add_argument(
        "--json-output", action="store_true", help="Save as JSON instead of CSV"
    )
    parser.add_argument(
        "--source",
        choices=["eastmoney", "sina"],
        default="sina",
        help="Data source: eastmoney (has volume ratio), sina (no volume ratio)",
    )

    args = parser.parse_args()

    results = fetch_all_astocks(source=args.source)

    if not results:
        print("No data fetched. API may be rate-limited.")
        sys.exit(1)

    sources = set(r.get("source", "unknown") for r in results)
    print(f"Data source: {', '.join(sources)}")

    if args.output:
        if args.json_output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        else:
            save_csv(results, args.output)
        print(f"Saved to {args.output}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_summary(results)


if __name__ == "__main__":
    main()
