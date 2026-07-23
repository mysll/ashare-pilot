#!/usr/bin/env python3
"""Normalize v2 main-strategy selection before strict schema validation.

This script only moves non-selected rows from stocks[] to observation_pool. It
does not repair or invent strategy fields for rows that remain selected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .validate_strategy import PREOPEN_DECISIONS, ENTRY_SETUPS, REGIME_STOCK_LIMITS


RATING_RANK = {"5★": 5, "4★": 4, "3★": 3, "2★": 2, "1★": 1, "—": 0}


def exclusion_reason(stock: dict[str, Any]) -> str | None:
    if stock.get("direction") not in {"看多", "偏多"}:
        return f"non_buyable_direction:{stock.get('direction')}"
    if stock.get("entry_profile") == "暂不参与":
        return "entry_profile:暂不参与"
    plan = stock.get("preopen_plan")
    if not isinstance(plan, dict):
        return "preopen_plan_missing"
    decision = plan.get("decision")
    setup = plan.get("entry_setup")
    if decision not in PREOPEN_DECISIONS:
        return f"unsupported_decision:{decision}"
    if setup not in ENTRY_SETUPS:
        return f"unsupported_entry_setup:{setup}"
    return None


def priority(item: tuple[int, dict[str, Any]]) -> tuple[Any, ...]:
    index, stock = item
    plan = stock.get("preopen_plan", {})
    actionable = plan.get("decision") == "CONDITIONAL" and float(stock.get("position_budget") or 0) > 0
    return (
        -(1 if actionable else 0),
        -RATING_RANK.get(stock.get("rating"), 0),
        -float(stock.get("position_budget") or 0),
        index,
    )


def compact_observation(stock: dict[str, Any], reason: str) -> dict[str, str]:
    return {
        "code": str(stock.get("code") or ""),
        "name": str(stock.get("name") or stock.get("code") or "未知"),
        "reason": reason,
    }


def normalize(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if doc.get("schema_version") != "daily_strategy.v2":
        raise ValueError("normalize_strategy_selection only supports daily_strategy.v2")
    stocks = doc.get("stocks")
    if not isinstance(stocks, list):
        raise ValueError("stocks must be list")
    regime = doc.get("market", {}).get("regime_prior")
    limit = REGIME_STOCK_LIMITS.get(regime)
    if limit is None:
        raise ValueError(f"unsupported regime_prior: {regime!r}")

    eligible: list[tuple[int, dict[str, Any]]] = []
    moved: list[dict[str, str]] = []
    for index, stock in enumerate(stocks):
        if not isinstance(stock, dict):
            raise ValueError(f"stocks[{index}] must be object")
        reason = exclusion_reason(stock)
        if reason:
            moved.append(compact_observation(stock, reason))
        else:
            eligible.append((index, stock))

    ranked = sorted(eligible, key=priority)
    selected_pairs = ranked[:limit]
    overflow = ranked[limit:]
    selected = [stock for _, stock in selected_pairs]
    for _, stock in overflow:
        moved.append(compact_observation(stock, f"selection_overflow:{regime}_limit_{limit}"))

    observation = doc.get("observation_pool")
    existing = observation if isinstance(observation, list) else []
    selected_codes = {stock.get("code") for stock in selected}
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*existing, *moved]:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not isinstance(code, str) or code in selected_codes or code in seen:
            continue
        seen.add(code)
        merged.append({
            "code": code,
            "name": str(item.get("name") or code),
            "reason": str(item.get("reason") or "未进入主策略"),
        })

    normalized = dict(doc)
    normalized["stocks"] = selected
    normalized["observation_pool"] = merged
    summary = {
        "regime_prior": regime,
        "limit": limit,
        "input_stocks": len(stocks),
        "selected_stocks": len(selected),
        "moved_to_observation": len(moved),
        "selected_codes": [stock.get("code") for stock in selected],
    }
    return normalized, summary


def atomic_write(path: Path, doc: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize daily strategy main-list selection")
    parser.add_argument("path")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--in-place", action="store_true")
    group.add_argument("--output")
    args = parser.parse_args(argv)
    source = Path(args.path)
    try:
        doc = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(doc, dict):
            raise ValueError("root must be object")
        normalized, summary = normalize(doc)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    target = source if args.in_place else Path(args.output)
    atomic_write(target, normalized)
    print(json.dumps(summary, ensure_ascii=False))
    print(f"Saved to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
