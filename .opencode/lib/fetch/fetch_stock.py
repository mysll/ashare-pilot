#!/usr/bin/env python3
"""Fetch real-time stock data from Chinese financial APIs.

Supports: A stocks (sh/sz/bj), HK stocks, US stocks, and futures (nf_/hf_).
Data sources: Sina Finance (A/US/futures), Tencent Finance (HK).

Usage:
    python fetch_stock.py sh000001,sz399001,hk00700,usr_nvda,nf_IF0
    python fetch_stock.py sh600519 --json
    python fetch_stock.py sh600519 --csv -o output.csv
    python fetch_stock.py --search "茅台"
    python fetch_stock.py sh600519 --intraday              # Today's 5-min K-line
    python fetch_stock.py sh600519 --intraday --scale 1    # Today's 1-min K-line
    python fetch_stock.py sh600519 --intraday --days 3     # Last 3 days, 5-min K-line
"""

import argparse
import csv
import io
import json
import re
import sys
from typing import Any

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.datasources import SinaDataSource, TencentDataSource


_sina = SinaDataSource()
_tencent = TencentDataSource()


def fetch_stocks(codes: list) -> list:
    sina_codes = []
    hk_codes = []
    a_codes = []
    for code in codes:
        code = code.strip()
        if not code:
            continue
        if re.match(r"^[A-Z]", code):
            code = f"nf_{code}"
        code = code.replace("cnf_", "nf_")
        if code.startswith("hk"):
            hk_codes.append(code)
        else:
            sina_codes.append(code)
            if re.match(r"^(sh|sz|bj)", code):
                a_codes.append(code)
    results = []
    if sina_codes:
        results.extend(_sina.fetch_quotes(sina_codes))
    if hk_codes:
        results.extend(_tencent.fetch_hk_quotes(hk_codes))
    for r in results:
        code = r.get("code", "")
        r["float_shares"] = (
            _sina.get_float_shares(code) if code in a_codes else None
        )
    return results


def fetch_intraday_kline(code: str, scale: int = 5, days: int = 1) -> list:
    return _sina.fetch_intraday(code, scale, days)


def search_stocks(keyword: str) -> list:
    return _tencent.search_stocks(keyword)


def print_table(results: list) -> None:
    if not results:
        print("No data.")
        return
    for r in results:
        if "error" in r:
            print(f"[{r['code']}] Error: {r['error']}")
            continue
        name = r.get("name", "?")
        code = r.get("code", "?")
        price = r.get("price", "?")
        percent = r.get("percent", "?")
        updown = r.get("updown", "?")
        market = r.get("market", "?")
        time_str = r.get("time", "")
        print(f"[{market}] {code} {name}")
        print(f"  Price: {price}  Change: {updown} ({percent})  Time: {time_str}")
        print()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "code",
        "name",
        "price",
        "open",
        "yestclose",
        "high",
        "low",
        "volume",
        "amount",
        "amount_10000",
        "float_shares",
        "updown",
        "percent",
        "time",
        "market",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def to_csv_output_intraday(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "ma_price5",
        "ma_volume5",
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

    parser = argparse.ArgumentParser(
        description="Fetch real-time stock data from Chinese financial APIs"
    )
    parser.add_argument(
        "codes",
        nargs="?",
        help="Comma-separated stock codes (e.g., sh000001,sz399001,hk00700,usr_nvda)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV format")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--search", metavar="KEYWORD", help="Search stocks by keyword")
    parser.add_argument(
        "--intraday",
        action="store_true",
        help="Fetch intraday K-line data for A stocks",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=5,
        metavar="MINUTES",
        help="Minute interval for intraday K-line",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        metavar="DAYS",
        help="Number of days for intraday K-line",
    )

    args = parser.parse_args()

    if args.search:
        results = search_stocks(args.search)
        if args.json:
            output_str = json.dumps(results, ensure_ascii=False, indent=2)
        else:
            lines = []
            if not results:
                lines.append("No results found.")
            for r in results:
                if "error" in r:
                    lines.append(f"Error: {r['error']}")
                else:
                    lines.append(f"{r['code']} | {r['name']} ({r['market']})")
            output_str = "\n".join(lines)
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output_str)
            print(f"Saved to {args.output}")
        else:
            print(output_str)
        return

    if not args.codes:
        parser.print_help()
        sys.exit(1)

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    if args.intraday:
        if len(codes) > 1:
            print(
                "Warning: Intraday mode only supports single stock. Using first code."
            )
        results = fetch_intraday_kline(codes[0], scale=args.scale, days=args.days)
    else:
        results = fetch_stocks(codes)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        if args.intraday:
            output_str = to_csv_output_intraday(results)
        else:
            output_str = to_csv_output(results)
    else:
        lines = []
        if args.intraday:
            if results and "error" not in results[0]:
                lines.append(
                    f"{'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}"
                )
                lines.append("-" * 75)
                for r in results:
                    time_str = r.get("time", "?")
                    open_p = r.get("open", 0)
                    high = r.get("high", 0)
                    low = r.get("low", 0)
                    close = r.get("close", 0)
                    volume = r.get("volume", 0)
                    if volume >= 10000:
                        vol_str = f"{volume / 10000:.1f}万"
                    else:
                        vol_str = str(volume)
                    lines.append(
                        f"{time_str:<20} {open_p:>10.2f} {high:>10.2f} {low:>10.2f} {close:>10.2f} {vol_str:>12}"
                    )
            else:
                for r in results:
                    if "error" in r:
                        lines.append(f"Error: {r['error']}")
        else:
            for r in results:
                if "error" in r:
                    lines.append(f"[{r['code']}] Error: {r['error']}")
                    continue
                name = r.get("name", "?")
                code = r.get("code", "?")
                price = r.get("price", "?")
                percent = r.get("percent", "?")
                updown = r.get("updown", "?")
                market = r.get("market", "?")
                time_str = r.get("time", "")
                lines.append(f"[{market}] {code} {name}")
                lines.append(
                    f"  Price: {price}  Change: {updown} ({percent})  Time: {time_str}"
                )
                lines.append("")
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
