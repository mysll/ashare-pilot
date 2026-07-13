#!/usr/bin/env python3
"""Merge deterministic intraday base with validated reasoning annotations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from intraday_mapper_json_lib import intraday_dir, merge_annotations, read_json, write_json
from validate_intraday_mapper_annotations import validate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--base")
    parser.add_argument("--annotations")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = intraday_dir(args.date)
    base_path = Path(args.base) if args.base else root / "intraday_mapper.base.json"
    annotations_path = Path(args.annotations) if args.annotations else root / "intraday_mapper.annotations.json"
    output_path = Path(args.output) if args.output else root / "intraday_mapper.json"
    if not base_path.exists() or not annotations_path.exists():
        print("[ERROR] base or annotations file is missing", file=sys.stderr)
        return 1
    base, annotations = read_json(base_path), read_json(annotations_path)
    if not isinstance(base, dict) or base.get("date") != args.date:
        print("[ERROR] invalid base schema/date", file=sys.stderr)
        return 1
    allowed = {item.get("code") for item in base.get("stocks", []) if isinstance(item, dict)}
    errors = validate(annotations, args.date, allowed, base=base)
    if errors:
        print("[ERROR] annotations validation failed; regenerate annotations", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    write_json(output_path, merge_annotations(base, annotations))
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
