#!/usr/bin/env python3
"""End-to-end intraday overnight alpha pipeline orchestrator.

Runs at ~14:30:
    1. Market Scan → MarketState + ScanPool
    2. Stock Discovery → Enriched ComputePool + ThemeRanking
    3. Overnight Scoring → OpportunityPool

Layout:
    Intermediate JSON data → .cache/intraday/{date}/   (this script writes these)
    Final contracts        → intraday/{date}/          (base/annotations/mapper/overnight JSON; LLM + build scripts)

Usage:
    ashare-pilot automation intraday run --date 2026-06-30
    ashare-pilot automation intraday run --date 2026-06-30 --data-dir .cache/intraday/2026-06-30
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ashare_pilot.market_data._datasources import EastMoneyIntradayDataSource
from ashare_pilot.market_data.runtime import workspace_path

_cache_ds = EastMoneyIntradayDataSource()


def cli_command(*arguments: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "ashare_pilot",
        "--workspace",
        str(workspace_path()),
        *arguments,
    ]


def run_cmd(cmd: list, label: str = "") -> dict:
    print(f"  [{label}] Running...", flush=True)
    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(workspace_path()),
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


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run intraday overnight alpha pipeline")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument(
        "--data-dir",
        help="Intermediate JSON data directory (default: .cache/intraday/{date})",
    )
    parser.add_argument(
        "--compute-pool-size", type=int, default=120,
        help="Compute Pool size (default: 120)",
    )
    parser.add_argument(
        "--opportunity-size", type=int, default=30,
        help="Opportunity Pool size (default: 30)",
    )
    args = parser.parse_args(argv)

    # Intermediate JSON under .cache/; final contracts under intraday/.
    out_dir = Path(args.data_dir) if args.data_dir else workspace_path(".cache", "intraday", args.date)
    if not out_dir.is_absolute():
        out_dir = workspace_path() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir = workspace_path("intraday", args.date)
    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Overnight Alpha Pipeline ({args.date}) ===")
    print(f"Data dir:   {out_dir}")
    print(f"Report dir: {report_dir}")
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
            cli_command("market-data", "breadth", "--json", "-o", str(out_dir / "market_breadth.json"), "--cache-dir", cache_dir_arg),
            "breadth",
        ),
        (
            cli_command("market-data", "quote", "sh000001,sz399001,sz399006,sh000688,sh000852", "--json", "-o", str(out_dir / "indices.json")),
            "indices",
        ),
        (
            cli_command("themes", "dashboard", "build", "--json", "--top", "100", "-o", str(out_dir / "concept_dashboard.json"), "--cache-dir", cache_dir_arg),
            "concept",
        ),
    ]
    for cmd, name in tasks:
        results[name] = run_cmd(cmd, name)

    # ── Phase 2: Build Scan Pool ──
    print("\n--- Phase 2: Scan Pool Build ---")
    scan_cmd = [
        *cli_command("mapping", "intraday", "build-scan-pool"),
        "--compute-pool-size", str(args.compute_pool_size),
        "--json", "-o", str(out_dir / "scan_pool.json"),
        "--cache-dir", cache_dir_arg,
    ]
    results["scan"] = run_cmd(scan_cmd, "scan")

    # ── Phase 3: Enrich Compute Pool ──
    print("\n--- Phase 3: Enrich Compute Pool ---")
    enrich_cmd = [
        *cli_command("mapping", "intraday", "enrich-compute-pool"),
        str(out_dir / "scan_pool.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["enrich"] = run_cmd(enrich_cmd, "enrich")

    # ── Phase 3.5: Technical Indicators ──
    print("\n--- Phase 3.5: Technical Indicators ---")
    tech_cmd = [
        *cli_command("indicators", "pool", "enrich"),
        str(out_dir / "compute_pool_enriched.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["technicals"] = run_cmd(tech_cmd, "technicals")

    # ── Phase 3.6: Theme Ranking ──
    print("\n--- Phase 3.6: Theme Ranking ---")
    theme_cmd = [
        *cli_command("themes", "ranking", "compute"),
        str(out_dir / "compute_pool_enriched.json"),
        "--json", "--date", args.date,
        "-o", str(out_dir / "theme_ranking.json"),
    ]
    results["theme"] = run_cmd(theme_cmd, "theme")

    # ── Phase 4: Overnight Scoring ──
    print("\n--- Phase 4: Overnight Scoring ---")
    score_cmd = [
        *cli_command("strategy", "overnight", "score"),
        str(out_dir / "compute_pool_enriched.json"),
        "--opportunity-pool-size", str(args.opportunity_size),
        "--json", "-o", str(out_dir / "opportunity_pool.json"),
        "--breadth", str(out_dir / "market_breadth.json"),
        "--indices", str(out_dir / "indices.json"),
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
