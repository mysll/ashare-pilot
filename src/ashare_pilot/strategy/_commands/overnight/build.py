#!/usr/bin/env python3
"""Project intraday_mapper.v3 into overnight_strategy.v3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    MAPPER_SCHEMA_VERSION,
    OVERNIGHT_STRATEGY_SCHEMA_VERSION,
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
    resolved_stop_loss,
    utc_now_iso,
    write_json,
)


def executable_projection(stock: dict[str, Any]) -> dict[str, Any]:
    reasoning = (
        stock.get("reasoning")
        if isinstance(stock.get("reasoning"), dict)
        else {}
    )
    source_plan = reasoning.get("t_plus_1_plan")
    plan = dict(source_plan) if isinstance(source_plan, dict) else {}
    plan.update(resolved_stop_loss(stock, plan.get("stop_loss_basis")))
    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "market_board": stock.get("market_board"),
        "primary_theme": stock.get("primary_theme"),
        "themes": stock.get("themes") or [],
        "theme_support_shadow": stock.get("theme_support_shadow"),
        "overnight_score": stock.get("overnight_score"),
        "rank": stock.get("rank"),
        "rank_tier": stock.get("rank_tier"),
        "tradeability": reasoning.get("tradeability"),
        "execution_role": reasoning.get("execution_role"),
        "i14_exemption": stock.get("i14_exemption"),
        "direction": reasoning.get("direction"),
        "trading_strategy": reasoning.get("trading_strategy"),
        "risk_severity": reasoning.get("risk_severity"),
        "expected_premium": reasoning.get("expected_premium"),
        "key_reason": reasoning.get("key_reason"),
        "execution_condition": reasoning.get("execution_condition"),
        "t_plus_1_plan": plan,
        "rules_applied": reasoning.get("rules_applied") or [],
        "reasoning_trace": reasoning.get("reasoning_trace"),
        "execution_state": stock.get("execution_state"),
        "execution_eligibility": stock.get("execution_eligibility"),
    }


def observation_projection(stock: dict[str, Any]) -> dict[str, Any]:
    note = (
        stock.get("observation_reasoning")
        if isinstance(stock.get("observation_reasoning"), dict)
        else {}
    )
    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "market_board": stock.get("market_board"),
        "primary_theme": stock.get("primary_theme"),
        "themes": stock.get("themes") or [],
        "theme_support_shadow": stock.get("theme_support_shadow"),
        "score_status": stock.get("score_status"),
        "overnight_score": stock.get("overnight_score"),
        "rank": stock.get("rank"),
        "rank_tier": stock.get("rank_tier"),
        "observation_reasons": stock.get("observation_reasons") or [],
        "primary_observation_reason": stock.get(
            "primary_observation_reason"
        ),
        "observation_summary": note.get("observation_summary"),
        "watch_condition": note.get("watch_condition"),
        "risk_note": note.get("risk_note"),
    }


def build(mapper: dict[str, Any]) -> dict[str, Any]:
    if mapper.get("schema_version") != MAPPER_SCHEMA_VERSION:
        raise ValueError(f"input must be {MAPPER_SCHEMA_VERSION}")
    recommendations = []
    eligible_watchlist = []
    for stock in mapper.get("executable_stocks", []):
        if not isinstance(stock, dict) or not isinstance(
            stock.get("reasoning"), dict
        ):
            raise ValueError(f"{stock.get('code')}: executable reasoning missing")
        projected = executable_projection(stock)
        errors = reasoning_invariant_errors(stock, stock["reasoning"])
        if errors:
            raise ValueError(f"{stock.get('code')}: {'; '.join(errors)}")
        role = projected.get("execution_role")
        if role == "primary":
            recommendations.append(projected)
        elif role in {"alternative", "watch"}:
            eligible_watchlist.append(projected)
        else:
            raise ValueError(f"{stock.get('code')}: invalid execution_role")
    observations = [
        observation_projection(stock)
        for stock in mapper.get("observation_stocks", [])
        if isinstance(stock, dict)
    ]
    strategy = (
        dict(mapper.get("strategy"))
        if isinstance(mapper.get("strategy"), dict)
        else {}
    )
    pool_summary = (
        mapper.get("pool_summary")
        if isinstance(mapper.get("pool_summary"), dict)
        else {}
    )
    return {
        "schema_version": OVERNIGHT_STRATEGY_SCHEMA_VERSION,
        "date": mapper.get("date"),
        "generated_at": utc_now_iso(),
        "source": {
            "schema_version": mapper.get("schema_version"),
            "file": f"intraday/{mapper.get('date')}/intraday_mapper.json",
        },
        "market_assessment": mapper.get("market_assessment") or {},
        "strategy": strategy,
        "data_quality": pool_summary.get("data_quality") or {},
        "recall_quality": pool_summary.get("recall_quality") or {},
        "recommendations": recommendations,
        "eligible_watchlist": eligible_watchlist,
        "observations": observations,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = intraday_dir(args.date)
    input_path = (
        Path(args.input) if args.input else root / "intraday_mapper.json"
    )
    output_path = (
        Path(args.output) if args.output else root / "overnight_strategy.json"
    )
    try:
        mapper = read_json(input_path)
        if mapper.get("date") != args.date:
            raise ValueError(f"input date must be {args.date}")
        document = build(mapper)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] strategy build failed: {exc}", file=sys.stderr)
        return 1
    write_json(output_path, document)
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
