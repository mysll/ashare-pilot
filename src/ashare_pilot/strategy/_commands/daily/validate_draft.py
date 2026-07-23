#!/usr/bin/env python3
"""Validate strategy.draft.json against its exact compact input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .finalize import validate_draft
from ashare_pilot.market_data.runtime import workspace_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate selected-only Step 3 draft")
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--draft")
    args = parser.parse_args(argv)
    pdir = workspace_path("predict", args.date)
    try:
        compact = json.loads(Path(args.input or pdir / ".strategy_llm_input.json").read_text(encoding="utf-8-sig"))
        draft = json.loads(Path(args.draft or pdir / "strategy.draft.json").read_text(encoding="utf-8-sig"))
        errors = validate_draft(draft, compact, args.date)
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
