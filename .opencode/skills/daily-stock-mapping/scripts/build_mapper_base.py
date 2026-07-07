#!/usr/bin/env python3
"""Build predict/{date}/mapper.base.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mapper_json_lib import (
    build_base_from_annotations,
    build_mapper_from_markdown,
    default_predict_dir,
    ensure_doc_date,
    load_pool,
    read_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build mapper.base.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--legacy-md", action="store_true", help="Build from legacy mapper.md instead of annotations")
    parser.add_argument("--mapper-md", help="Path to legacy mapper.md; default predict/{date}/mapper.md when --legacy-md is set")
    parser.add_argument("--annotations", help="Path to mapper.annotations.json; default predict/{date}/mapper.annotations.json")
    parser.add_argument("--pool", help="Path to pool_indicators.json; default predict/{date}/pool_indicators.json")
    parser.add_argument("--theme-stocks", help="Path to enriched theme_stocks.md; default predict/{date}/theme_stocks.md")
    parser.add_argument("--output", help="Path to mapper.base.json; default predict/{date}/mapper.base.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    annotations_path = Path(args.annotations) if args.annotations else predict_dir / "mapper.annotations.json"
    pool_path = Path(args.pool) if args.pool else predict_dir / "pool_indicators.json"
    theme_stocks_path = Path(args.theme_stocks) if args.theme_stocks else predict_dir / "theme_stocks.md"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.base.json"

    pool = load_pool(pool_path)
    if args.legacy_md:
        mapper_path = Path(args.mapper_md) if args.mapper_md else predict_dir / "mapper.md"
        if not mapper_path.exists():
            print(f"[ERROR] missing legacy mapper.md: {mapper_path}", file=sys.stderr)
            return 1
        mapper_text = mapper_path.read_text(encoding="utf-8")
        doc = build_mapper_from_markdown(args.date, mapper_text, pool)
        doc["schema_version"] = "daily_mapper_base.v1"
        mode = "markdown-bridge"
    else:
        if not annotations_path.exists():
            print(f"[ERROR] missing mapper.annotations.json: {annotations_path}", file=sys.stderr)
            return 1
        annotations = read_json(annotations_path)
        if not isinstance(annotations, dict):
            print("[ERROR] annotations must be a JSON object", file=sys.stderr)
            return 1
        try:
            ensure_doc_date(annotations, args.date, str(annotations_path))
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        theme_stocks_text = theme_stocks_path.read_text(encoding="utf-8") if theme_stocks_path.exists() else None
        doc = build_base_from_annotations(args.date, annotations, pool, theme_stocks_text)
        mode = "annotations"
    write_json(output_path, doc)
    print(f"OK: wrote {output_path} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
