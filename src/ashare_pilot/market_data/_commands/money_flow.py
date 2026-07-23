#!/usr/bin/env python3
"""Fetch money flow data from East Money.

Shows capital flow data - either industry-level or individual stocks.

Usage:
    python fetch_money_flow.py                    # Industry money flow (default)
    python fetch_money_flow.py --stock            # Individual stock money flow
    python fetch_money_flow.py --stock --top 20   # Top 20 stocks by main net inflow
    python fetch_money_flow.py --json             # JSON output
    python fetch_money_flow.py --csv -o flow.csv  # Save as CSV
    python fetch_money_flow.py --cookie /path/to/.cookie  # Use custom cookie file
"""

import argparse
import csv
import io
import json
import sys

from pathlib import Path


from ashare_pilot.market_data._datasources import EastMoneyDataSource, set_cookie_file


_eastmoney = EastMoneyDataSource()


def fetch_money_flow(top: int = 100) -> list:
    """Fetch industry money flow data."""
    return _eastmoney.fetch_industry_money_flow(top)


def fetch_stock_money_flow(top: int = 100) -> list:
    """Fetch individual stock money flow data."""
    return _eastmoney.fetch_stock_money_flow(page_size=top)


def print_table(results: list, is_stock: bool = False) -> None:
    """Print money flow data in table format."""
    if not results:
        print("No data.")
        return

    # Sort by net_inflow descending (values are already in 亿)
    sorted_results = sorted(results, key=lambda x: float(x.get("net_inflow", 0) or 0) if not is_stock else float(x.get("main_net_inflow", 0) or 0), reverse=True)

    if is_stock:
        # Stock money flow table
        print(f"\n{'Code':<10} {'Name':<12} {'Price':>8} {'Change':>8} {'MainFlow(亿)':>12} {'Super(亿)':>10} {'Large(亿)':>10}")
        print("-" * 72)

        for r in sorted_results:
            code = r.get("code", "")
            name = r.get("name", "")[:10]
            price = r.get("price", "-")
            change = r.get("change_pct", "-")
            main_flow = r.get("main_net_inflow", "0.00")
            super_large = r.get("super_large_net", "0.00")
            large = r.get("large_net", "0.00")

            print(f"{code:<10} {name:<12} {price:>8} {change:>8} {main_flow:>12} {super_large:>10} {large:>10}")

        # Summary
        total_main = sum(float(r.get("main_net_inflow", 0) or 0) for r in results)
        print("-" * 72)
        print(f"{'TOTAL':<10} {'':<12} {'':>8} {'':>8} {total_main:>12.2f}亿")
    else:
        # Industry money flow table
        print(f"\n{'Code':<10} {'Industry':<20} {'NetFlow(亿)':>12}")
        print("-" * 44)

        for r in sorted_results:
            code = r.get("code", "")
            industry = r.get("industry", "")[:18]
            net_inflow = r.get("net_inflow", "0.00")

            print(f"{code:<10} {industry:<20} {net_inflow:>12}")

        # Summary
        total_net = sum(float(r.get("net_inflow", 0) or 0) for r in results)
        print("-" * 44)
        print(f"{'TOTAL':<10} {'':<20} {total_net:>12.2f}亿")


def to_csv_output(results: list, is_stock: bool = False) -> str:
    """Convert results to CSV format."""
    output = io.StringIO(newline="")
    if is_stock:
        fieldnames = [
            "code",
            "name",
            "price",
            "change_pct",
            "main_net_inflow",
            "main_ratio",
            "super_large_net",
            "super_large_ratio",
            "large_net",
            "large_ratio",
            "medium_net",
            "medium_ratio",
            "small_net",
            "small_ratio",
            "source",
        ]
    else:
        fieldnames = [
            "code",
            "type",
            "industry",
            "net_inflow",
            "source",
        ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    return output.getvalue()


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch money flow data from East Money"
    )
    parser.add_argument(
        "--stock",
        action="store_true",
        help="Fetch individual stock money flow instead of industry",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        metavar="N",
        help="Number of items to fetch (default: 50)",
    )
    parser.add_argument(
        "--cookie",
        metavar="FILE",
        help="Custom cookie file path (default: .cookie in project root)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV format")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")

    args = parser.parse_args(argv)

    # Set custom cookie file if provided
    if args.cookie:
        set_cookie_file(args.cookie)

    if args.stock:
        results = fetch_stock_money_flow(args.top)
    else:
        results = fetch_money_flow(args.top)

    if not results:
        print("No data fetched. API may be rate-limited or cookie expired.")
        sys.exit(1)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results, args.stock)
    else:
        # Table output
        lines = []
        if args.stock:
            sorted_results = sorted(results, key=lambda x: x.get("main_net_inflow_raw", 0), reverse=True)
            lines.append(f"\n{'Code':<10} {'Name':<12} {'Price':>8} {'Change':>8} {'MainFlow(亿)':>12} {'Super(亿)':>10} {'Large(亿)':>10}")
            lines.append("-" * 72)
            for r in sorted_results:
                code = r.get("code", "")
                name = r.get("name", "")[:10]
                price = r.get("price", "-")
                change = r.get("change_pct", "-")
                main_flow = r.get("main_net_inflow", "0.00")
                super_large = r.get("super_large_net", "0.00")
                large = r.get("large_net", "0.00")
                lines.append(f"{code:<10} {name:<12} {price:>8} {change:>8} {main_flow:>12} {super_large:>10} {large:>10}")
            total_main = sum(float(r.get("main_net_inflow", 0) or 0) for r in results)
            lines.append("-" * 72)
            lines.append(f"{'TOTAL':<10} {'':<12} {'':>8} {'':>8} {total_main:>12.2f}亿")
        else:
            sorted_results = sorted(results, key=lambda x: float(x.get("net_inflow", 0) or 0), reverse=True)
            lines.append(f"\n{'Code':<10} {'Industry':<20} {'NetFlow(亿)':>12}")
            lines.append("-" * 44)
            for r in sorted_results:
                code = r.get("code", "")
                industry = r.get("industry", "")[:18]
                net_inflow = r.get("net_inflow", "0.00")
                lines.append(f"{code:<10} {industry:<20} {net_inflow:>12}")
            total_net = sum(float(r.get("net_inflow", 0) or 0) for r in results)
            lines.append("-" * 44)
            lines.append(f"{'TOTAL':<10} {'':<20} {total_net:>12.2f}亿")
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
