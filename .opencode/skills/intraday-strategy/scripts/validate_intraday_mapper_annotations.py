#!/usr/bin/env python3
"""Validate LLM-authored intraday_mapper.annotations.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from intraday_mapper_json_lib import intraday_dir, read_json

CODE_RE = re.compile(r"^(sh|sz)\d{6}$")
DIRECTIONS = {"持有偏多", "持有", "谨慎持有", "观望"}
STRATEGIES = {"趋势跟随", "回调布局", "强势接力", "防御布局"}
RISKS = {"low", "medium", "high", "critical"}


def validate(doc: Any, date: str, allowed_codes: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["root: must be object"]
    if doc.get("schema_version") != "intraday_mapper_annotations.v1":
        errors.append("schema_version: must be intraday_mapper_annotations.v1")
    if doc.get("date") != date:
        errors.append(f"date: must be {date}")
    assessment = doc.get("market_assessment")
    if not isinstance(assessment, dict):
        errors.append("market_assessment: must be object")
    elif not isinstance(assessment.get("reasoning_trace"), str) or not assessment["reasoning_trace"].strip():
        errors.append("market_assessment.reasoning_trace: must be non-empty string")
    stocks = doc.get("stocks")
    if not isinstance(stocks, list):
        errors.append("stocks: must be list")
        return errors
    seen: set[str] = set()
    for i, item in enumerate(stocks):
        path = f"stocks[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: must be object")
            continue
        code = item.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            errors.append(f"{path}.code: invalid A-share code")
        elif code not in allowed_codes:
            errors.append(f"{path}.code: {code} is not in compute opportunity pool")
        elif code in seen:
            errors.append(f"{path}.code: duplicate {code}")
        else:
            seen.add(code)
        if item.get("direction") not in DIRECTIONS:
            errors.append(f"{path}.direction: invalid enum")
        if item.get("trading_strategy") not in STRATEGIES:
            errors.append(f"{path}.trading_strategy: invalid enum")
        if item.get("risk_severity") not in RISKS:
            errors.append(f"{path}.risk_severity: invalid enum")
        for field in ("expected_premium", "key_reason", "reasoning_trace"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{path}.{field}: must be non-empty string")
    strategy = doc.get("strategy")
    if not isinstance(strategy, dict):
        errors.append("strategy: must be object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--base")
    args = parser.parse_args()
    input_path = Path(args.input) if args.input else intraday_dir(args.date) / "intraday_mapper.annotations.json"
    base_path = Path(args.base) if args.base else intraday_dir(args.date) / "intraday_mapper.base.json"
    if not input_path.exists() or not base_path.exists():
        print("[ERROR] annotations or base file is missing", file=sys.stderr)
        return 1
    base = read_json(base_path)
    allowed = {
        item.get("code")
        for item in base.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    errors = validate(read_json(input_path), args.date, allowed)
    if errors:
        print(f"[ERROR] {input_path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
