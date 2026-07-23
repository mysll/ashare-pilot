#!/usr/bin/env python3
"""Build predict/{date}/mapper.base.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.daily_contract import (
    build_deterministic_mapper_base,
    default_predict_dir,
    ensure_doc_date,
    load_trading_scope,
    load_pool,
    read_json,
    write_json,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build mapper.base.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--pool", help="Path to pool_indicators.json; default predict/{date}/pool_indicators.json")
    parser.add_argument("--theme-stocks-json", help="Path to theme_stocks.json; default predict/{date}/theme_stocks.json")
    parser.add_argument("--scope", help="Path to trading-scope.json; default config/trading-scope.json")
    parser.add_argument("--output", help="Path to mapper.base.json; default predict/{date}/mapper.base.json")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    pool_path = Path(args.pool) if args.pool else predict_dir / "pool_indicators.json"
    theme_stocks_json_path = Path(args.theme_stocks_json) if args.theme_stocks_json else predict_dir / "theme_stocks.json"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.base.json"

    pool = load_pool(pool_path)
    scope = load_trading_scope(Path(args.scope) if args.scope else None)
    if not theme_stocks_json_path.exists():
        print(f"[ERROR] missing theme_stocks.json: {theme_stocks_json_path}", file=sys.stderr)
        return 1
    theme_stocks_doc = read_json(theme_stocks_json_path)
    if not isinstance(theme_stocks_doc, dict):
        print(f"[ERROR] theme_stocks.json must be a JSON object: {theme_stocks_json_path}", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(theme_stocks_doc, args.date, str(theme_stocks_json_path))
        doc = build_deterministic_mapper_base(args.date, pool, theme_stocks_doc, scope)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    mode = "deterministic-theme-stocks"
    write_json(output_path, doc)
    print(f"OK: wrote {output_path} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
