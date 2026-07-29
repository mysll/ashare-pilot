#!/usr/bin/env python3
"""Validate strategy.draft.json against its exact compact input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .draft_link import INPUT_HASH_FILENAME, validate_draft_link
from .finalize import validate_draft
from ashare_pilot.market_data.runtime import workspace_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate selected-only Step 3 draft")
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--input-hash")
    parser.add_argument("--draft")
    args = parser.parse_args(argv)
    pdir = workspace_path("predict", args.date)
    try:
        input_path = Path(args.input) if args.input else pdir / ".strategy_llm_input.json"
        input_hash_path = Path(args.input_hash) if args.input_hash else input_path.with_name(INPUT_HASH_FILENAME)
        draft_path = Path(args.draft) if args.draft else pdir / "strategy.draft.json"
        compact = json.loads(input_path.read_text(encoding="utf-8-sig"))
        draft = json.loads(draft_path.read_text(encoding="utf-8-sig"))
        errors = validate_draft_link(compact, draft_path, input_hash_path)
        errors.extend(validate_draft(draft, compact, args.date))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if errors:
        print("[ERROR] draft validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("OK: strategy draft is linked and valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
