#!/usr/bin/env python3
"""Validate separated executable and observation annotations (v3)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    EXECUTION_ROLES,
    MAPPER_ANNOTATIONS_SCHEMA_VERSION,
    RISK_POSTURES,
    STOP_LOSS_BASES,
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
)

CODE_RE = re.compile(r"^(sh|sz)\d{6}$")
DIRECTIONS = {"持有偏多", "持有", "谨慎持有", "观望"}
STRATEGIES = {"趋势跟随", "回调布局", "强势接力", "防御布局"}
RISKS = {"low", "medium", "high", "critical"}
TRADEABILITIES = {"Suitable", "Watch", "Extended", "Avoid"}
COMPUTE_OWNED_STOCK_FIELDS = {
    "overnight_score",
    "absolute_score",
    "rank",
    "tier",
    "rank_tier",
    "score_trace",
    "score_status",
    "trend_raw",
    "execution_state",
    "execution_eligibility",
    "observation_reasons",
    "primary_observation_reason",
    "market_board",
    "primary_theme",
    "themes",
    "theme_support_shadow",
}
OBSERVATION_EXECUTION_FIELDS = {
    "tradeability",
    "direction",
    "execution_role",
    "execution_condition",
    "trading_strategy",
    "risk_severity",
    "expected_premium",
    "key_reason",
    "t_plus_1_plan",
    "rules_applied",
    "reasoning_trace",
    "position",
    "stop_loss",
    "stop_loss_basis",
    "stop_loss_price",
}
FORBIDDEN_ACCOUNT_SIZING_FIELDS = {
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


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _forbidden_paths(value: Any, path: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            if key in FORBIDDEN_ACCOUNT_SIZING_FIELDS:
                paths.append(nested_path)
            paths.extend(_forbidden_paths(nested, nested_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_forbidden_paths(nested, f"{path}[{index}]"))
    return paths


def _codes(
    values: Any,
    path: str,
    expected: set[str],
    errors: list[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(values, list):
        errors.append(f"{path}: must be list")
        return [], set()
    rows: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, item in enumerate(values):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path}: must be object")
            continue
        rows.append(item)
        code = item.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            errors.append(f"{item_path}.code: invalid A-share code")
            continue
        codes.append(code)
    if len(codes) != len(set(codes)):
        errors.append(f"{path}: duplicate codes")
    actual = set(codes)
    if actual != expected:
        errors.append(
            f"{path}: exact coverage mismatch "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    return rows, actual


def validate(
    doc: Any,
    date: str,
    executable_codes: set[str],
    observation_codes: set[str],
    base: dict | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["root: must be object"]
    if doc.get("schema_version") != MAPPER_ANNOTATIONS_SCHEMA_VERSION:
        errors.append(
            f"schema_version: must be {MAPPER_ANNOTATIONS_SCHEMA_VERSION}"
        )
    if doc.get("date") != date:
        errors.append(f"date: must be {date}")
    assessment = doc.get("market_assessment")
    if not isinstance(assessment, dict):
        assessment = {}
        errors.append("market_assessment: must be object")
    for field in ("regime_hint", "tomorrow_expectation", "reasoning_trace"):
        if not _nonempty_string(assessment.get(field)):
            errors.append(
                f"market_assessment.{field}: must be non-empty string"
            )
    if assessment.get("risk_severity") not in RISKS:
        errors.append(
            "market_assessment.risk_severity: invalid enum"
        )
    strategy = doc.get("strategy")
    if not isinstance(strategy, dict):
        strategy = {}
        errors.append("strategy: must be object")
    posture = strategy.get("risk_posture")
    if posture not in RISK_POSTURES:
        errors.append("strategy.risk_posture: invalid enum")
    if not _nonempty_string(strategy.get("execution_principle")):
        errors.append("strategy.execution_principle: must be non-empty string")
    controls = strategy.get("risk_control")
    if not isinstance(controls, list) or any(
        not _nonempty_string(value) for value in controls
    ):
        errors.append("strategy.risk_control: must be string array")
    if strategy.get("execution_window") != "14:50-14:57":
        errors.append("strategy.execution_window: must be 14:50-14:57")
    for path in _forbidden_paths(doc):
        errors.append(f"{path}: account sizing field not allowed")

    executable_rows, actual_executable = _codes(
        doc.get("executable_annotations"),
        "executable_annotations",
        executable_codes,
        errors,
    )
    observation_rows, actual_observation = _codes(
        doc.get("observation_annotations"),
        "observation_annotations",
        observation_codes,
        errors,
    )
    overlap = sorted(actual_executable & actual_observation)
    if overlap:
        errors.append(f"annotation code overlap: {overlap}")

    base = base if isinstance(base, dict) else {}
    base_by_code = {
        item.get("code"): item
        for item in base.get("executable_stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    for index, item in enumerate(executable_rows):
        path = f"executable_annotations[{index}]"
        for field in COMPUTE_OWNED_STOCK_FIELDS:
            if field in item:
                errors.append(
                    f"{path}.{field}: deterministic field not allowed"
                )
        if item.get("direction") not in DIRECTIONS:
            errors.append(f"{path}.direction: invalid enum")
        if item.get("tradeability") not in TRADEABILITIES:
            errors.append(f"{path}.tradeability: invalid enum")
        if "execution_role" not in item:
            errors.append(f"{path}.execution_role: required")
        elif item.get("execution_role") not in EXECUTION_ROLES:
            errors.append(f"{path}.execution_role: invalid enum")
        if item.get("trading_strategy") not in STRATEGIES:
            errors.append(f"{path}.trading_strategy: invalid enum")
        if item.get("risk_severity") not in RISKS:
            errors.append(f"{path}.risk_severity: invalid enum")
        for field in (
            "expected_premium",
            "key_reason",
            "execution_condition",
            "reasoning_trace",
        ):
            if not _nonempty_string(item.get(field)):
                errors.append(f"{path}.{field}: must be non-empty string")
        rules = item.get("rules_applied")
        if not isinstance(rules, list) or any(
            not isinstance(value, str) for value in rules
        ):
            errors.append(f"{path}.rules_applied: must be string array")
        plan = item.get("t_plus_1_plan")
        if not isinstance(plan, dict):
            errors.append(f"{path}.t_plus_1_plan: must be object")
        else:
            if "stop_loss" in plan or "stop_loss_price" in plan:
                errors.append(
                    f"{path}.t_plus_1_plan: deterministic stop text/price not allowed"
                )
            for field in ("auction_condition", "open_strategy", "take_profit"):
                if not _nonempty_string(plan.get(field)):
                    errors.append(
                        f"{path}.t_plus_1_plan.{field}: must be non-empty string"
                    )
            if plan.get("stop_loss_basis") not in STOP_LOSS_BASES:
                errors.append(
                    f"{path}.t_plus_1_plan.stop_loss_basis: invalid enum"
                )
        base_stock = base_by_code.get(item.get("code"))
        if not isinstance(base_stock, dict):
            errors.append(f"{path}.code: executable base join missing")
            continue
        exemption = base_stock.get("i14_exemption")
        if exemption == "cautious_hold" and item.get("direction") in {
            "持有",
            "持有偏多",
        }:
            errors.append(
                f"{path}.direction: cautious_hold caps direction at 谨慎持有"
            )
        for error in reasoning_invariant_errors(base_stock, item):
            errors.append(f"{path}: {error}")

    for index, item in enumerate(observation_rows):
        path = f"observation_annotations[{index}]"
        for field in sorted(OBSERVATION_EXECUTION_FIELDS & set(item)):
            errors.append(f"{path}.{field}: execution field not allowed")
        for field in ("observation_summary", "watch_condition", "risk_note"):
            if not _nonempty_string(item.get(field)):
                errors.append(f"{path}.{field}: must be non-empty string")
    primary_exists = any(
        item.get("execution_role") == "primary" for item in executable_rows
    )
    if primary_exists and posture == "zero":
        errors.append("strategy.risk_posture: must not be zero when primary exists")
    if not primary_exists and posture in RISK_POSTURES - {"zero"}:
        errors.append("strategy.risk_posture: must be zero when no primary exists")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    input_path = (
        Path(args.input)
        if args.input
        else intraday_dir(args.date) / "intraday_mapper.annotations.json"
    )
    base_path = (
        Path(args.base)
        if args.base
        else intraday_dir(args.date) / "intraday_mapper.base.json"
    )
    if not input_path.exists() or not base_path.exists():
        print("[ERROR] annotations or base file is missing", file=sys.stderr)
        return 1
    base = read_json(base_path)
    executable_codes = {
        item.get("code")
        for item in base.get("executable_stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    observation_codes = {
        item.get("code")
        for item in base.get("observation_stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    errors = validate(
        read_json(input_path),
        args.date,
        executable_codes,
        observation_codes,
        base=base,
    )
    if errors:
        print(
            f"[ERROR] {input_path} failed validation ({len(errors)} errors):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
