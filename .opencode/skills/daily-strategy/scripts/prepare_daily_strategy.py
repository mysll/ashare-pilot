#!/usr/bin/env python3
"""Validate and project deterministic Step 3 inputs in one process."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, time as clock_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
MAPPING_SCRIPTS = ROOT / ".opencode" / "skills" / "daily-stock-mapping" / "scripts"
sys.path.insert(0, str(MAPPING_SCRIPTS))

from build_strategy_view import build_view  # noqa: E402
from mapper_json_lib import ensure_doc_date, load_pool, load_trading_scope, read_json, write_json  # noqa: E402
from validate_mapper_json import check_doc as validate_mapper  # noqa: E402

from build_step3_timing import update_report  # noqa: E402
from build_strategy_llm_input import build_input, canonical_sha256, compact_write, index_percent, percent_number  # noqa: E402

INDEX_CODES = ("sh000001", "sz399001", "sh000688")


def wait_for_market_snapshot(date: str) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.date().isoformat() != date or now.time() >= clock_time(9, 25, 10):
        return
    target = now.replace(hour=9, minute=25, second=10, microsecond=0)
    time.sleep(max(0.0, (target - now).total_seconds()))


def normalize_indices(value: Any) -> dict[str, dict[str, Any]]:
    rows = value if isinstance(value, list) else list(value.values()) if isinstance(value, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict) or item.get("code") not in INDEX_CODES:
            continue
        normalized = {
            key: item.get(key) for key in ("code", "name", "percent", "change_pct", "pct_change", "open", "close", "prev_close", "error")
            if item.get(key) is not None
        }
        for key in ("percent", "change_pct", "pct_change"):
            if key in normalized:
                parsed = percent_number(normalized[key])
                if parsed is not None:
                    normalized[key] = parsed
        result[item["code"]] = normalized
    for code in INDEX_CODES:
        result.setdefault(code, {"code": code, "error": "missing index quote"})
    return result


def fetch_indices(path: Path | None) -> tuple[dict[str, dict[str, Any]], float, bool]:
    started = time.perf_counter()
    if path:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        command = [sys.executable, str(ROOT / ".opencode" / "lib" / "fetch" / "fetch_stock.py"), ",".join(INDEX_CODES), "--json"]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "index fetch failed")
        data = json.loads(completed.stdout)
    indices = normalize_indices(data)
    failed = any(item.get("error") or index_percent(indices, code) is None for code, item in indices.items())
    return indices, time.perf_counter() - started, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare daily Step 3 compact input")
    parser.add_argument("--date", required=True)
    parser.add_argument("--input-dir", help="Fixture input directory; defaults to predict/{date}")
    parser.add_argument("--output-dir", help="Fixture output directory; defaults to input directory")
    parser.add_argument("--indices", help="Use frozen index quote JSON instead of fetching")
    parser.add_argument("--scope")
    args = parser.parse_args()
    started = time.perf_counter()
    input_dir = Path(args.input_dir) if args.input_dir else ROOT / "predict" / args.date
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    mapper_path = input_dir / "mapper.json"
    view_input_path = input_dir / "mapper.strategy_view.json"
    view_output_path = output_dir / "mapper.strategy_view.json"
    output_path = output_dir / ".strategy_llm_input.json"
    index_duration = 0.0
    index_failed = True
    try:
        mapper = read_json(mapper_path)
        if not isinstance(mapper, dict):
            raise ValueError("mapper root must be object")
        ensure_doc_date(mapper, args.date, str(mapper_path))
        pool_path = input_dir / "pool_indicators.json"
        pool = read_json(pool_path)
        errors = validate_mapper(mapper, load_pool(pool_path), load_trading_scope(Path(args.scope) if args.scope else None))
        if errors:
            raise ValueError("mapper validation failed:\n" + "\n".join(f"  - {item}" for item in errors))
        mapper_hash = canonical_sha256(mapper)
        view = read_json(view_input_path) if view_input_path.exists() else None
        linked = (
            isinstance(view, dict) and view.get("date") == args.date
            and view.get("source", {}).get("mapper_sha256") == mapper_hash
        )
        if not linked:
            view = build_view(mapper)
            write_json(view_output_path, view)
        elif view_input_path != view_output_path:
            write_json(view_output_path, view)
        theme_stocks = read_json(input_dir / "theme_stocks.json")
        news = read_json(input_dir / "news.json")
        if not isinstance(theme_stocks, dict) or not isinstance(news, dict):
            raise ValueError("theme_stocks.json and news.json must be objects")
        ensure_doc_date(theme_stocks, args.date, "theme_stocks.json")
        ensure_doc_date(news, args.date, "news.json")
        if not args.indices:
            wait_for_market_snapshot(args.date)
        indices, index_duration, index_failed = fetch_indices(Path(args.indices) if args.indices else None)
        compact = build_input(view, theme_stocks, pool, news, indices)
        compact["market_inputs"]["index_fetch_failed"] = index_failed
        compact_write(output_path, compact)
        if output_path.stat().st_size > 80 * 1024:
            raise ValueError(f"compact input exceeds hard 80KB target: {output_path.stat().st_size} bytes")
        if output_path.stat().st_size > 70 * 1024:
            print(f"[WARN] compact input exceeds 70KB warning threshold: {output_path.stat().st_size} bytes", file=sys.stderr)
        duration = time.perf_counter() - started
        counts = {
            "candidate_count": len(compact["candidates"]),
            "selected_count": 0,
            "observation_count": 0,
            "conditional_news_count": len(compact["news_evidence"]),
            "llm_input_bytes": output_path.stat().st_size,
            "llm_output_bytes": 0,
        }
        update_report(output_dir / "step3_timing.json", args.date, "prepare", duration,
                      [mapper_path, view_output_path, input_dir / "theme_stocks.json", pool_path, input_dir / "news.json"],
                      [output_path], counts, validation_retries=0,
                      index_fetch_duration=index_duration, index_fetch_failed=index_failed)
    except Exception as exc:
        print(f"[ERROR] prepare_daily_strategy failed: {exc}", file=sys.stderr)
        return 1
    warning = " (index fetch degraded; LLM must treat regime hint as advisory)" if index_failed else ""
    print(f"OK: prepared {len(compact['candidates'])} candidates in {duration:.3f}s, {output_path.stat().st_size} bytes{warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
