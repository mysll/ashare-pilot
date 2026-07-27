#!/usr/bin/env python3
"""Validate intraday_operation_decision.v2 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.operations.mechanical_classification import CLASS_RANK
from ashare_pilot.position_tier import POSITION_TIERS


def resolve_reference(value: str, reference_base: Path | None) -> Path:
    path = Path(value)
    return path if path.is_absolute() or reference_base is None else reference_base / path


def validate(
    doc: dict[str, Any],
    reference_base: Path | None = None,
    require_references: bool = False,
) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "intraday_operation_decision.v2":
        errors.append("schema_version: invalid")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        errors.append("date: invalid")
    source = doc.get("source_snapshot")
    source_hash = doc.get("source_snapshot_sha256")
    if not isinstance(source, str) or not source:
        errors.append("source_snapshot: invalid")
    elif not isinstance(source_hash, str) or not re.match(r"^[0-9a-f]{64}$", source_hash):
        errors.append("source_snapshot_sha256: must be lowercase SHA256")
    else:
        source_path = resolve_reference(source, reference_base)
        if require_references and not source_path.exists():
            errors.append("source_snapshot: file does not exist")
        elif source_path.exists() and hashlib.sha256(source_path.read_bytes()).hexdigest() != source_hash:
            errors.append("source_snapshot_sha256: does not match source snapshot")
    action = doc.get("global_action")
    if action not in {"NORMAL", "SELECTIVE", "WAIT", "NO_NEW_BUY"}:
        errors.append("global_action: invalid")
    delivery = doc.get("delivery_confirmation")
    if not isinstance(delivery, dict) or delivery.get("execution_action") not in {"EVALUATE", "WAIT_SECOND_CONFIRMATION", "OBSERVE_ONLY"}:
        errors.append("delivery_confirmation: invalid")
    stocks = doc.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        errors.append("stocks: must be non-empty list")
        return errors
    seen: set[str] = set()
    total = 0
    for index, stock in enumerate(stocks):
        base = f"stocks[{index}]"
        code = stock.get("code") if isinstance(stock, dict) else None
        if not isinstance(code, str) or not re.match(r"^(sh|sz)\d{6}$", code):
            errors.append(f"{base}.code: invalid")
        elif code in seen:
            errors.append(f"{base}.code: duplicate")
        else:
            seen.add(code)
        mechanical = stock.get("mechanical_class")
        maximum = stock.get("max_allowed_class")
        final = stock.get("final_class")
        if any(item not in CLASS_RANK for item in (mechanical, maximum, final)):
            errors.append(f"{base}: invalid class")
        elif CLASS_RANK[final] > CLASS_RANK[maximum]:
            errors.append(f"{base}.final_class: exceeds max allowed class")
        position = stock.get("final_position_tier")
        if position not in POSITION_TIERS:
            errors.append(f"{base}.final_position_tier: invalid")
        else:
            if position != "WATCH_ONLY":
                total += 1
            if final != "A" and position != "WATCH_ONLY":
                errors.append(f"{base}.final_position_tier: non-A class must be WATCH_ONLY")
        controls = stock.get("t1_controls")
        if not isinstance(controls, dict) or controls.get("same_day_sell_allowed") is not False:
            errors.append(f"{base}.t1_controls: same-day sell must be false")
    portfolio = doc.get("portfolio")
    expected = total
    if not isinstance(portfolio, dict) or portfolio.get("actionable_positions") != expected:
        errors.append("portfolio.actionable_positions: does not match stock total")
    elif isinstance(portfolio.get("allocation"), dict):
        allocated = portfolio["allocation"].get("allocated_positions")
        if allocated != expected:
            errors.append("portfolio.allocation.allocated_positions: does not match decision total")
    if action == "NO_NEW_BUY" and expected:
        errors.append("portfolio.actionable_positions: NO_NEW_BUY must be zero")
    if isinstance(delivery, dict) and delivery.get("execution_action") in {"WAIT_SECOND_CONFIRMATION", "OBSERVE_ONLY"} and expected:
        errors.append("portfolio.actionable_positions: delivery gate must be zero")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate operation decision")
    parser.add_argument("path")
    parser.add_argument("--portable", action="store_true", help="Allow source snapshot to be absent")
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
