#!/usr/bin/env python3
"""Validate overnight_strategy.v3 and its exact mapper projection."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    HOLD_DIRECTIONS,
    OVERNIGHT_STRATEGY_SCHEMA_VERSION,
    RISK_POSTURES,
    STOP_LOSS_BASES,
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
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
    "position_cap",
    "position_pct",
    "position_amount",
    "share_count",
    "lot_count",
    "quantity",
    "qty",
    "execution_role",
    "execution_condition",
    "t_plus_1_plan",
    "stop_loss",
    "stop_loss_basis",
    "stop_loss_price",
    "rules_applied",
}
REMOVED_ACCOUNT_SIZING_FIELDS = {
    "position",
    "position_plan",
    "position_cap",
    "position_pct",
    "position_percent",
    "position_amount",
    "cash_amount",
    "order_amount",
    "position_shares",
    "share_count",
    "position_lots",
    "lot_count",
    "quantity",
    "qty",
}


def _removed_paths(value: Any, path: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            if key in REMOVED_ACCOUNT_SIZING_FIELDS:
                paths.append(nested_path)
            paths.extend(_removed_paths(nested, nested_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_removed_paths(nested, f"{path}[{index}]"))
    return paths


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
        strategy = {}
    else:
        strategy = document["strategy"]
    posture = strategy.get("risk_posture")
    if posture not in RISK_POSTURES:
        errors.append("strategy.risk_posture must be a supported value")
    if not isinstance(strategy.get("execution_principle"), str) or not strategy[
        "execution_principle"
    ].strip():
        errors.append("strategy.execution_principle must be non-empty string")
    controls = strategy.get("risk_control")
    if not isinstance(controls, list) or any(
        not isinstance(value, str) or not value.strip() for value in controls
    ):
        errors.append("strategy.risk_control must be a string array")
    if strategy.get("execution_window") != "14:50-14:57":
        errors.append("strategy.execution_window must be 14:50-14:57")
    for path in _removed_paths(document):
        errors.append(f"{path}: removed account sizing field")
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
        if not isinstance(item, dict):
            continue
        if item.get("direction") not in HOLD_DIRECTIONS:
            errors.append(
                f"recommendations[{index}].direction must be actionable"
            )
        if item.get("execution_role") != "primary":
            errors.append(
                f"recommendations[{index}].execution_role must be primary"
            )
        if not isinstance(item.get("execution_condition"), str) or not item[
            "execution_condition"
        ].strip():
            errors.append(
                f"recommendations[{index}].execution_condition must be non-empty"
            )
        if item.get("tradeability") == "Watch" and item.get(
            "direction"
        ) != "谨慎持有":
            errors.append(
                f"recommendations[{index}]: Watch primary requires 谨慎持有"
            )
        if item.get("tradeability") in {"Extended", "Avoid"}:
            errors.append(
                f"recommendations[{index}]: Extended/Avoid cannot be primary"
            )
        state = item.get("execution_state")
        if not isinstance(state, dict) or state.get("eligible") is not True:
            errors.append(
                f"recommendations[{index}].execution_state must be eligible"
            )
        plan = item.get("t_plus_1_plan")
        if not isinstance(plan, dict) or plan.get(
            "stop_loss_basis"
        ) not in STOP_LOSS_BASES - {"not_applicable"}:
            errors.append(
                f"recommendations[{index}].t_plus_1_plan must use executable basis"
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
        if item.get("execution_role") not in {"alternative", "watch"}:
            errors.append(
                f"eligible_watchlist[{index}].execution_role must be alternative or watch"
            )
        if not isinstance(item.get("execution_condition"), str) or not item[
            "execution_condition"
        ].strip():
            errors.append(
                f"eligible_watchlist[{index}].execution_condition must be non-empty"
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
    primary_exists = bool(recommendation_codes)
    if primary_exists and posture == "zero":
        errors.append("strategy.risk_posture must not be zero with recommendations")
    if not primary_exists and posture in RISK_POSTURES - {"zero"}:
        errors.append("strategy.risk_posture must be zero without recommendations")
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
        executable_expected = set(mapper_executable)
        recommendation_expected = {
            code
            for code, item in mapper_executable.items()
            if isinstance(item.get("reasoning"), dict)
            and item["reasoning"].get("execution_role") == "primary"
        }
        eligible_expected = {
            code
            for code, item in mapper_executable.items()
            if isinstance(item.get("reasoning"), dict)
            and item["reasoning"].get("execution_role")
            in {"alternative", "watch"}
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
        if recommendation_codes != recommendation_expected:
            errors.append("recommendations must exactly equal mapper primary roles")
        if eligible_codes != eligible_expected:
            errors.append(
                "eligible_watchlist must exactly equal mapper alternative/watch roles"
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
            if item != expected:
                errors.append(
                    "eligible_watchlist"
                    f"[{index}]: must exactly match mapper projection"
                )
        if document.get("strategy") != mapper.get("strategy"):
            errors.append("strategy must exactly match mapper projection")
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
