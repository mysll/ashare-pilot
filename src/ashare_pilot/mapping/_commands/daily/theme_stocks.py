#!/usr/bin/env python3
"""Publish predict/{date}/theme_stocks.json from its deterministic base."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.daily_contract import default_predict_dir, ensure_doc_date, publish_theme_stocks, read_json, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--base", help="Path to theme_stocks.base.json; default predict/{date}/theme_stocks.base.json")
    parser.add_argument("--output", help="Path to theme_stocks.json; default predict/{date}/theme_stocks.json")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    base_path = Path(args.base) if args.base else predict_dir / "theme_stocks.base.json"
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.json"

    if not base_path.exists():
        print(f"[ERROR] missing theme_stocks.base.json: {base_path}", file=sys.stderr)
        return 1
    base = read_json(base_path)
    if not isinstance(base, dict):
        print("[ERROR] base must be a JSON object", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(base, args.date, str(base_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if base.get("schema_version") != "daily_theme_stocks_base.v2":
        print("[ERROR] base schema_version must be daily_theme_stocks_base.v2", file=sys.stderr)
        return 1
    doc = publish_theme_stocks(base, args.date)
    write_json(output_path, doc)
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
