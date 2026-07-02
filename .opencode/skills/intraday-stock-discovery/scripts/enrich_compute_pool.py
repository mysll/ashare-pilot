#!/usr/bin/env python3
"""Enrich Compute Pool with technical indicators and money flow.

Takes a Compute Pool JSON (from build_scan_pool.py), fetches:
- Real-time quotes (Sina batch)
- Money flow (East Money batch)

Usage:
    python enrich_compute_pool.py compute_pool.json --json -o enriched.json
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.datasources import SinaDataSource, EastMoneyDataSource
from lib.datasources.eastmoney import set_cookie_file

_sina = SinaDataSource()
_eastmoney = EastMoneyDataSource()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CONFIG_PATH = os.path.join(_PROJECT_ROOT, ".opencode", "config", "trading-scope.json")


def load_board_exclusions():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

    excluded = set()
    for prefix, rule in config.get("boards", {}).items():
        if rule.get("exclude", False):
            excluded.add(prefix.lower())
    return excluded


def is_excluded(code, excluded_prefixes):
    if not code:
        return False
    code_lower = code.lower()
    for prefix in excluded_prefixes:
        if code_lower.startswith(prefix):
            return True
    return False


def fetch_vwap_for_codes(codes: list) -> dict:
    """Fetch intraday VWAP (分时均价线) via Sina per-stock K-line API.
    
    Extracts ma_price5 from the latest 5-min bar, which is the
    cumulative average price (VWAP) for the day.
    
    Returns {code: vwap_float} dict. Returns 0.0 for failures.
    """
    vwap_map = {}
    def _fetch_vwap(code):
        try:
            bars = _sina.fetch_intraday(code, scale=5, days=2)
            if bars and isinstance(bars, list) and len(bars) > 0:
                last = bars[-1]
                vwap = last.get("ma_price5")
                if vwap is not None:
                    return code, float(vwap)
        except Exception:
            pass
        return code, 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exc:
        futures = [exc.submit(_fetch_vwap, code) for code in codes]
        for f in concurrent.futures.as_completed(futures):
            try:
                code, vwap = f.result()
                vwap_map[code] = vwap
            except Exception:
                pass

    return vwap_map


def fetch_indicators_for_codes(codes: list) -> dict:
    """Fetch real-time quotes, VWAP and money flow for a batch of stock codes."""
    results = {}

    sina_results = {}
    try:
        sina_data = _sina.fetch_quotes(codes)
        for r in sina_data:
            if "error" not in r:
                sina_results[r["code"]] = {
                    "price": r.get("price"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "yestclose": r.get("yestclose"),
                    "volume": r.get("volume"),
                    "amount": r.get("amount", "0"),
                    "time": r.get("time"),
                }
    except Exception:
        pass

    vwap_map = {}
    try:
        vwap_map = fetch_vwap_for_codes(codes)
    except Exception:
        pass

    try:
        all_money = _eastmoney.fetch_stock_money_flow(page_size=5000)
    except Exception:
        all_money = []

    money_map = {}
    for m in all_money:
        money_map[m.get("code", "")] = m

    for code in codes:
        entry = sina_results.get(code, {})
        mf = money_map.get(code, {})
        results[code] = {
            "price": entry.get("price", "-"),
            "open": entry.get("open", "-"),
            "high": entry.get("high", "-"),
            "low": entry.get("low", "-"),
            "yestclose": entry.get("yestclose", "-"),
            "volume": entry.get("volume", "0"),
            "amount": entry.get("amount", "0"),
            "vwap": vwap_map.get(code, 0.0),
            "main_net_inflow": mf.get("main_net_inflow", "0.00"),
            "main_ratio": mf.get("main_ratio", "-"),
            "super_large_net": mf.get("super_large_net", "0.00"),
            "large_net": mf.get("large_net", "0.00"),
            "medium_net": mf.get("medium_net", "0.00"),
            "small_net": mf.get("small_net", "0.00"),
            "change_pct": mf.get("change_pct", "-"),
        }

    return results


def load_compute_pool(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("compute_pool", data.get("scan_pool", []))
    return data


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Enrich Compute Pool with indicators")
    parser.add_argument("input", help="Compute Pool JSON file from build_scan_pool.py")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--no-board-filter", action="store_true",
        help="Disable board exclusion filter (sh688/bj)",
    )
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    print(f"Loading Compute Pool from {args.input}...", file=sys.stderr)
    pool = load_compute_pool(args.input)

    if not args.no_board_filter:
        excluded_prefixes = load_board_exclusions()
        if excluded_prefixes:
            kept = []
            removed = []
            for s in pool:
                if is_excluded(s.get("code", ""), excluded_prefixes):
                    removed.append(s.get("code", "?"))
                else:
                    kept.append(s)
            if removed:
                prefix_str = ", ".join(sorted(excluded_prefixes))
                print(f"Board filter ({prefix_str}): removed {len(removed)}, kept {len(kept)}", file=sys.stderr)
                pool = kept

    codes = [s["code"] for s in pool if s.get("code")]
    print(f"Enriching {len(codes)} stocks...", file=sys.stderr)

    t0 = time.time()
    indicator_data = fetch_indicators_for_codes(codes)

    for stock in pool:
        code = stock.get("code", "")
        enrich = indicator_data.get(code, {})
        stock["enriched"] = {
            "real_time": {
                "price": enrich.get("price", "-"),
                "open": enrich.get("open", "-"),
                "high": enrich.get("high", "-"),
                "low": enrich.get("low", "-"),
                "yestclose": enrich.get("yestclose", "-"),
                "volume": enrich.get("volume", "0"),
                "amount": enrich.get("amount", "0"),
                "vwap": enrich.get("vwap", 0.0),
            },
            "money_flow": {
                "main_net_inflow": enrich.get("main_net_inflow", "0.00"),
                "main_ratio": enrich.get("main_ratio", "-"),
                "super_large_net": enrich.get("super_large_net", "0.00"),
                "large_net": enrich.get("large_net", "0.00"),
                "medium_net": enrich.get("medium_net", "0.00"),
                "small_net": enrich.get("small_net", "0.00"),
            },
        }

    elapsed = time.time() - t0
    print(f"Enrichment complete in {elapsed:.1f}s for {len(codes)} stocks.", file=sys.stderr)

    output = {
        "pool_size": len(pool),
        "enriched_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "compute_pool": pool,
    }
    if not args.no_board_filter and load_board_exclusions():
        output["board_filter_active"] = True

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
