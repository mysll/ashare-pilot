#!/usr/bin/env python3
"""Enrich Compute Pool with technical indicators.

Fetches daily K-line via Sina, caches via kline_cache.py, computes:
  - MA5, MA10, MA20, MA60
  - Bollinger Bands (20, 2): mid, upper, lower
  - boll_zone: above_ub | upper_half | below_mid
  - ma_alignment: bullish | mixed | bearish
  - above_ma5: bool

Usage:
    python enrich_technicals.py compute_pool_enriched.json --json -o enriched.json
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from datasources import SinaDataSource


_sina = SinaDataSource()


def parse_float(val, default=0.0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(
            str(val)
            .replace("%", "")
            .replace("+", "")
            .replace(",", "")
            .replace("亿", "")
            .replace("万", "")
        )
    except (ValueError, TypeError):
        return default


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def bollinger_bands(values, period=20, std_dev=2.0):
    mid = sma(values, period)
    if mid is None:
        return None, None, None
    window = values[-period:]
    variance = sum((x - mid) ** 2 for x in window) / (period - 1)
    std = math.sqrt(variance)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return mid, upper, lower


def _fetch_and_compute(code, current_price):
    try:
        records = _sina.fetch_daily_history(code, range_str="3m")
    except Exception:
        return None

    if not records or len(records) < 5:
        return None

    closes = [parse_float(r.get("close", 0)) for r in records]
    closes = [c for c in closes if c > 0]
    if len(closes) < 5:
        return None

    ma5_val = sma(closes, 5)
    ma10_val = sma(closes, 10)
    ma20_val = sma(closes, 20)
    ma60_val = sma(closes, 60) if len(closes) >= 60 else None

    boll_mid_val, boll_ub_val, boll_lb_val = bollinger_bands(closes, 20, 2)

    # Bollinger zone
    if boll_mid_val is None:
        boll_zone = "no_data"
    elif current_price > 0 and current_price >= boll_ub_val:
        boll_zone = "above_ub"
    elif current_price > 0 and current_price >= boll_mid_val:
        boll_zone = "upper_half"
    elif boll_mid_val is not None:
        boll_zone = "below_mid"
    else:
        boll_zone = "no_data"

    # MA alignment
    if ma5_val is None or ma10_val is None or ma20_val is None:
        ma_alignment = "no_data"
    elif ma5_val > ma10_val > ma20_val:
        ma_alignment = "bullish"
    elif ma5_val < ma10_val < ma20_val:
        ma_alignment = "bearish"
    else:
        ma_alignment = "mixed"

    above_ma5 = (current_price > 0 and ma5_val is not None
                 and current_price >= ma5_val)

    return {
        "ma5": round(ma5_val, 2) if ma5_val is not None else None,
        "ma10": round(ma10_val, 2) if ma10_val is not None else None,
        "ma20": round(ma20_val, 2) if ma20_val is not None else None,
        "ma60": round(ma60_val, 2) if ma60_val is not None else None,
        "boll_mid": round(boll_mid_val, 2) if boll_mid_val is not None else None,
        "boll_ub": round(boll_ub_val, 2) if boll_ub_val is not None else None,
        "boll_lb": round(boll_lb_val, 2) if boll_lb_val is not None else None,
        "boll_zone": boll_zone,
        "ma_alignment": ma_alignment,
        "above_ma5": above_ma5,
    }


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Enrich Compute Pool with technical indicators"
    )
    parser.add_argument("input", help="Enriched Compute Pool JSON file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument(
        "--max-workers", type=int, default=8,
        help="Max concurrent workers (default: 8)",
    )
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    pool = data.get("compute_pool", data.get("scan_pool", []))
    if isinstance(data, list):
        pool = data

    codes = []
    for s in pool:
        code = s.get("code", "")
        if not code:
            continue
        enriched = s.get("enriched", {})
        rt = enriched.get("real_time", {})
        current_price = parse_float(rt.get("price", s.get("price", 0)))
        codes.append((code, current_price))

    print(f"Fetching technicals for {len(codes)} stocks...", file=sys.stderr)
    t0 = time.time()

    results = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(_fetch_and_compute, code, price): code
            for code, price in codes
        }
        for f in as_completed(futures):
            code = futures[f]
            try:
                results[code] = f.result()
            except Exception as e:
                print(f"  Error {code}: {e}", file=sys.stderr)
                results[code] = None

    elapsed = time.time() - t0
    success = sum(1 for v in results.values() if v is not None)
    cache_hits = sum(1 for c, _p in codes if results.get(c) is not None)
    print(
        f"Technicals: {success}/{len(codes)} enriched in {elapsed:.1f}s",
        file=sys.stderr,
    )

    for stock in pool:
        code = stock.get("code", "")
        tech = results.get(code)
        if tech:
            stock["technicals"] = tech
        else:
            stock["technicals"] = {
                "boll_zone": "no_data",
                "ma_alignment": "no_data",
                "above_ma5": False,
            }

    output_str = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
