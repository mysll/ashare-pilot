#!/usr/bin/env python3
"""Build overnight_strategy.json from the validated intraday mapper contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
    resolved_stop_loss,
    utc_now_iso,
    write_json,
)


def strategy_stock(stock: dict[str, Any]) -> dict[str, Any]:
    reasoning = stock.get("reasoning") if isinstance(stock.get("reasoning"), dict) else {}
    source_plan = reasoning.get("t_plus_1_plan")
    plan = dict(source_plan) if isinstance(source_plan, dict) else {}
    plan.update(resolved_stop_loss(stock, plan.get("stop_loss_basis")))
    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "market_board": stock.get("market_board"),
        "primary_theme": stock.get("primary_theme"),
        "themes": stock.get("themes") or [],
        "sector": stock.get("primary_theme"),
        "source_tier": stock.get("tier"),
        "source_rank": stock.get("rank"),
        "overnight_score": stock.get("overnight_score"),
        "absolute_score": stock.get("absolute_score"),
        "rank_tier": stock.get("rank_tier"),
        "tradeability": reasoning.get("tradeability"),
        "i14_exemption": stock.get("i14_exemption"),
        "anomaly_flags": stock.get("anomaly_flags") or [],
        "execution_state": stock.get("execution_state"),
        "direction": reasoning.get("direction"),
        "trading_strategy": reasoning.get("trading_strategy"),
        "risk_severity": reasoning.get("risk_severity"),
        "expected_premium": reasoning.get("expected_premium"),
        "key_reason": reasoning.get("key_reason"),
        "position_plan": reasoning.get("position_plan"),
        "t_plus_1_exit_plan": reasoning.get("t_plus_1_exit_plan"),
        "t_plus_1_plan": plan,
        "rules_applied": reasoning.get("rules_applied") or [],
        "reasoning_trace": reasoning.get("reasoning_trace"),
        "execution_references": {
            "price": stock.get("price"),
            "high": (
                stock.get("enriched", {}).get("real_time", {}).get("high")
                if isinstance(stock.get("enriched"), dict)
                else None
            ),
            "low": (
                stock.get("enriched", {}).get("real_time", {}).get("low")
                if isinstance(stock.get("enriched"), dict)
                else None
            ),
            "vwap": (
                stock.get("enriched", {}).get("real_time", {}).get("vwap")
                if isinstance(stock.get("enriched"), dict)
                else None
            ),
            "ma5": stock.get("technicals", {}).get("ma5") if isinstance(stock.get("technicals"), dict) else None,
            "ma10": stock.get("technicals", {}).get("ma10") if isinstance(stock.get("technicals"), dict) else None,
            "ma20": stock.get("technicals", {}).get("ma20") if isinstance(stock.get("technicals"), dict) else None,
        },
    }


def build(mapper: dict[str, Any]) -> dict[str, Any]:
    invariant_errors = []
    for stock in mapper.get("stocks", []):
        if not isinstance(stock, dict) or not isinstance(stock.get("reasoning"), dict):
            continue
        normalized_reasoning = dict(stock["reasoning"])
        source_plan = normalized_reasoning.get("t_plus_1_plan")
        normalized_plan = dict(source_plan) if isinstance(source_plan, dict) else {}
        normalized_plan.update(resolved_stop_loss(stock, normalized_plan.get("stop_loss_basis")))
        normalized_reasoning["t_plus_1_plan"] = normalized_plan
        for error in reasoning_invariant_errors(stock, normalized_reasoning):
            invariant_errors.append(f"{stock.get('code')}: {error}")
    if invariant_errors:
        raise ValueError("; ".join(invariant_errors))
    stocks = [
        strategy_stock(stock)
        for stock in mapper.get("stocks", [])
        if isinstance(stock, dict) and isinstance(stock.get("reasoning"), dict)
    ]
    pool_summary = (
        mapper.get("pool_summary")
        if isinstance(mapper.get("pool_summary"), dict)
        else {}
    )
    return {
        "schema_version": "intraday_overnight_strategy.v1",
        "date": mapper.get("date"),
        "generated_at": utc_now_iso(),
        "scoring_policy_version": (
            mapper.get("pool_summary", {}).get("scoring_policy_version")
            if isinstance(mapper.get("pool_summary"), dict)
            else None
        ),
        "source": {
            "schema_version": mapper.get("schema_version"),
            "generated_at": mapper.get("generated_at"),
            "file": f"intraday/{mapper.get('date')}/intraday_mapper.json",
        },
        "market": mapper.get("market_assessment"),
        "portfolio": mapper.get("strategy"),
        "data_quality": pool_summary.get("data_quality_summary"),
        "data_warning": pool_summary.get("pool_warning"),
        "positions": [stock for stock in stocks if stock.get("direction") != "观望"],
        "watchlist": [stock for stock in stocks if stock.get("direction") == "观望"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = intraday_dir(args.date)
    input_path = Path(args.input) if args.input else root / "intraday_mapper.json"
    output_path = Path(args.output) if args.output else root / "overnight_strategy.json"
    mapper = read_json(input_path)
    if not isinstance(mapper, dict) or mapper.get("schema_version") != "intraday_mapper.v1":
        print("[ERROR] input must be intraday_mapper.v1", file=sys.stderr)
        return 1
    if mapper.get("date") != args.date:
        print(f"[ERROR] input date must be {args.date}", file=sys.stderr)
        return 1
    try:
        doc = build(mapper)
    except ValueError as exc:
        print(f"[ERROR] execution invariants failed: {exc}", file=sys.stderr)
        return 1
    write_json(output_path, doc)
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
