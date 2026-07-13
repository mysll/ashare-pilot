#!/usr/bin/env python3
"""Validate intraday/{date}/overnight_strategy.json."""

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


def validate_stock(
    item: Any,
    path: str,
    expected_direction: str | None,
    errors: list[str],
    require_tradeability: bool = False,
) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path}: must be object")
        return
    if not isinstance(item.get("code"), str) or not CODE_RE.fullmatch(item["code"]):
        errors.append(f"{path}.code: invalid")
    if not isinstance(item.get("name"), str) or not item["name"]:
        errors.append(f"{path}.name: required")
    if expected_direction == "position" and (
        not isinstance(item.get("sector"), str) or not item["sector"].strip()
    ):
        errors.append(f"{path}.sector: actionable position requires non-empty string")
    if item.get("direction") not in DIRECTIONS:
        errors.append(f"{path}.direction: invalid enum")
    tradeability = item.get("tradeability")
    if require_tradeability and tradeability not in TRADEABILITIES:
        errors.append(f"{path}.tradeability: invalid enum")
    elif tradeability is not None and tradeability not in TRADEABILITIES:
        errors.append(f"{path}.tradeability: invalid enum")
    if expected_direction == "观望" and item.get("direction") != "观望":
        errors.append(f"{path}.direction: watchlist item must be 观望")
    if expected_direction == "position" and item.get("direction") == "观望":
        errors.append(f"{path}.direction: position must be actionable")
    if item.get("trading_strategy") not in STRATEGIES:
        errors.append(f"{path}.trading_strategy: invalid enum")
    if item.get("risk_severity") not in RISKS:
        errors.append(f"{path}.risk_severity: invalid enum")
    for field in ("expected_premium", "key_reason", "position_plan", "t_plus_1_exit_plan", "reasoning_trace"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"{path}.{field}: required")
    plan = item.get("t_plus_1_plan")
    if expected_direction == "position":
        if not isinstance(plan, dict):
            errors.append(f"{path}.t_plus_1_plan: actionable position requires object")
        else:
            for field in ("auction_condition", "open_strategy", "stop_loss", "take_profit"):
                if not isinstance(plan.get(field), str) or not plan[field].strip():
                    errors.append(f"{path}.t_plus_1_plan.{field}: required")
    if not isinstance(item.get("rules_applied"), list) or not all(
        isinstance(value, str) for value in item.get("rules_applied", [])
    ):
        errors.append(f"{path}.rules_applied: must be list[str]")


def validate(doc: Any, date: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["root: must be object"]
    if doc.get("schema_version") != "intraday_overnight_strategy.v1":
        errors.append("schema_version: invalid")
    if doc.get("date") != date:
        errors.append(f"date: must be {date}")
    if not isinstance(doc.get("market"), dict):
        errors.append("market: must be object")
    if not isinstance(doc.get("portfolio"), dict):
        errors.append("portfolio: must be object")
    require_tradeability = doc.get("scoring_policy_version") == "convergence_v1"
    codes: list[str] = []
    for group, expected in (("positions", "position"), ("watchlist", "观望")):
        values = doc.get(group)
        if not isinstance(values, list):
            errors.append(f"{group}: must be list")
            continue
        for i, item in enumerate(values):
            validate_stock(
                item,
                f"{group}[{i}]",
                expected,
                errors,
                require_tradeability=require_tradeability,
            )
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                codes.append(item["code"])
    if len(codes) != len(set(codes)):
        errors.append("positions/watchlist: duplicate codes")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--mapper")
    args = parser.parse_args()
    path = Path(args.input) if args.input else intraday_dir(args.date) / "overnight_strategy.json"
    doc = read_json(path)
    errors = validate(doc, args.date)
    mapper_path = Path(args.mapper) if args.mapper else intraday_dir(args.date) / "intraday_mapper.json"
    if mapper_path.exists() and isinstance(doc, dict):
        mapper = read_json(mapper_path)
        mapper_stocks = {
            item.get("code"): item
            for item in mapper.get("stocks", [])
            if isinstance(item, dict) and isinstance(item.get("reasoning"), dict)
        }
        strategy_stocks = {
            item.get("code"): item
            for group in ("positions", "watchlist")
            for item in doc.get(group, [])
            if isinstance(item, dict)
        }
        if set(strategy_stocks) != set(mapper_stocks):
            errors.append("positions/watchlist codes must exactly cover annotated mapper stocks")
        for code in set(strategy_stocks) & set(mapper_stocks):
            source = mapper_stocks[code]
            target = strategy_stocks[code]
            if target.get("overnight_score") != source.get("overnight_score"):
                errors.append(f"{code}.overnight_score: differs from mapper")
            if target.get("absolute_score") != source.get("absolute_score"):
                errors.append(f"{code}.absolute_score: differs from mapper")
            if target.get("rank_tier") != source.get("rank_tier"):
                errors.append(f"{code}.rank_tier: differs from mapper")
            if target.get("tradeability") != source["reasoning"].get("tradeability"):
                errors.append(f"{code}.tradeability: differs from mapper reasoning")
            if target.get("direction") != source["reasoning"].get("direction"):
                errors.append(f"{code}.direction: differs from mapper reasoning")
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {path} ({len(doc['positions'])} positions, {len(doc['watchlist'])} watchlist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
