#!/usr/bin/env python3
"""Enrich Compute Pool with technical indicators and money flow.

Takes a Compute Pool JSON (from build_scan_pool.py), fetches:
- Real-time quotes (Sina batch)
- Money flow (East Money batch)

Usage:
    python enrich_compute_pool.py compute_pool.json --json -o enriched.json
"""

import argparse
import json
import sys
import time

from ashare_pilot.market_data._datasources import EastMoneyDataSource, SinaDataSource
from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.market_data.settings import (
    load_stock_money_flow_min_inflow_yuan,
)

_sina = SinaDataSource()
_eastmoney = EastMoneyDataSource()

def load_board_exclusions():
    try:
        with workspace_path("config", "trading-scope.json").open(encoding="utf-8") as f:
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


def compute_vwap(amount, volume):
    """True intraday VWAP = 成交额 / 成交量 (元/股).

    NOT ma_price5 (which is a 25-min moving average of 5-min bar closes and
    tracks price too closely to be a meaningful average-cost line).
    Returns 0.0 when data is missing/unparsable.
    """
    try:
        amt = float(str(amount).replace(",", ""))
        vol = float(str(volume).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
    if vol <= 0:
        return 0.0
    return round(amt / vol, 3)


def fetch_indicators_for_codes(
    codes: list,
    *,
    include_quality: bool = False,
    min_main_inflow_yuan: int | None = None,
):
    """Fetch real-time quotes, VWAP and money flow for a batch of stock codes."""
    results = {}
    if min_main_inflow_yuan is None:
        min_main_inflow_yuan = load_stock_money_flow_min_inflow_yuan()

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
    for code, entry in sina_results.items():
        vwap_map[code] = compute_vwap(entry.get("amount", "0"), entry.get("volume", "0"))

    try:
        money_result = _eastmoney.fetch_stock_money_flow_adaptive(
            target_codes=set(codes),
            min_main_inflow_yuan=min_main_inflow_yuan,
        )
        all_money = money_result.rows
        money_quality = money_result.quality(set(codes))
    except Exception as exc:
        all_money = []
        money_quality = {
            "status": "unavailable",
            "fetch_status": "unavailable",
            "rows_fetched": 0,
            "reported_total": None,
            "pages_fetched": 0,
            "failed_page": 1,
            "error": f"unexpected_error:{type(exc).__name__}",
            "stop_reason": None,
            "min_main_inflow_yuan": min_main_inflow_yuan,
            "requested_stock_count": len(codes),
            "matched_stock_count": 0,
            "coverage_pct": 0.0,
        }

    money_map = {}
    for m in all_money:
        money_map[m.get("code", "")] = m

    for code in codes:
        entry = sina_results.get(code, {})
        mf = money_map.get(code, {})
        result = {
            "price": entry.get("price", "-"),
            "open": entry.get("open", "-"),
            "high": entry.get("high", "-"),
            "low": entry.get("low", "-"),
            "yestclose": entry.get("yestclose", "-"),
            "volume": entry.get("volume", "0"),
            "amount": entry.get("amount", "0"),
            "vwap": vwap_map.get(code, 0.0),
            "money_flow_available": bool(mf),
            "money_flow_minimum_filter_applied": (
                money_quality.get("fetch_status") in {"threshold_reached", "partial"}
                and not mf
            ),
            "min_main_inflow_yuan": min_main_inflow_yuan,
        }
        if mf:
            result.update({
                "main_net_inflow": mf.get("main_net_inflow"),
                "main_net_inflow_yuan": mf.get("main_net_inflow_yuan"),
                "main_ratio": mf.get("main_ratio"),
                "super_large_net": mf.get("super_large_net"),
                "large_net": mf.get("large_net"),
                "medium_net": mf.get("medium_net"),
                "small_net": mf.get("small_net"),
                "change_pct": mf.get("change_pct"),
            })
        results[code] = result

    if include_quality:
        return results, money_quality
    return results


def load_compute_pool(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("compute_pool", data.get("scan_pool", []))
    return data


def main(argv=None):
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
    args = parser.parse_args(argv)

    print(f"Loading Compute Pool from {args.input}...", file=sys.stderr)
    with open(args.input, "r", encoding="utf-8") as f:
        source_document = json.load(f)
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
    indicator_data, money_flow_quality = fetch_indicators_for_codes(
        codes, include_quality=True
    )

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
            "money_flow": (
                {
                    "available": True,
                    "main_net_inflow": enrich.get("main_net_inflow"),
                    "main_net_inflow_yuan": enrich.get("main_net_inflow_yuan"),
                    "minimum_main_inflow_yuan": enrich.get(
                        "min_main_inflow_yuan"
                    ),
                    "meets_minimum_main_inflow": (
                        isinstance(enrich.get("main_net_inflow_yuan"), (int, float))
                        and enrich["main_net_inflow_yuan"]
                        >= enrich.get("min_main_inflow_yuan", 0)
                    ),
                    "main_ratio": enrich.get("main_ratio"),
                    "super_large_net": enrich.get("super_large_net"),
                    "large_net": enrich.get("large_net"),
                    "medium_net": enrich.get("medium_net"),
                    "small_net": enrich.get("small_net"),
                }
                if enrich.get("money_flow_available")
                else {
                    "available": False,
                    "minimum_filter_applied": enrich.get(
                        "money_flow_minimum_filter_applied", False
                    ),
                    "minimum_main_inflow_yuan": enrich.get(
                        "min_main_inflow_yuan"
                    ),
                    "missing_reason": (
                        "below_configured_minimum_or_not_returned_by_endpoint"
                        if enrich.get("money_flow_minimum_filter_applied")
                        else "not_returned_in_fetched_money_flow_pages"
                    ),
                }
            ),
        }

    elapsed = time.time() - t0
    print(f"Enrichment complete in {elapsed:.1f}s for {len(codes)} stocks.", file=sys.stderr)

    output = {
        "pool_size": len(pool),
        "enriched_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "recall_quality": (
            source_document.get("recall_quality", {})
            if isinstance(source_document, dict)
            else {}
        ),
        "data_quality": {
            "money_flow": money_flow_quality,
        },
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
    valid_money_count = sum(
        1
        for stock in pool
        if stock.get("enriched", {}).get("money_flow", {}).get("available") is True
    )
    if money_flow_quality.get("status") == "unavailable" or valid_money_count == 0:
        print(
            "[ERROR] Stock money flow is unavailable for the entire Compute Pool",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    main()
