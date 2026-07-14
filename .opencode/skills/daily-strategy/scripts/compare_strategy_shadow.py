#!/usr/bin/env python3
"""Compare Step 3 shadow outputs without regenerating historical strategies."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def compare(before: dict, after: dict) -> dict:
    b = [item for item in before.get("stocks", []) if isinstance(item, dict)]
    a = [item for item in after.get("stocks", []) if isinstance(item, dict)]
    before_codes = [item.get("code") for item in b]
    after_codes = [item.get("code") for item in a]
    before_directions = {item.get("code"): item.get("direction") for item in b}
    after_directions = {item.get("code"): item.get("direction") for item in a}
    before_regime = before.get("market", {}).get("regime_prior") if isinstance(before.get("market"), dict) else None
    after_regime = after.get("market", {}).get("regime_prior") if isinstance(after.get("market"), dict) else None
    blocked = []
    if before_codes != after_codes:
        blocked.append("selected stock codes/order changed")
    if before_directions != after_directions:
        blocked.append("selected stock directions changed")
    if before_regime != after_regime:
        blocked.append("market regime changed")
    return {
        "before_codes": before_codes,
        "after_codes": after_codes,
        "before_direction_distribution": dict(Counter(item.get("direction") for item in b)),
        "after_direction_distribution": dict(Counter(item.get("direction") for item in a)),
        "before_regime": before_regime,
        "after_regime": after_regime,
        "added": sorted({item.get("code") for item in a} - {item.get("code") for item in b}),
        "removed": sorted({item.get("code") for item in b} - {item.get("code") for item in a}),
        "blocked": blocked,
        "passed": not blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two strategy shadow outputs")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--report-only", action="store_true", help="Print differences without failing")
    args = parser.parse_args()
    before, after = load(args.before), load(args.after)
    report = compare(before, after)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.report_only or report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
