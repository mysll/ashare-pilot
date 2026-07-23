#!/usr/bin/env python3
"""Fetch historical stock daily K-line data (前复权).

Supports: A stocks (sh/sz only).
Data sources: Sohu Finance (搜狐财经), with Sina Finance (新浪财经) fallback.

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
from datetime import date, datetime
from pathlib import Path
from typing import Any


from ashare_pilot.market_data._datasources import SohuDataSource, SinaDataSource
from ashare_pilot.market_data._datasources.utils import RANGE_PATTERN, parse_range_days
from ashare_pilot.market_data.trading_calendar import expected_latest_bar
_sohu = SohuDataSource()
_sina = SinaDataSource()


def _dashed(value: str | None) -> str | None:
    if value and len(value) == 8 and "-" not in value:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _filter_dates(records: list, start: str = None, end: str = None) -> list:
    start_date = _dashed(start)
    end_date = _dashed(end)
    return [
        row for row in records
        if (not start_date or row["date"] >= start_date)
        and (not end_date or row["date"] <= end_date)
    ]


def _sina_range(start: str, range_str: str) -> str:
    """Ensure Sina fetches far enough back for an explicit start date."""
    if not start:
        return range_str
    try:
        start_date = datetime.strptime(_dashed(start), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return range_str
    required_days = max(1, (date.today() - start_date).days + 1)
    return f"{max(required_days, parse_range_days(range_str))}d"


def _needs_fallback(records: list, start: str = None, end: str = None) -> bool:
    """Detect an empty or stale Sohu result using A-share sessions."""
    if not records:
        return True
    try:
        expected = expected_latest_bar(_dashed(end))
    except (TypeError, ValueError):
        return False
    start_date = _dashed(start)
    if start_date and expected.isoformat() < start_date:
        return False
    return max(row["date"] for row in records) < expected.isoformat()


def fetch_history(
    stock_code: str, start: str = None, end: str = None, range_str: str = "3m",
    use_cache: bool = True, source: str = "sohu",
) -> list:
    if source == "sina":
        records = _sina.fetch_daily_history(
            stock_code, _sina_range(start, range_str), use_cache=use_cache
        ) or []
        return _filter_dates(records, start, end)

    # Do not ask the daily endpoint for bars that should not exist yet (before
    # the publication cutoff or during an exchange holiday).
    effective_end = expected_latest_bar(_dashed(end)).strftime("%Y%m%d")
    primary = _sohu.fetch_history(
        stock_code, start, effective_end, range_str, use_cache=use_cache
    ) or []
    if not _needs_fallback(primary, start, end):
        return primary

    fallback = _sina.fetch_daily_history(
        stock_code, _sina_range(start, range_str), use_cache=use_cache
    ) or []
    fallback = _filter_dates(fallback, start, end)
    if not fallback:
        return primary
    if not primary:
        return fallback
    # Never splice vendors in one adjusted-price series. Use the complete Sina
    # series only when it advances beyond the stale Sohu series.
    if max(row["date"] for row in fallback) > max(
        row["date"] for row in primary
    ):
        return fallback
    return primary


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


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch historical stock daily K-line data (前复权)"
    )
    parser.add_argument("code", help="Stock code (sh/sz only, e.g., sh600519)")
    parser.add_argument(
        "--range",
        type=lambda value: value.lower() if RANGE_PATTERN.fullmatch(value) else parser.error(
            "--range must be a positive integer followed by d, w, m, or y (for example: 5d, 2w, 3m, 1y)"
        ),
        default="3m",
        help="Time range: positive integer + d/w/m/y (for example: 5d, 2w, 3m, 1y)",
    )
    parser.add_argument("--start", help="Start date (YYYYMMDD), overrides --range")
    parser.add_argument("--end", help="End date (YYYYMMDD), default: today")
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch directly from API")
    parser.add_argument(
        "--source", choices=["sohu", "sina"], default="sohu",
        help="Primary data source (default: sohu; automatically falls back to sina)"
    )

    args = parser.parse_args(argv)

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
