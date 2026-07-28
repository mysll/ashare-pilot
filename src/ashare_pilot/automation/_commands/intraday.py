#!/usr/bin/env python3
"""End-to-end intraday overnight alpha pipeline orchestrator.

Runs at ~14:30:
    1. Market Scan → MarketState + ScanPool
    2. Stock Discovery → Enriched ComputePool + ThemeRanking
    3. Overnight Scoring → SelectionPools

Layout:
    Intermediate JSON data → .cache/intraday/{date}/   (this script writes these)
    Final contracts        → intraday/{date}/          (base/annotations/mapper/overnight JSON; LLM + build scripts)

Usage:
    ashare-pilot automation intraday run --date 2026-06-30
    ashare-pilot automation intraday run --date 2026-06-30 --data-dir .cache/intraday/2026-06-30
"""

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ashare_pilot.market_data._datasources import EastMoneyIntradayDataSource
from ashare_pilot.market_data.runtime import workspace_path

_cache_ds = EastMoneyIntradayDataSource()


def _finite_number(value) -> bool:
    if (
        isinstance(value, bool)
        or value is None
        or (isinstance(value, str) and value in {"", "-"})
    ):
        return False
    try:
        return math.isfinite(
            float(str(value).replace("%", "").replace("+", "").replace(",", ""))
        )
    except (TypeError, ValueError):
        return False


def validate_required_indices(document) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, list):
        return ["indices output must be an array"]
    by_code = {
        row.get("code"): row
        for row in document
        if isinstance(row, dict) and isinstance(row.get("code"), str)
    }
    for code in ("sh000001", "sz399001"):
        row = by_code.get(code)
        if row is None:
            errors.append(f"required index missing: {code}")
            continue
        if not _finite_number(row.get("price")):
            errors.append(f"required index price invalid: {code}")
        if not _finite_number(row.get("percent")):
            errors.append(f"required index percent invalid: {code}")
    return errors


def build_indices_quality(document) -> dict:
    rows = document if isinstance(document, list) else []
    by_code = {
        row.get("code"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("code"), str)
    }
    required = {"sh000001", "sz399001"}
    configured = [
        "sh000001",
        "sz399001",
        "sz399006",
        "sh000688",
        "sh000852",
    ]
    values = {}
    for code in configured:
        row = by_code.get(code)
        valid = bool(
            row
            and _finite_number(row.get("price"))
            and _finite_number(row.get("percent"))
        )
        values[code] = {
            "status": "complete" if valid else "unavailable",
            "required": code in required,
            **({} if valid else {"error": "missing_or_invalid_quote"}),
        }
    return {
        "status": (
            "complete"
            if all(values[code]["status"] == "complete" for code in required)
            else "unavailable"
        ),
        "indices": values,
        "required_complete_count": sum(
            values[code]["status"] == "complete" for code in required
        ),
        "auxiliary_complete_count": sum(
            values[code]["status"] == "complete"
            for code in set(configured) - required
        ),
    }


