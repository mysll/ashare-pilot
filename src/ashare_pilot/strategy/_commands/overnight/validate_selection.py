"""Validate the canonical intraday selection-pools contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.strategy.intraday_selection import selection_invariant_errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate selection_pools.json"
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--input", help="Override selection_pools.json path")
    args = parser.parse_args(argv)
    path = (
        Path(args.input)
        if args.input
        else workspace_path(
            ".cache", "intraday", args.date, "selection_pools.json"
        )
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] selection pools unreadable: {exc}", file=sys.stderr)
        return 1
    errors = selection_invariant_errors(document)
    if document.get("date") != args.date:
        errors.append(f"date must be {args.date}")
    if errors:
        for error in errors:
            print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    print(
        "Selection pools valid: "
        f"executable={len(document['executable_pool'])}, "
        f"observation={len(document['observation_pool'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
