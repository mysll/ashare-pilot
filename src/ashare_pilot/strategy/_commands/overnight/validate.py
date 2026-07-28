#!/usr/bin/env python3
"""Validate overnight_strategy.v2 and its exact mapper projection."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    HOLD_DIRECTIONS,
    OVERNIGHT_STRATEGY_SCHEMA_VERSION,
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
    resolved_stop_loss,
)
from ashare_pilot.strategy._commands.overnight.build import (
    executable_projection,
    observation_projection,
)

CODE_RE = re.compile(r"^(sh|sz)\d{6}$")
NON_ACTIONABLE_DIRECTIONS = {"观望"}
OBSERVATION_FORBIDDEN = {
    "direction",
    "tradeability",
    "trading_strategy",
    "position",
    "position_plan",
    "t_plus_1_plan",
    "stop_loss",
    "stop_loss_basis",
    "stop_loss_price",
    "rules_applied",
}


def _codes(values: Any, path: str, errors: list[str]) -> set[str]:
    if not isinstance(values, list):
        errors.append(f"{path}: must be list")
        return set()
    codes = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}]: must be object")
            continue
        code = item.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            errors.append(f"{path}[{index}].code: invalid")
        else:
            codes.append(code)
    if len(codes) != len(set(codes)):
        errors.append(f"{path}: duplicate codes")
    return set(codes)


def validate(
    document: Any,
    date: str,
    mapper: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["root: must be object"]
    if document.get("schema_version") != OVERNIGHT_STRATEGY_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {OVERNIGHT_STRATEGY_SCHEMA_VERSION}"
        )
    if document.get("date") != date:
        errors.append(f"date must be {date}")
    if not isinstance(document.get("market_assessment"), dict):
        errors.append("market_assessment must be object")
    if not isinstance(document.get("strategy"), dict):
        errors.append("strategy must be object")
    recommendation_codes = _codes(
        document.get("recommendations"), "recommendations", errors
    )
    eligible_codes = _codes(
        document.get("eligible_watchlist"), "eligible_watchlist", errors
    )
    observation_codes = _codes(
        document.get("observations"), "observations", errors
    )
    if recommendation_codes & eligible_codes:
        errors.append("recommendations and eligible_watchlist overlap")
    if (recommendation_codes | eligible_codes) & observation_codes:
        errors.append("executable views and observations overlap")
    for index, item in enumerate(document.get("recommendations", [])):
        if isinstance(item, dict) and item.get("direction") not in HOLD_DIRECTIONS:
            errors.append(
                f"recommendations[{index}].direction must be actionable"
            )
    for index, item in enumerate(document.get("eligible_watchlist", [])):
        if not isinstance(item, dict):
            continue
        if item.get("direction") not in NON_ACTIONABLE_DIRECTIONS:
            errors.append(
                "eligible_watchlist"
                f"[{index}].direction must be one of "
                f"{sorted(NON_ACTIONABLE_DIRECTIONS)}"
            )
        plan = item.get("t_plus_1_plan")
        if not isinstance(plan, dict) or plan.get(
            "stop_loss_basis"
        ) != "not_applicable":
            errors.append(
                f"eligible_watchlist[{index}].t_plus_1_plan must use not_applicable"
            )
    for index, item in enumerate(document.get("observations", [])):
        if not isinstance(item, dict):
            continue
        for field in sorted(OBSERVATION_FORBIDDEN & set(item)):
            errors.append(f"observations[{index}].{field}: forbidden")
    if isinstance(mapper, dict):
        mapper_executable = {
            item.get("code"): item
            for item in mapper.get("executable_stocks", [])
            if isinstance(item, dict)
        }
        mapper_observations = {
            item.get("code"): item
            for item in mapper.get("observation_stocks", [])
            if isinstance(item, dict)
        }
        executable_expected = {
            code for code in mapper_executable
        }
        observation_expected = {
            item.get("code")
            for item in mapper.get("observation_stocks", [])
            if isinstance(item, dict)
        }
        if recommendation_codes | eligible_codes != executable_expected:
            errors.append(
                "recommendations union eligible_watchlist must exactly cover executable"
            )
        if observation_codes != observation_expected:
            errors.append("observations must exactly cover observation pool")
        for index, item in enumerate(document.get("recommendations", [])):
            if not isinstance(item, dict):
                continue
            source = mapper_executable.get(item.get("code"))
            reasoning = source.get("reasoning") if isinstance(source, dict) else None
            if not isinstance(source, dict) or not isinstance(reasoning, dict):
                errors.append(f"recommendations[{index}]: mapper reasoning join missing")
                continue
            if item != executable_projection(source):
                errors.append(
                    f"recommendations[{index}]: must exactly match mapper projection"
                )
            for error in reasoning_invariant_errors(source, reasoning):
                errors.append(f"recommendations[{index}]: {error}")
        for index, item in enumerate(document.get("eligible_watchlist", [])):
            if not isinstance(item, dict):
                continue
            source = mapper_executable.get(item.get("code"))
            if not isinstance(source, dict):
                errors.append(
                    f"eligible_watchlist[{index}]: mapper join missing"
                )
                continue
            expected = executable_projection(source)
            expected["t_plus_1_plan"] = resolved_stop_loss(
                source, "not_applicable"
            )
            if item != expected:
                errors.append(
                    "eligible_watchlist"
                    f"[{index}]: must exactly match mapper projection"
                )
        for index, item in enumerate(document.get("observations", [])):
            if not isinstance(item, dict):
                continue
            source = mapper_observations.get(item.get("code"))
            if not isinstance(source, dict):
                errors.append(f"observations[{index}]: mapper join missing")
                continue
            if item != observation_projection(source):
                errors.append(
                    f"observations[{index}]: must exactly match mapper projection"
                )
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--mapper")
    args = parser.parse_args(argv)
    path = (
        Path(args.input)
        if args.input
        else intraday_dir(args.date) / "overnight_strategy.json"
    )
    mapper_path = (
        Path(args.mapper)
        if args.mapper
        else intraday_dir(args.date) / "intraday_mapper.json"
    )
    try:
        document = read_json(path)
        mapper = read_json(mapper_path) if mapper_path.exists() else None
    except (OSError, ValueError) as exc:
        print(f"[ERROR] strategy unreadable: {exc}", file=sys.stderr)
        return 1
    errors = validate(document, args.date, mapper)
    if errors:
        print(f"[ERROR] {path} failed validation:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"OK: {path} "
        f"({len(document['recommendations'])} recommendations, "
        f"{len(document['eligible_watchlist'])} eligible watch, "
        f"{len(document['observations'])} observations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
