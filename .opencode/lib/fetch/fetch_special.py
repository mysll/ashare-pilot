#!/usr/bin/env python3
"""Fetch Dragon and Tiger List (龙虎榜) and Margin Trading (融资融券) data from East Money.

Usage:
    # Dragon and Tiger List (today)
    python fetch_special.py lhb
    python fetch_special.py lhb --date 2026-03-31
    python fetch_special.py lhb --json

    # Margin Trading (latest)
    python fetch_special.py rzye
    python fetch_special.py rzye --top 20
    python fetch_special.py rzye --code sh600519 --json
"""

import argparse
import io
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.datasources import EastMoneyDataSource


_eastmoney = EastMoneyDataSource()


def fetch_lhb(date_str: str = None) -> list:
    return _eastmoney.fetch_lhb(date_str)


def fetch_lhb_stock(code: str, date_str: str = None) -> dict | None:
    return _eastmoney.fetch_lhb_stock(code, date_str)


def fetch_rzye(top: int = 10) -> list:
    return _eastmoney.fetch_rzye(top)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch Dragon and Tiger List (龙虎榜) and Margin Trading (融资融券) data"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    lhb_parser = subparsers.add_parser("lhb", help="Dragon and Tiger List (龙虎榜)")
    lhb_parser.add_argument("--date", help="Date (YYYY-MM-DD), default: today")
    lhb_parser.add_argument("--code", help="Stock code to query specifically")
    lhb_parser.add_argument("--json", action="store_true", help="Output as JSON")
    lhb_parser.add_argument(
        "-o", "--output", metavar="FILE", help="Save output to file"
    )

    rzye_parser = subparsers.add_parser(
        "rzye", help="Margin Trading balance (融资融券)"
    )
    rzye_parser.add_argument(
        "--top", type=int, default=10, help="Number of records (default: 10)"
    )
    rzye_parser.add_argument("--json", action="store_true", help="Output as JSON")
    rzye_parser.add_argument(
        "-o", "--output", metavar="FILE", help="Save output to file"
    )

    args = parser.parse_args()

    if args.command == "lhb":
        if args.code:
            result = fetch_lhb_stock(args.code, args.date)
            if result:
                if args.json:
                    output_str = json.dumps(result, ensure_ascii=False, indent=2)
                else:
                    lines = []
                    lines.append(
                        f"{'Date':<12} {'Code':<8} {'Name':<8} {'Close':>8} {'Chg%':>8} {'NetBuy(亿)':>10} {'Turnover':>8} {'Abnormal'}"
                    )
                    lines.append("-" * 100)
                    close = result.get("close") or 0
                    chg = result.get("change_pct") or 0
                    turnover = result.get("turnover_rate") or 0
                    abnormal = (result.get("abnormal") or "")[:25]
                    lines.append(
                        f"{result['date']:<12} {result['code']:<8} {result['name']:<8} {close:>8.2f} {chg:>7.2f}% {result['net_buy']:>10} {turnover:>7.2f}% {abnormal}"
                    )
                    output_str = "\n".join(lines)
                if args.output:
                    with open(args.output, "w", encoding="utf-8", newline="") as f:
                        f.write(output_str)
                    print(f"Saved to {args.output}")
                else:
                    print(output_str)
            else:
                print("No data found for this stock.")
        else:
            records = fetch_lhb(args.date)
            if args.json:
                output_str = json.dumps(records, ensure_ascii=False, indent=2)
            else:
                lines = []
                if not records:
                    lines.append("No data.")
                else:
                    lines.append(
                        f"{'Date':<12} {'Code':<8} {'Name':<8} {'Close':>8} {'Chg%':>8} {'NetBuy(亿)':>10} {'Turnover':>8} {'Abnormal'}"
                    )
                    lines.append("-" * 100)
                    for r in records:
                        close = r.get("close") or 0
                        chg = r.get("change_pct") or 0
                        turnover = r.get("turnover_rate") or 0
                        abnormal = (r.get("abnormal") or "")[:25]
                        lines.append(
                            f"{r['date']:<12} {r['code']:<8} {r['name']:<8} {close:>8.2f} {chg:>7.2f}% {r['net_buy']:>10} {turnover:>7.2f}% {abnormal}"
                        )
                output_str = "\n".join(lines)
            if args.output:
                with open(args.output, "w", encoding="utf-8", newline="") as f:
                    f.write(output_str)
                print(f"Saved to {args.output}")
            else:
                print(output_str)

    elif args.command == "rzye":
        records = fetch_rzye(args.top)
        if args.json:
            output_str = json.dumps(records, ensure_ascii=False, indent=2)
        else:
            lines = []
            if not records:
                lines.append("No data.")
            else:
                lines.append(
                    f"{'Date':<12} {'Market':<8} {'RZYE(亿)':>12} {'RZMRE(亿)':>10} {'RZJME(亿)':>10} {'RZRQYE(亿)':>12}"
                )
                lines.append("-" * 70)
                for r in records:
                    lines.append(
                        f"{r['date']:<12} {r['market']:<8} {r['rzye']:>12} {r['rzmre']:>10} {r['rzjme']:>10} {r['rzrqye']:>12}"
                    )
            output_str = "\n".join(lines)
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output_str)
            print(f"Saved to {args.output}")
        else:
            print(output_str)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
