#!/usr/bin/env python3
"""Validate intraday_operation_snapshot.v3 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.operations.mechanical_classification import CLASS_RANK
from ashare_pilot.operations.operation_time import parse_market_datetime
from ashare_pilot.position_tier import POSITION_TIERS, POSITION_TIER_RANK


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def resolve_reference(value: str, reference_base: Path | None) -> Path:
    path = Path(value)
    return path if path.is_absolute() or reference_base is None else reference_base / path


def validate(
    doc: dict[str, Any],
    reference_base: Path | None = None,
    require_references: bool = False,
) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "intraday_operation_snapshot.v3":
        add(errors, "schema_version", "must be intraday_operation_snapshot.v3")
    date_text = doc.get("date")
    if not isinstance(date_text, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
        add(errors, "date", "must be YYYY-MM-DD")
    generated = parse_market_datetime(doc.get("generated_at"))
    if generated is None:
        add(errors, "generated_at", "must be timezone-aware ISO datetime")
    run_mode = doc.get("run_mode")
    if run_mode is not None and run_mode not in {
        "INITIAL_CONFIRMATION", "LATE_INITIAL_CONFIRMATION", "SECOND_CONFIRMATION", "RECHECK", "LATE_OBSERVE_ONLY", "EARLY"
    }:
        add(errors, "run_mode", "invalid enum")
    lineage = doc.get("lineage")
    if run_mode in {"SECOND_CONFIRMATION", "RECHECK"}:
        if not isinstance(lineage, dict):
            add(errors, "lineage", "continuation modes require lineage")
        else:
            previous_path = lineage.get("previous_snapshot")
            previous_hash = lineage.get("previous_snapshot_sha256")
            if not isinstance(previous_path, str) or not previous_path:
                add(errors, "lineage.previous_snapshot", "must be non-empty path")
            elif not isinstance(previous_hash, str) or not re.match(r"^[0-9a-f]{64}$", previous_hash):
                add(errors, "lineage.previous_snapshot_sha256", "must be lowercase SHA256")
            else:
                resolved = resolve_reference(previous_path, reference_base)
                if resolved.exists() and hashlib.sha256(resolved.read_bytes()).hexdigest() != previous_hash:
                    add(errors, "lineage.previous_snapshot_sha256", "does not match previous snapshot")
                elif require_references and not resolved.exists():
                    add(errors, "lineage.previous_snapshot", "file does not exist")
            if not isinstance(lineage.get("chain_root"), str) or not lineage.get("chain_root"):
                add(errors, "lineage.chain_root", "must be non-empty path")
    market = doc.get("market_confirmation")
    if not isinstance(market, dict):
        add(errors, "market_confirmation", "must be object")
        market = {}
    action = market.get("global_action")
    if action not in {"NORMAL", "SELECTIVE", "WAIT", "NO_NEW_BUY"}:
        add(errors, "market_confirmation.global_action", "invalid enum")
    indices = market.get("indices")
    if not isinstance(indices, dict) or not all(code in indices for code in ("sh000001", "sz399001", "sh000688")):
        add(errors, "market_confirmation.indices", "must cover three required indices")
    themes = doc.get("theme_confirmations")
    if not isinstance(themes, dict):
        add(errors, "theme_confirmations", "must be object")
    else:
        for name, theme in themes.items():
            if not isinstance(theme, dict) or theme.get("theme_state") not in {"CONFIRMED", "NARROW", "FADING", "FAILED", "UNKNOWN"}:
                add(errors, f"theme_confirmations.{name}", "invalid theme confirmation")
    delivery = doc.get("delivery_confirmation")
    if not isinstance(delivery, dict):
        add(errors, "delivery_confirmation", "must be object")
        delivery_action = None
    else:
        delivery_action = delivery.get("execution_action")
        if delivery_action not in {"EVALUATE", "WAIT_SECOND_CONFIRMATION", "OBSERVE_ONLY"}:
            add(errors, "delivery_confirmation.execution_action", "invalid enum")

    stocks = doc.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        add(errors, "stocks", "must be non-empty list")
        return errors
    seen: set[str] = set()
    source_schema = doc.get("source_strategy", {}).get("schema_version") if isinstance(doc.get("source_strategy"), dict) else None
    allocated_total = 0
    allocated_by_theme: dict[str, int] = {}
    allocated_names_by_theme: dict[str, int] = {}
    for index, stock in enumerate(stocks):
        base = f"stocks[{index}]"
        if not isinstance(stock, dict):
            add(errors, base, "must be object")
            continue
        code = stock.get("code")
        if not isinstance(code, str) or not re.match(r"^(sh|sz)\d{6}$", code):
            add(errors, f"{base}.code", "invalid A-share code")
        elif code in seen:
            add(errors, f"{base}.code", "duplicate")
        else:
            seen.add(code)
        signals = stock.get("signals")
        if not isinstance(signals, dict):
            add(errors, f"{base}.signals", "must be object")
            continue
        for bar_key in ("first_bar", "latest_completed_bar"):
            bar = signals.get(bar_key)
            if not isinstance(bar, dict):
                add(errors, f"{base}.signals.{bar_key}", "must be object")
                continue
            if bar.get("is_complete"):
                bar_end = parse_market_datetime(bar.get("bar_end"))
                if bar_end is None or generated is None or bar_end > generated:
                    add(errors, f"{base}.signals.{bar_key}.bar_end", "must not be after snapshot time")
        guard = stock.get("decision_guardrails")
        if not isinstance(guard, dict):
            add(errors, f"{base}.decision_guardrails", "must be object")
            continue
        mechanical = guard.get("mechanical_class")
        maximum = guard.get("max_allowed_class")
        if mechanical not in CLASS_RANK or maximum not in CLASS_RANK:
            add(errors, f"{base}.decision_guardrails", "invalid class")
        elif CLASS_RANK[mechanical] > CLASS_RANK[maximum]:
            add(errors, f"{base}.decision_guardrails.mechanical_class", "exceeds max allowed class")
        if action == "NO_NEW_BUY" and maximum in {"A", "B"}:
            add(errors, f"{base}.decision_guardrails.max_allowed_class", "NO_NEW_BUY caps class at C")
        if delivery_action == "WAIT_SECOND_CONFIRMATION" and maximum == "A":
            add(errors, f"{base}.decision_guardrails.max_allowed_class", "late initial 09:40 caps class at B")
        if delivery_action == "OBSERVE_ONLY" and maximum in {"A", "B"}:
            add(errors, f"{base}.decision_guardrails.max_allowed_class", "late observe-only snapshot caps class at C")
        position = guard.get("position_tier")
        if not isinstance(position, dict):
            add(errors, f"{base}.decision_guardrails.position_tier", "must be object")
        else:
            values = [position.get(key) for key in ("morning", "market_adjusted", "signal_adjusted", "portfolio_adjusted", "final")]
            if not all(value in POSITION_TIERS for value in values):
                add(errors, f"{base}.decision_guardrails.position_tier", "all stages must be qualitative tiers")
            elif not all(
                POSITION_TIER_RANK[left] >= POSITION_TIER_RANK[right]
                for left, right in zip(values, values[1:])
            ):
                add(errors, f"{base}.decision_guardrails.position_tier", "tiers must monotonically decrease")
            else:
                allocated = values[4]
                if allocated != "WATCH_ONLY":
                    allocated_total += 1
                    theme = str(stock.get("strategy", {}).get("sector") or "未分类")
                    allocated_by_theme[theme] = allocated_by_theme.get(theme, 0) + 1
                    allocated_names_by_theme[theme] = allocated_names_by_theme.get(theme, 0) + 1
                if delivery_action in {"WAIT_SECOND_CONFIRMATION", "OBSERVE_ONLY"} and allocated != "WATCH_ONLY":
                    add(errors, f"{base}.decision_guardrails.position_tier.final", "delivery gate requires WATCH_ONLY")
        controls = guard.get("t1_controls")
        if not isinstance(controls, dict) or controls.get("same_day_sell_allowed") is not False:
            add(errors, f"{base}.decision_guardrails.t1_controls", "new position must forbid same-day sell")
        elif not isinstance(controls.get("t1_exit_plan"), dict):
            add(errors, f"{base}.decision_guardrails.t1_controls.t1_exit_plan", "must be object")
        elif source_schema == "daily_strategy.v3":
            plan = controls["t1_exit_plan"]
            if plan.get("source") != "daily_strategy.v3":
                add(errors, f"{base}.decision_guardrails.t1_controls.t1_exit_plan.source", "must preserve v3 plan")
            for key in ("overnight_risk", "gap_up_action", "flat_open_action", "gap_down_action"):
                if plan.get(key) is None:
                    add(errors, f"{base}.decision_guardrails.t1_controls.t1_exit_plan.{key}", "missing v3 field")
        transition = stock.get("transition")
        if not isinstance(transition, dict) or transition.get("current_class") != mechanical:
            add(errors, f"{base}.transition", "must match mechanical class")
    allocation = doc.get("portfolio_allocation")
    if not isinstance(allocation, dict):
        add(errors, "portfolio_allocation", "must be object")
    else:
        limits = allocation.get("limits")
        if not isinstance(limits, dict):
            add(errors, "portfolio_allocation.limits", "must be object")
        else:
            total_limit = limits.get("max_new_positions")
            theme_limit = limits.get("max_theme_positions")
            correlated_limit = limits.get("max_correlated_names")
            if source_schema != "daily_strategy.v3" or limits.get("source") != "daily_strategy.v3":
                add(errors, "portfolio_allocation.limits.source", "must preserve v3 portfolio limits")
            if isinstance(total_limit, int) and allocated_total > total_limit:
                add(errors, "portfolio_allocation", "allocated positions exceed total limit")
            for theme, value in allocated_by_theme.items():
                if isinstance(theme_limit, int) and value > theme_limit:
                    add(errors, f"portfolio_allocation.{theme}", "allocated positions exceed theme limit")
                if isinstance(correlated_limit, int) and allocated_names_by_theme[theme] > correlated_limit:
                    add(errors, f"portfolio_allocation.{theme}", "allocated names exceed correlated limit")
        recorded = allocation.get("allocated_positions")
        if recorded != allocated_total:
            add(errors, "portfolio_allocation.allocated_positions", "does not match stock total")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate operation snapshot v3")
    parser.add_argument("path")
    parser.add_argument("--portable", action="store_true", help="Allow referenced files to be absent")
    args = parser.parse_args(argv)
    path = Path(args.path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        return 1
    errors = validate(doc, reference_base=Path.cwd(), require_references=not args.portable)
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
