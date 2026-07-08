#!/usr/bin/env python3
"""Build predict/{date}/theme_stocks.json from base + annotations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mapper_json_lib import default_predict_dir, ensure_doc_date, merge_theme_stock_annotations, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--base", help="Path to theme_stocks.base.json; default predict/{date}/theme_stocks.base.json")
    parser.add_argument("--annotations", help="Path to theme_stocks.annotations.json; default predict/{date}/theme_stocks.annotations.json")
    parser.add_argument("--output", help="Path to theme_stocks.json; default predict/{date}/theme_stocks.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    base_path = Path(args.base) if args.base else predict_dir / "theme_stocks.base.json"
    annotations_path = Path(args.annotations) if args.annotations else predict_dir / "theme_stocks.annotations.json"
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.json"

    if not base_path.exists():
        print(f"[ERROR] missing theme_stocks.base.json: {base_path}", file=sys.stderr)
        return 1
    if not annotations_path.exists():
        print(f"[ERROR] missing theme_stocks.annotations.json: {annotations_path}", file=sys.stderr)
        return 1

    base = read_json(base_path)
    annotations = read_json(annotations_path)
    if not isinstance(base, dict) or not isinstance(annotations, dict):
        print("[ERROR] base and annotations must be JSON objects", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(base, args.date, str(base_path))
        ensure_doc_date(annotations, args.date, str(annotations_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if base.get("schema_version") != "daily_theme_stocks_base.v1":
        print("[ERROR] base schema_version must be daily_theme_stocks_base.v1", file=sys.stderr)
        return 1
    if annotations.get("schema_version") != "daily_theme_stocks_annotations.v1":
        print("[ERROR] annotations schema_version must be daily_theme_stocks_annotations.v1", file=sys.stderr)
        return 1

    doc = merge_theme_stock_annotations(base, annotations, args.date)
    write_json(output_path, doc)
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