def validate_indices_file(path: Path) -> list[str]:
    try:
        return validate_required_indices(
            json.loads(path.read_text(encoding="utf-8-sig"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"indices output unreadable: {type(exc).__name__}"]


def write_unavailable_contract(path: Path, schema_version: str, error: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "status": "unavailable",
                "error": error,
                "themes": {},
                "rankings": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def validate_theme_ranking_file(path: Path) -> list[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"theme ranking unreadable: {type(exc).__name__}"]
    if not isinstance(document, dict):
        return ["theme ranking must be an object"]
    if document.get("schema_version") != "intraday_theme_ranking.v2":
        return ["theme ranking schema_version must be intraday_theme_ranking.v2"]
    if not isinstance(document.get("theme_ranking"), list):
        return ["theme_ranking must be an array"]
    return []


def _stop(errors: list[str] | str) -> int:
    messages = [errors] if isinstance(errors, str) else errors
    for error in messages:
        print(f"  [HARD STOP] {error}", file=sys.stderr)
    return 1


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
        "--executable-size", type=int, default=30,
        help="Executable Pool size (default: 30)",
    )
    parser.add_argument(
        "--observation-size", type=int, default=30,
        help="Observation Pool size (default: 30)",
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
    all_stocks = _cache_ds.fetch_all_astocks(
        cache_dir=str(out_dir),
        resume_partial=True,
    )
    cache_quality = _cache_ds.last_all_stocks_quality
    cache_status = cache_quality.get("status", "unknown")
    print(
        f"  Cached {len(all_stocks)} stocks "
        f"(status={cache_status}) in {time.time() - t0:.1f}s"
    )
    if cache_status != "complete":
        return _stop(
            "all-stock snapshot is not complete: "
            f"status={cache_status}, pages={cache_quality.get('pages_fetched')}, "
            f"failed_page={cache_quality.get('failed_page')}, "
            f"next_page={cache_quality.get('next_page')}, "
            f"error={cache_quality.get('error')}"
        )
    cache_dir_arg = str(out_dir)

    # ── Phase 1: Market Scan (parallel-ready independent calls) ──
    print("\n--- Phase 1: Market Scan ---")

    results = {}
    breadth_cmd = cli_command(
        "market-data", "breadth", "--json",
        "-o", str(out_dir / "market_breadth.json"),
        "--cache-dir", cache_dir_arg,
    )
    results["breadth"] = run_cmd(breadth_cmd, "breadth")
    if not results["breadth"]["success"]:
        return _stop("market breadth command failed")

    indices_cmd = cli_command(
        "market-data", "quote",
        "sh000001,sz399001,sz399006,sh000688,sh000852",
        "--json", "-o", str(out_dir / "indices.json"),
    )
    results["indices"] = run_cmd(indices_cmd, "indices")
    if not results["indices"]["success"]:
        return _stop("required indices command failed")
    index_errors = validate_indices_file(out_dir / "indices.json")
    if index_errors:
        return _stop(index_errors)
    indices_document = json.loads(
        (out_dir / "indices.json").read_text(encoding="utf-8-sig")
    )
    (out_dir / "indices_quality.json").write_text(
        json.dumps(
            build_indices_quality(indices_document),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    concept_path = out_dir / "concept_dashboard.json"
    concept_cmd = cli_command(
        "themes", "dashboard", "build", "--json", "--top", "100",
        "-o", str(concept_path), "--cache-dir", cache_dir_arg,
    )
    results["concept"] = run_cmd(concept_cmd, "concept")
    if not results["concept"]["success"]:
        write_unavailable_contract(
            concept_path,
            "intraday_concept_dashboard.v1",
            "concept_dashboard_command_failed",
        )
    else:
        try:
            concept_document = json.loads(
                concept_path.read_text(encoding="utf-8-sig")
            )
            if (
                not isinstance(concept_document, dict)
                or concept_document.get("status") not in {"complete", "unavailable"}
            ):
                raise ValueError("invalid concept dashboard quality contract")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            write_unavailable_contract(
                concept_path,
                "intraday_concept_dashboard.v1",
                f"invalid_concept_dashboard:{type(exc).__name__}",
            )

    # ── Phase 2: Build Scan Pool ──
    print("\n--- Phase 2: Scan Pool Build ---")
    scan_cmd = [
        *cli_command("mapping", "intraday", "build-scan-pool"),
        "--compute-pool-size", str(args.compute_pool_size),
        "--json", "-o", str(out_dir / "scan_pool.json"),
        "--cache-dir", cache_dir_arg,
    ]
    results["scan"] = run_cmd(scan_cmd, "scan")
    if not results["scan"]["success"]:
        return _stop("Scan Pool command failed or did not reach Compute Pool target")

    # ── Phase 3: Enrich Compute Pool ──
    print("\n--- Phase 3: Enrich Compute Pool ---")
    enrich_cmd = [
        *cli_command("mapping", "intraday", "enrich-compute-pool"),
        str(out_dir / "scan_pool.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["enrich"] = run_cmd(enrich_cmd, "enrich")
    if not results["enrich"]["success"]:
        return _stop("Compute Pool quote/money-flow enrichment failed")

    # ── Phase 3.5: Technical Indicators ──
    print("\n--- Phase 3.5: Technical Indicators ---")
    tech_cmd = [
        *cli_command("indicators", "pool", "enrich"),
        str(out_dir / "compute_pool_enriched.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["technicals"] = run_cmd(tech_cmd, "technicals")
    if not results["technicals"]["success"]:
        return _stop("technical enrichment is unavailable")

    # ── Phase 3.6: Theme Ranking ──
    print("\n--- Phase 3.6: Theme Ranking ---")
    theme_cmd = [
        *cli_command("themes", "ranking", "compute"),
        str(out_dir / "compute_pool_enriched.json"),
        "--json", "--date", args.date,
        "-o", str(out_dir / "theme_ranking.json"),
    ]
    results["theme"] = run_cmd(theme_cmd, "theme")
    if not results["theme"]["success"]:
        return _stop("Theme Ranking command failed")
    theme_errors = validate_theme_ranking_file(out_dir / "theme_ranking.json")
    if theme_errors:
        return _stop(theme_errors)

    # ── Phase 4: Overnight Scoring ──
    print("\n--- Phase 4: Overnight Scoring ---")
    score_cmd = [
        *cli_command("strategy", "overnight", "score"),
        str(out_dir / "compute_pool_enriched.json"),
        "--executable-pool-size", str(args.executable_size),
        "--observation-pool-size", str(args.observation_size),
        "--date", args.date,
        "--json", "-o", str(out_dir / "selection_pools.json"),
        "--breadth", str(out_dir / "market_breadth.json"),
        "--indices", str(out_dir / "indices.json"),
    ]
    results["score"] = run_cmd(score_cmd, "score")
    if not results["score"]["success"]:
        return _stop("overnight scoring failed")

    total = time.time() - total_start

    # ── Summary ──
    print(f"\n=== Pipeline Complete in {total:.1f}s ===")
    print(f"\nOutput files in {out_dir}:")
    for fpath in sorted(out_dir.glob("*.json")):
        size = fpath.stat().st_size
        print(f"  {fpath.name} ({size:>8,} bytes)")

    # Quick validation
    pool_file = out_dir / "selection_pools.json"
    if pool_file.exists():
        try:
            with open(pool_file, "r", encoding="utf-8") as f:
                pool_data = json.load(f)
            executable = pool_data.get("executable_pool", [])
            observation = pool_data.get("observation_pool", [])
            print(
                f"\nSelection Pools: executable={len(executable)}, "
                f"observation={len(observation)} "
                f"({pool_data.get('scoring_version', '?')})"
            )
        except Exception as e:
            print(f"  (Failed to read selection pools: {e})")

    # Phase timings
    print(f"\nPhase timings:")
    for name, r in results.items():
        status = "OK" if r["success"] else "FAIL"
        print(f"  {name:<10} {r['elapsed']:>5.1f}s  [{status}]")
    return 0


if __name__ == "__main__":
    main()
