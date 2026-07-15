#!/usr/bin/env python3
"""Compare Step 3 shadow outputs without regenerating historical strategies."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


ROLE_TAGS = {"ThemeLibrary", "MarketActive", "NewsDirect", "MultiTheme", "Anchor", "LHB"}
LIVE_PROFILE_FIELDS = ("playbook", "preferred_anchor", "chase_policy", "entry_window", "stop_policy", "time_horizon", "position_budget")


def source_grounding(stock: dict) -> dict:
    text = str(stock.get("reasoning", {}).get("source_basis") or "")
    return {
        "news_refs": sorted(set(re.findall(r"news#\d+", text))),
        "role_tags": sorted(
            tag for tag in ROLE_TAGS
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(tag)}(?![A-Za-z0-9_])", text)
        ),
    }


def profile_projection(stock: dict, mode: str):
    profile = stock.get("profile")
    if mode == "frozen" or not isinstance(profile, dict):
        return profile
    return {field: profile.get(field) for field in LIVE_PROFILE_FIELDS}


def compare(before: dict, after: dict, mode: str = "frozen") -> dict:
    if mode not in {"frozen", "live"}:
        raise ValueError(f"unsupported comparison mode: {mode}")
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
    field_differences = {}
    before_by_code = {item.get("code"): item for item in b}
    after_by_code = {item.get("code"): item for item in a}
    locked_fields = ("rating", "position_budget", "entry_profile", "anchor", "rules_applied")
    profile_differences = {}
    source_grounding_differences = {}
    for code in before_codes:
        if code not in after_by_code:
            continue
        changes = {
            field: {"before": before_by_code[code].get(field), "after": after_by_code[code].get(field)}
            for field in locked_fields
            if before_by_code[code].get(field) != after_by_code[code].get(field)
        }
        if changes:
            field_differences[code] = changes
        before_profile = profile_projection(before_by_code[code], mode)
        after_profile = profile_projection(after_by_code[code], mode)
        if before_profile != after_profile:
            profile_differences[code] = {"before": before_profile, "after": after_profile}
        before_sources = source_grounding(before_by_code[code])
        after_sources = source_grounding(after_by_code[code])
        if before_sources != after_sources:
            source_grounding_differences[code] = {"before": before_sources, "after": after_sources}
    if field_differences:
        blocked.append("selected stock rating/budget/entry/anchor/rules changed")
    if profile_differences:
        blocked.append(f"selected stock {'full' if mode == 'frozen' else 'material'} profile changed")
    if source_grounding_differences:
        blocked.append("selected stock source grounding changed")
    return {
        "before_codes": before_codes,
        "after_codes": after_codes,
        "before_direction_distribution": dict(Counter(item.get("direction") for item in b)),
        "after_direction_distribution": dict(Counter(item.get("direction") for item in a)),
        "before_regime": before_regime,
        "after_regime": after_regime,
        "added": sorted({item.get("code") for item in a} - {item.get("code") for item in b}),
        "removed": sorted({item.get("code") for item in b} - {item.get("code") for item in a}),
        "field_differences": field_differences,
        "profile_differences": profile_differences,
        "source_grounding_differences": source_grounding_differences,
        "mode": mode,
        "blocked": blocked,
        "passed": not blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two strategy shadow outputs")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--report-only", action="store_true", help="Print differences without failing")
    parser.add_argument("--mode", choices=("frozen", "live"), default="frozen")
    args = parser.parse_args()
    before, after = load(args.before), load(args.after)
    report = compare(before, after, mode=args.mode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.report_only or report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
