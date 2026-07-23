#!/usr/bin/env python3
"""Fetch stocks for each concept board from East Money.

Supports resume: skips already-fetched concepts, retries previously failed ones.
Each concept is stored as a separate file: cache/stocks/BK0917.json

Usage:
    python fetch_concept_stocks.py
    python fetch_concept_stocks.py -q          # quiet: skip summary table
    python fetch_concept_stocks.py --concept BK0917
    python fetch_concept_stocks.py --top 10
    python fetch_concept_stocks.py --retry-failed
    python fetch_concept_stocks.py --reset
    python fetch_concept_stocks.py --json
"""

import argparse
import io
import json
import random
import sys
import time
from pathlib import Path

from ashare_pilot.themes.datasource import EastMoneyConceptSource
from ashare_pilot.themes.runtime import theme_cache_path

CACHE_DIR = theme_cache_path()
STOCKS_DIR = CACHE_DIR / "stocks"
FAILED_FILE = CACHE_DIR / "concept_stocks_failed.json"


def load_concepts():
    cache_path = CACHE_DIR / "concepts.json"
    if not cache_path.exists():
        print(f"Error: {cache_path} not found. Run fetch_concepts.py first.")
        sys.exit(1)
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def concept_cache_path(code):
    return STOCKS_DIR / f"{code}.json"


