#!/usr/bin/env python3
"""Offline six-day v1-cache replay for ADR-0004.

This is deliberately test-only migration logic.  Production code never accepts
the historical cache shape.  Historical money-flow rows are considered
available only when all five buckets are numeric and at least one is non-zero;
this avoids turning the old endpoint's all-zero outage placeholder into facts.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ashare_pilot.mapping._commands.intraday.validate_annotations import validate as validate_annotations
from ashare_pilot.mapping._commands.intraday.validate_mapper import validate as validate_mapper
from ashare_pilot.mapping.intraday_contract import (
    attach_theme_evidence,
    execution_state,
    merge_annotations,
)
from ashare_pilot.strategy._commands.overnight import score as scoring
from ashare_pilot.strategy._commands.overnight.build import build as build_strategy
from ashare_pilot.strategy._commands.overnight.render_report import render
from ashare_pilot.strategy._commands.overnight.validate import validate as validate_strategy
from ashare_pilot.strategy.intraday_selection import (
    build_selection_pools,
    finite_number,
    selection_invariant_errors,
)


DATES = (
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
    "2026-07-24",
    "2026-07-27",
)
MONEY_BUCKETS = (
    "main_net_inflow",
    "super_large_net",
    "large_net",
    "medium_net",
    "small_net",
)


def _number(value: Any) -> float:
    return float(str(value).replace("%", "").replace("+", "").replace(",", ""))


def normalize_historical_compute(document: dict[str, Any]) -> list[dict[str, Any]]:
    stocks = copy.deepcopy(document["compute_pool"])
    for stock in stocks:
        money = stock.setdefault("enriched", {}).setdefault("money_flow", {})
        complete = all(finite_number(money.get(field)) for field in MONEY_BUCKETS)
        nonzero = complete and any(_number(money[field]) != 0 for field in MONEY_BUCKETS)
        money["available"] = bool(nonzero)
        money["main_net_inflow_yuan"] = (
            round(_number(money["main_net_inflow"]) * 100_000_000)
            if nonzero
            else None
        )
        technicals = stock.get("technicals")
        if isinstance(technicals, dict) and technicals:
            technicals["status"] = "available"
        else:
            stock["technicals"] = {"status": "no_data"}
    return stocks


def _annotations(date: str, base: dict[str, Any]) -> dict[str, Any]:
    executable = []
    for stock in base["executable_stocks"]:
        executable.append(
            {
                "code": stock["code"],
                "tradeability": "Watch",
                "direction": "观望",
                "execution_role": "watch",
                "trading_strategy": "趋势跟随",
                "risk_severity": "medium",
                "expected_premium": "冻结回放不生成交易预测",
                "key_reason": "仅验证 v2 合同投影",
                "execution_condition": "冻结回放仅观察，不执行",
                "t_plus_1_plan": {
                    "auction_condition": "不适用",
                    "open_strategy": "仅观察",
                    "stop_loss_basis": "not_applicable",
                    "take_profit": "不适用",
                },
                "rules_applied": [],
                "reasoning_trace": "测试专用确定性注释",
            }
        )
    observations = [
        {
            "code": stock["code"],
            "observation_summary": "确定性观察池冻结回放",
            "watch_condition": "缺失数据恢复且全部执行门槛通过后重评",
            "risk_note": "禁止生成执行字段",
        }
        for stock in base["observation_stocks"]
    ]
    return {
        "schema_version": "intraday_mapper_annotations.v3",
        "date": date,
        "market_assessment": {
            "regime_hint": "offline_replay",
            "tomorrow_expectation": "冻结回放不生成预测",
            "risk_severity": "medium",
            "reasoning_trace": "离线合同回放",
        },
        "executable_annotations": executable,
        "observation_annotations": observations,
        "strategy": {
            "risk_posture": "zero",
            "execution_principle": "冻结回放不执行",
            "risk_control": ["仅验证合同投影"],
            "execution_window": "14:50-14:57",
        },
    }


def replay_date(date: str) -> tuple[dict[str, Any], str]:
    cache = ROOT / ".cache" / "intraday" / date
    compute = json.loads((cache / "compute_pool_enriched.json").read_text(encoding="utf-8"))
    legacy = json.loads((cache / "opportunity_pool.json").read_text(encoding="utf-8"))
    themes = json.loads((cache / "theme_ranking.json").read_text(encoding="utf-8"))
    stocks = normalize_historical_compute(compute)
    pools = build_selection_pools(
        stocks,
        executable_limit=30,
        observation_limit=30,
        configured_min_inflow_yuan=10_000_000,
        regime=legacy.get("regime_snapshot", {}),
    )
    invariant_errors = selection_invariant_errors(pools)
    if invariant_errors:
        raise AssertionError(invariant_errors)

    old = legacy.get("opportunity_pool", [])
    old_codes = {stock.get("code") for stock in old}
    old_ineligible = {
        stock.get("code")
        for stock in old
        if execution_state(stock).get("eligible") is not True
    }
    executable_codes = {stock["code"] for stock in pools["executable_pool"]}
    if old_ineligible & executable_codes:
        raise AssertionError("legacy ineligible stock entered executable pool")

    stock_themes = themes.get("stock_themes", {})
    score_snapshot = {
        stock["code"]: stock.get("overnight_score")
        for stock in pools["executable_pool"] + pools["observation_pool"]
    }
    base = {
        "schema_version": "intraday_mapper_base.v2",
        "date": date,
        "market": {},
        "themes": themes,
        "pool_summary": {
            **pools["pool_summary"],
            "scored_pool_summary": pools["scored_pool_summary"],
            "configured_limits": pools["configured_limits"],
        },
        "executable_stocks": attach_theme_evidence(
            pools["executable_pool"], stock_themes, themes
        ),
        "observation_stocks": attach_theme_evidence(
            pools["observation_pool"], stock_themes, themes
        ),
    }
    attached_scores = {
        stock["code"]: stock.get("overnight_score")
        for stock in base["executable_stocks"] + base["observation_stocks"]
    }
    if attached_scores != score_snapshot:
        raise AssertionError("theme shadow changed a deterministic score")
    annotations = _annotations(date, base)
    annotation_errors = validate_annotations(
        annotations,
        date,
        {stock["code"] for stock in base["executable_stocks"]},
        {stock["code"] for stock in base["observation_stocks"]},
        base,
    )
    if annotation_errors:
        raise AssertionError(annotation_errors)
    mapper = merge_annotations(base, annotations)
    mapper_errors = validate_mapper(mapper, date)
    if mapper_errors:
        raise AssertionError(mapper_errors)
    strategy = build_strategy(mapper)
    strategy_errors = validate_strategy(strategy, date, mapper)
    if strategy_errors:
        raise AssertionError(strategy_errors)
    html = render(strategy, mapper)
    if "Intraday 双池隔夜策略" not in html:
        raise AssertionError("HTML reconstruction failed")

    reasons = Counter(
        reason
        for stock in pools["observation_pool"]
        for reason in stock.get("observation_reasons", [])
    )
    current_rank = {
        stock["code"]: stock["rank"]
        for stock in pools["executable_pool"] + pools["observation_pool"]
        if stock.get("score_status") == "scored"
    }
    old_rank = {
        stock["code"]: stock.get("rank")
        for stock in old
        if isinstance(stock, dict)
    }
    rank_changed = sum(
        old_rank[code] != current_rank[code]
        for code in old_codes & current_rank.keys()
    )
    summary = {
        "date": date,
        "compute_count": len(stocks),
        "legacy_opportunity_count": len(old),
        "scoreable_count": pools["scored_pool_summary"]["scoreable_count"],
        "unscoreable_count": pools["scored_pool_summary"]["unscoreable_count"],
        "executable_count": len(pools["executable_pool"]),
        "observation_count": len(pools["observation_pool"]),
        "legacy_ineligible_count": len(old_ineligible),
        "legacy_ineligible_in_executable": 0,
        "sealed_moved_from_legacy": sum(
            execution_state(stock).get("is_sealed") is True
            for stock in old
        ),
        "money_reason_count": sum(
            value for key, value in reasons.items() if "money_flow" in key
        ),
        "technical_reason_count": sum(
            value for key, value in reasons.items() if "technical" in key or "trend" in key
        ),
        "vwap_reason_count": sum(value for key, value in reasons.items() if "vwap" in key),
        "shared_rank_count": len(old_codes & current_rank.keys()),
        "rank_changed_count": rank_changed,
        "mapper_valid": True,
        "strategy_valid": True,
        "html_rebuilt": True,
    }
    return summary, html


def legacy_theme_continuity_raw(stock: dict[str, Any]) -> float:
    mapping = {"limit_up": 1.0, "turnover": 0.7, "gain_range": 0.4}
    base = mapping.get(stock.get("source_pool", ""), 0.1)
    inflow = scoring.parse_float(
        stock.get("enriched", {}).get("money_flow", {}).get("main_net_inflow", "0")
    )
    return base * 0.7 + scoring.sigmoid(inflow, center=1.0, steepness=1.5) * 0.3


def main() -> int:
    summaries = []
    raw_checks = 0
    for date in DATES:
        summary, _ = replay_date(date)
        summaries.append(summary)
        compute = json.loads(
            (ROOT / ".cache" / "intraday" / date / "compute_pool_enriched.json").read_text(
                encoding="utf-8"
            )
        )
        for stock in compute["compute_pool"]:
            assert scoring.extract_source_capital_proxy_raw(stock) == legacy_theme_continuity_raw(stock)
            raw_checks += 1
    report = {
        "schema_version": "intraday_selection_frozen_replay.v1",
        "dates": list(DATES),
        "historical_normalization": {
            "production_compatibility": False,
            "money_flow": "all five buckets finite and at least one non-zero; main yuan derived from displayed 亿",
            "technicals": "non-empty legacy technical object marked available",
            "reason": "old all-zero endpoint placeholders are ambiguous and therefore fail closed",
        },
        "source_capital_proxy_raw_equal_to_legacy_theme_continuity": True,
        "source_capital_proxy_comparisons": raw_checks,
        "theme_shadow_score_change_count": 0,
        "rank_change_explanation": (
            "v2 ranks only the scoreable cohort and uses code-ascending tie breaks; "
            "v1 ranked the larger proxy-imputed cohort, so shared-stock ranks may move."
        ),
        "days": summaries,
        "totals": {
            key: sum(day[key] for day in summaries)
            for key in (
                "legacy_opportunity_count",
                "scoreable_count",
                "unscoreable_count",
                "executable_count",
                "observation_count",
                "legacy_ineligible_count",
                "legacy_ineligible_in_executable",
                "sealed_moved_from_legacy",
                "rank_changed_count",
            )
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
