#!/usr/bin/env python3
"""Fetch concept board list from East Money.

Supports checkpoint/resume: if a page fails, progress is saved and
next run resumes from that page. Use --fresh to ignore checkpoint.

Usage:
    python fetch_concepts.py
    python fetch_concepts.py -q          # quiet: skip concept table
    python fetch_concepts.py --reset     # ignore checkpoint, restart
    python fetch_concepts.py --json
    python fetch_concepts.py -o concepts.json
    python fetch_concepts.py --top 50
    python fetch_concepts.py -v          # verbose retry details
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

from datasource import EastMoneyConceptSource

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
CACHE_DIR = SKILL_DIR / "cache"
METADATA_DIR = SKILL_DIR / "metadata"


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch concept board list from East Money")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--top", type=int, default=0, help="Limit number of results")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed progress and retry messages")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress concept table output, only show progress")
    parser.add_argument("--fresh", "--reset", action="store_true", help="Ignore checkpoint, start fresh")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    state_file = CACHE_DIR / "concepts_fetch_state.json"
    if args.fresh and state_file.exists():
        state_file.unlink()
        print("Cleared checkpoint, starting fresh.")

    print("Fetching concept boards from East Money...")
    source = EastMoneyConceptSource(verbose=args.verbose, state_dir=CACHE_DIR)
    concepts = source.fetch_concept_sectors(resume=not args.fresh)

    if args.top > 0:
        concepts = concepts[:args.top]

    print(f"Fetched {len(concepts)} concept boards.")

    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = CACHE_DIR / "concepts.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(concepts, f, ensure_ascii=False, indent=2)
    print(f"Saved cache to {cache_path}")

    concept_list = [{"code": c["code"], "name": c["name"], "source": "eastmoney"} for c in concepts]
    list_path = METADATA_DIR / "concept_list.json"
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(concept_list, f, ensure_ascii=False, indent=2)
    print(f"Saved concept list to {list_path}")

    if args.json:
        output_str = json.dumps(concepts, ensure_ascii=False, indent=2)
    else:
        lines = []
        lines.append(f"{'Code':<10} {'Name':<20} {'Chg%':>8} {'Stocks':>8} {'Lead Stock'}")
        lines.append("-" * 70)
        for c in concepts:
            chg = c.get("change_pct")
            chg_str = f"{chg:>7.2f}%" if chg and chg != "-" else "    -  "
            stock_count = c.get("stock_count", "-")
            lead = c.get("lead_stock", "")[:15]
            lines.append(f"{c['code']:<10} {c['name']:<20} {chg_str} {stock_count!s:>8} {lead}")
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    elif not args.quiet:
        print(output_str)


if __name__ == "__main__":
    main()