def load_concept(code):
    path = concept_cache_path(code)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_concept(code, data):
    STOCKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(concept_cache_path(code), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_cached_codes():
    if not STOCKS_DIR.exists():
        return set()
    return {f.stem for f in STOCKS_DIR.glob("*.json")}


def load_all_cached():
    if not STOCKS_DIR.exists():
        return {}
    result = {}
    for f in STOCKS_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            result[f.stem] = json.load(fh)
    return result


def load_failed():
    if not FAILED_FILE.exists():
        return []
    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_failed(failed):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch stocks for concept boards")
    parser.add_argument("--concept", help="Fetch stocks for a specific concept code (e.g., BK0917)")
    parser.add_argument("--top", type=int, default=0, help="Limit number of concept boards to fetch")
    parser.add_argument("--retry-failed", action="store_true", help="Only retry previously failed concepts")
    parser.add_argument("--reset", action="store_true", help="Delete cache and start fresh")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed progress and retry messages")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress summary table output, only show progress")
    args = parser.parse_args(argv)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if args.reset:
        if STOCKS_DIR.exists():
            import shutil
            shutil.rmtree(STOCKS_DIR)
        if FAILED_FILE.exists():
            FAILED_FILE.unlink()
        if (CACHE_DIR / "concept_stocks.json").exists():
            (CACHE_DIR / "concept_stocks.json").unlink()
        print("Cleared cache and failed list.")

    source = EastMoneyConceptSource(requests_per_minute=15, min_interval=1.5, max_interval=3.0, verbose=args.verbose)

    if args.concept:
        print(f"Fetching stocks for concept {args.concept}...")
        stocks = source.fetch_concept_stocks(args.concept)
        print(f"Fetched {len(stocks)} stocks.")

        if args.json:
            output_str = json.dumps(stocks, ensure_ascii=False, indent=2)
        else:
            lines = [f"Concept: {args.concept}", f"Stocks: {len(stocks)}", ""]
            lines.append(f"{'Code':<10} {'Name':<12} {'Price':>8} {'Chg%':>8} {'MV(亿)':>12}")
            lines.append("-" * 60)
            for s in stocks[:50]:
                price = s.get("price", "-")
                chg = s.get("change_pct", "-")
                mv = s.get("total_mv", 0)
                mv_str = f"{mv / 100000000:.1f}" if mv else "-"
                lines.append(f"{s['code']:<10} {s['name']:<12} {price!s:>8} {chg!s:>7}% {mv_str:>12}")
            if len(stocks) > 50:
                lines.append(f"  ... and {len(stocks) - 50} more")
            output_str = "\n".join(lines)

        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output_str)
            print(f"Saved to {args.output}")
        elif not args.quiet:
            print(output_str)
        return

    concepts = load_concepts()
    cached_codes = get_cached_codes()
    failed = load_failed()
    failed_codes = set(f["code"] for f in failed)

    if args.retry_failed:
        todo = [c for c in concepts if c["code"] in failed_codes]
        if not todo:
            print("No failed concepts to retry.")
            return
        print(f"Retrying {len(todo)} previously failed concepts...")
    else:
        todo = [c for c in concepts if c["code"] not in cached_codes or c["code"] in failed_codes]

    if args.top > 0:
        todo = todo[:args.top]

    total = len(todo)
    already = len(cached_codes) - len(failed_codes & cached_codes)
    print(f"Concepts: {len(concepts)} total, {already} cached, {len(failed_codes)} failed, {total} to fetch")

    if total == 0:
        print("All concepts already fetched. Use --reset to start fresh.")
        return

    new_failed = []
    processed = 0

    for concept in todo:
        code = concept["code"]
        name = concept["name"]

        processed += 1
        print(f"[{processed}/{total}] Fetching {name} ({code})...", flush=True)

        try:
            stocks = source.fetch_concept_stocks(code)
            if not stocks:
                is_retry = code in failed_codes
                cached = load_concept(code)
                if is_retry and cached and cached.get("stock_count", 0) > 0:
                    print(f"  Retry returned empty, keeping cached data.")
                else:
                    new_failed.append({"code": code, "name": name, "error": "empty_result", "time": time.strftime("%Y-%m-%d %H:%M:%S")})
                    print(f"  Empty result, marked as failed.")
                    continue

            concept_data = {
                "concept_code": code,
                "concept_name": name,
                "stock_count": len(stocks),
                "stocks": stocks,
                "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            save_concept(code, concept_data)

            if code in failed_codes:
                failed_codes.discard(code)
                print(f"  Retry succeeded: {len(stocks)} stocks.")

            if processed < total:
                delay = random.uniform(2.0, 5.0)
                print(f"  Waiting {delay:.1f}s...", flush=True)
                time.sleep(delay)

        except KeyboardInterrupt:
            print(f"\n\nInterrupted! Progress saved. Run again to continue from where you left off.")
            new_failed.append({"code": code, "name": name, "error": "interrupted", "time": time.strftime("%Y-%m-%d %H:%M:%S")})
            all_failed = [f for f in failed if f["code"] not in failed_codes - {code}] + new_failed
            save_failed(all_failed)
            return
        except Exception as e:
            print(f"  Error: {e}")
            new_failed.append({"code": code, "name": name, "error": str(e), "time": time.strftime("%Y-%m-%d %H:%M:%S")})

    all_failed = [f for f in failed if f["code"] not in failed_codes] + new_failed
    save_failed(all_failed)

    cached_codes = get_cached_codes()
    total_stocks = sum((load_concept(c) or {}).get("stock_count", 0) for c in cached_codes)
    cached_count = len(cached_codes) - len([f for f in all_failed if f["code"] in cached_codes])
    print(f"\nDone! Cached: {cached_count}, Failed: {len(all_failed)}, Total stocks: {total_stocks}")

    if all_failed:
        print(f"Failed concepts ({len(all_failed)}):")
        for f in all_failed[:10]:
            print(f"  {f['code']} {f['name']} - {f['error']}")
        if len(all_failed) > 10:
            print(f"  ... and {len(all_failed) - 10} more")
        print(f"Run with --retry-failed to retry them.")

    all_data = load_all_cached()
    if args.json:
        output_str = json.dumps(
            {k: {"concept_name": v["concept_name"], "stock_count": v["stock_count"]} for k, v in all_data.items()},
            ensure_ascii=False,
            indent=2,
        )
    else:
        lines = []
        lines.append(f"{'Concept Code':<12} {'Concept Name':<20} {'Stocks':>8}")
        lines.append("-" * 45)
        for code, data in sorted(all_data.items(), key=lambda x: x[1]["stock_count"], reverse=True):
            lines.append(f"{code:<12} {data['concept_name']:<20} {data['stock_count']:>8}")
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    elif not args.quiet:
        print(output_str)


if __name__ == "__main__":
    main()
