#!/usr/bin/env python3
"""Build predict/{date}/mapper.json from JSON base + annotations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mapper_json_lib import (
    default_predict_dir,
    ensure_doc_date,
    merge_annotations,
    read_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build mapper.json sidecar")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--base", help="Path to mapper.base.json; default predict/{date}/mapper.base.json")
    parser.add_argument("--annotations", help="Path to mapper.annotations.json; default predict/{date}/mapper.annotations.json")
    parser.add_argument("--output", help="Path to mapper.json; default predict/{date}/mapper.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    base_path = Path(args.base) if args.base else predict_dir / "mapper.base.json"
    annotations_path = Path(args.annotations) if args.annotations else predict_dir / "mapper.annotations.json"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.json"

    if not annotations_path.exists():
        print(f"[ERROR] missing mapper.annotations.json: {annotations_path}", file=sys.stderr)
        return 1
    if not base_path.exists():
        print(f"[ERROR] missing mapper.base.json: {base_path}", file=sys.stderr)
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
    doc = merge_annotations(base, annotations, args.date)
    mode = "annotations"
    write_json(output_path, doc)
    print(f"OK: wrote {output_path} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
