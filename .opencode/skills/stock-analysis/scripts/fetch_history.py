#!/usr/bin/env python3
"""Fetch historical stock daily K-line data (前复权).

Supports: A stocks (sh/sz only).
Data sources: Sohu Finance (搜狐财经) / Sina Finance (新浪财经).

Usage:
    python fetch_history.py sh600519                    # Last 3 months (default)
    python fetch_history.py sz000001 --range 1m         # Last 1 month
    python fetch_history.py sh600519 --range 1y --json  # Last 1 year, JSON output
    python fetch_history.py sh600519 --start 20260101 --end 20260331
    python fetch_history.py sh600519 --source sina      # Use Sina as data source
"""

import argparse
import io
import json
import sys
from typing import Any

from datasources import SohuDataSource, SinaDataSource


_sohu = SohuDataSource()
_sina = SinaDataSource()


def fetch_history(
    stock_code: str, start: str = None, end: str = None, range_str: str = "3m",
    use_cache: bool = True, source: str = "sohu",
) -> list:
    if source == "sina":
        return _sina.fetch_daily_history(stock_code, range_str, use_cache=use_cache) or []
    return _sohu.fetch_history(stock_code, start, end, range_str, use_cache=use_cache)


def print_table(records: list, stock_code: str) -> None:
    if not records:
        print("No data.")
        return
    print(f"Stock: {stock_code}  Records: {len(records)}")
    print(
        f"{'Date':<12} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10} {'Change%':>10} {'Volume':>14}"
    )
    print("-" * 80)
    for r in records:
        print(
            f"{r['date']:<12} {r['open']:>10} {r['close']:>10} {r['high']:>10} {r['low']:>10} {r['change_pct']:>10} {r['volume']:>14}"
        )


def to_csv(records: list, stock_code: str) -> str:
    if not records:
        return ""
    lines = ["date,open,close,high,low,change,change_pct,volume,amount"]
    for r in records:
        lines.append(
            f"{r['date']},{r['open']},{r['close']},{r['high']},{r['low']},{r['change']},{r['change_pct']},{r['volume']},{r['amount']}"
        )
    return "\n".join(lines)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch historical stock daily K-line data (前复权)"
    )
    parser.add_argument("code", help="Stock code (sh/sz only, e.g., sh600519)")
    parser.add_argument(
        "--range",
        choices=["1y", "6m", "3m", "1m", "1w"],
        default="3m",
        help="Time range",
    )
    parser.add_argument("--start", help="Start date (YYYYMMDD), overrides --range")
    parser.add_argument("--end", help="End date (YYYYMMDD), default: today")
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch directly from API")
    parser.add_argument(
        "--source", choices=["sohu", "sina"], default="sohu",
        help="Data source (default: sohu)"
    )

    args = parser.parse_args()

    records = fetch_history(args.code, args.start, args.end, args.range,
                            use_cache=not args.no_cache, source=args.source)

    if args.json:
        output_str = json.dumps(records, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv(records, args.code)
    else:
        if not records:
            output_str = "No data."
        else:
            lines = [f"Stock: {args.code}  Records: {len(records)}"]
            lines.append(
                f"{'Date':<12} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10} {'Change%':>10} {'Volume':>14}"
            )
            lines.append("-" * 80)
            for r in records:
                lines.append(
                    f"{r['date']:<12} {r['open']:>10} {r['close']:>10} {r['high']:>10} {r['low']:>10} {r['change_pct']:>10} {r['volume']:>14}"
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
