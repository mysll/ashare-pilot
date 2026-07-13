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
TRADEABILITIES = {"Suitable", "Watch", "Extended", "Avoid"}
COMPUTE_OWNED_STOCK_FIELDS = {
    "overnight_score",
    "absolute_score",
    "tier",
    "rank_tier",
    "score_trace",
    "floor_pass",
    "floor_reason",
    "anomaly_flags",
    "i11_flagged",
    "i11_applied",
}
HOLD_DIRECTIONS = {"持有偏多", "持有", "谨慎持有"}
I14_WATCH_MAX = {"观望"}
I14_CAUTIOUS_MAX = {"观望", "谨慎持有"}


def is_zero_position_cap(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return value == 0
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    if normalized in {"0", "0%", "零", "空仓"}:
        return True
    return bool(
        re.fullmatch(r"(?:0(?:\.0+)?%?|空仓)\s*[（(][^）)]*[）)]", normalized)
    )


def validate(doc: Any, date: str, allowed_codes: set[str], base: dict | None = None) -> list[str]:
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

    base = base if isinstance(base, dict) else {}
    base_by_code = {
        item.get("code"): item
        for item in base.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    pool_summary = base.get("pool_summary") if isinstance(base.get("pool_summary"), dict) else {}
    regime = pool_summary.get("regime_snapshot") if isinstance(pool_summary.get("regime_snapshot"), dict) else {}
    up_ratio = regime.get("up_ratio_pct")
    i13_active = isinstance(up_ratio, (int, float)) and up_ratio < 15
    convergence_contract = pool_summary.get("scoring_policy_version") == "convergence_v1"

    seen: set[str] = set()
    for i, item in enumerate(stocks):
        path = f"stocks[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: must be object")
            continue
        for field in COMPUTE_OWNED_STOCK_FIELDS:
            if field in item:
                errors.append(f"{path}.{field}: compute-owned field not allowed in annotations")
        code = item.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            errors.append(f"{path}.code: invalid A-share code")
        elif code not in allowed_codes:
            errors.append(f"{path}.code: {code} is not in compute opportunity pool")
        elif code in seen:
            errors.append(f"{path}.code: duplicate {code}")
        else:
            seen.add(code)
        direction = item.get("direction")
        tradeability = item.get("tradeability")
        if direction not in DIRECTIONS:
            errors.append(f"{path}.direction: invalid enum")
        if convergence_contract and tradeability not in TRADEABILITIES:
            errors.append(f"{path}.tradeability: invalid or missing enum")
        elif tradeability is not None and tradeability not in TRADEABILITIES:
            errors.append(f"{path}.tradeability: invalid enum")
        if item.get("trading_strategy") not in STRATEGIES:
            errors.append(f"{path}.trading_strategy: invalid enum")
        if item.get("risk_severity") not in RISKS:
            errors.append(f"{path}.risk_severity: invalid enum")
        for field in ("expected_premium", "key_reason", "reasoning_trace"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{path}.{field}: must be non-empty string")

        if i13_active and direction in HOLD_DIRECTIONS:
            errors.append(f"{path}.direction: I13 requires 观望 when up_ratio_pct<15")

        base_stock = base_by_code.get(code) if isinstance(code, str) else None
        if isinstance(base_stock, dict):
            exemption = base_stock.get("i14_exemption")
            if exemption == "watch" and direction not in I14_WATCH_MAX and direction in HOLD_DIRECTIONS:
                errors.append(f"{path}.direction: i14_exemption=watch caps tradeability at 观望")
            if exemption == "watch" and tradeability not in {"Watch", "Avoid"}:
                errors.append(f"{path}.tradeability: i14_exemption=watch caps tradeability at Watch")
            if exemption == "cautious_hold" and direction not in I14_CAUTIOUS_MAX and direction in HOLD_DIRECTIONS:
                if direction in {"持有", "持有偏多"}:
                    errors.append(
                        f"{path}.direction: i14_exemption=cautious_hold caps direction at 谨慎持有"
                    )

    strategy = doc.get("strategy")
    if not isinstance(strategy, dict):
        errors.append("strategy: must be object")
    elif i13_active:
        cap = strategy.get("position_cap")
        if not is_zero_position_cap(cap):
            errors.append("strategy.position_cap: I13 requires explicit zero position")
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
    errors = validate(read_json(input_path), args.date, allowed, base=base)
    if errors:
        print(f"[ERROR] {input_path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
