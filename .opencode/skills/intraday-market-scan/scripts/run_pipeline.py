#!/usr/bin/env python3
"""End-to-end intraday overnight alpha pipeline orchestrator.

Runs at ~14:30:
    1. Market Scan → MarketState + ScanPool
    2. Stock Discovery → Enriched ComputePool + ThemeRanking
    3. Overnight Scoring → OpportunityPool

Usage:
    python run_pipeline.py --date 2026-06-30
    python run_pipeline.py --date 2026-06-30 --output-dir intraday/2026-06-30
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "stock-analysis" / "scripts"
LOCAL_SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

import sys as _sys
_sys.path.insert(0, str(SCRIPTS_DIR))
from datasources import EastMoneyIntradayDataSource
_cache_ds = EastMoneyIntradayDataSource()


def run_cmd(cmd: list, label: str = "") -> dict:
    print(f"  [{label}] Running...", flush=True)
    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"  [{label}] Done in {elapsed:.1f}s", flush=True)
    else:
        print(f"  [{label}] FAILED in {elapsed:.1f}s (exit={result.returncode})", flush=True)
        if result.stderr.strip():
            print(f"  [{label}] stderr: {result.stderr[:500]}", flush=True)
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed": elapsed,
    }


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run intraday overnight alpha pipeline")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", help="Output directory (default: intraday/{date})")
    parser.add_argument(
        "--compute-pool-size", type=int, default=120,
        help="Compute Pool size (default: 120)",
    )
    parser.add_argument(
        "--opportunity-size", type=int, default=30,
        help="Opportunity Pool size (default: 30)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else Path(f"intraday/{args.date}")
    out_dir.mkdir(parents=True, exist_ok=True)

    script_base = str(SCRIPTS_DIR)

    print(f"=== Overnight Alpha Pipeline ({args.date}) ===")
    print(f"Output dir: {out_dir}")
    total_start = time.time()

    # ── Phase 0: Prefetch all-stocks cache (once, shared by all downstream) ──
    print("\n--- Phase 0: Prefetch all-stocks cache ---")
    t0 = time.time()
    all_stocks = _cache_ds.fetch_all_astocks(cache_dir=str(out_dir))
    print(f"  Cached {len(all_stocks)} stocks in {time.time() - t0:.1f}s")
    cache_dir_arg = str(out_dir)

    # ── Phase 1: Market Scan (parallel-ready independent calls) ──
    print("\n--- Phase 1: Market Scan ---")

    results = {}
    tasks = [
        (
            [sys.executable, f"{script_base}/fetch_market_breadth.py", "--json", "-o", str(out_dir / "market_breadth.json"), "--cache-dir", cache_dir_arg],
            "breadth",
        ),
        (
            [sys.executable, f"{script_base}/fetch_stock.py", "sh000001,sz399001,sz399006,sh000688,sh000852", "--json", "-o", str(out_dir / "indices.json")],
            "indices",
        ),
        (
            [sys.executable, f"{LOCAL_SCRIPTS_DIR}/build_concept_dashboard.py", "--json", "--top", "100", "-o", str(out_dir / "concept_dashboard.json"), "--cache-dir", cache_dir_arg],
            "concept",
        ),
        (
            [sys.executable, f"{script_base}/fetch_north_bound.py", "--json", "-o", str(out_dir / "north_bound.json")],
            "north",
        ),
    ]
    for cmd, name in tasks:
        results[name] = run_cmd(cmd, name)

    # ── Phase 2: Build Scan Pool ──
    print("\n--- Phase 2: Scan Pool Build ---")
    scan_cmd = [
        sys.executable, f"{script_base}/build_scan_pool.py",
        "--compute-pool-size", str(args.compute_pool_size),
        "--json", "-o", str(out_dir / "scan_pool.json"),
        "--cache-dir", cache_dir_arg,
    ]
    results["scan"] = run_cmd(scan_cmd, "scan")

    # ── Phase 3: Enrich Compute Pool ──
    print("\n--- Phase 3: Enrich Compute Pool ---")
    enrich_cmd = [
        sys.executable, f"{script_base}/enrich_compute_pool.py",
        str(out_dir / "scan_pool.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["enrich"] = run_cmd(enrich_cmd, "enrich")

    # ── Phase 4: Overnight Scoring ──
    print("\n--- Phase 4: Overnight Scoring ---")
    score_cmd = [
        sys.executable, f"{script_base}/score_overnight.py",
        str(out_dir / "compute_pool_enriched.json"),
        "--opportunity-pool-size", str(args.opportunity_size),
        "--json", "-o", str(out_dir / "opportunity_pool.json"),
    ]
    results["score"] = run_cmd(score_cmd, "score")

    total = time.time() - total_start

    # ── Summary ──
    print(f"\n=== Pipeline Complete in {total:.1f}s ===")
    print(f"\nOutput files in {out_dir}:")
    for fpath in sorted(out_dir.glob("*.json")):
        size = fpath.stat().st_size
        print(f"  {fpath.name} ({size:>8,} bytes)")

    # Quick validation
    pool_file = out_dir / "opportunity_pool.json"
    if pool_file.exists():
        try:
            with open(pool_file, "r", encoding="utf-8") as f:
                opp_data = json.load(f)
            pool = opp_data.get("opportunity_pool", [])
            print(f"\nOpportunity Pool: {len(pool)} stocks (v{opp_data.get('weights_version', '?')})")
            if pool:
                print("Top 5:")
                for s in pool[:5]:
                    print(
                        f"  [{s.get('tier', '?')}] {s.get('code', '?')} {s.get('name', '?')} "
                        f"score={s.get('overnight_score', '?')}"
                    )
        except Exception as e:
            print(f"  (Failed to read opportunity pool: {e})")

    # Phase timings
    print(f"\nPhase timings:")
    for name, r in results.items():
        status = "OK" if r["success"] else "FAIL"
        print(f"  {name:<10} {r['elapsed']:>5.1f}s  [{status}]")


if __name__ == "__main__":
    main()
