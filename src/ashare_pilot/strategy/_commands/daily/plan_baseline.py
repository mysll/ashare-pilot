"""Deterministically materialize fixed Step 3 execution-plan fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any


PORTFOLIO_LIMITS = {
    "max_new_positions": 7,
    "max_theme_positions": 3,
    "max_correlated_names": 2,
}
PLAN_OVERRIDE_FIELDS = {
    "entry_trigger",
    "no_buy_condition",
    "pre_entry_invalidations",
    "t1_risk_plan",
}


def generated_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def entry_trigger(anchor: str, setup: str) -> str:
    setup_labels = {
        "LIMIT_UP_CONT": "开盘延续确认",
        "MOMENTUM": "强势延续确认",
        "FIRST_BAR_OR_PULLBACK": "首根5分钟企稳或回踩确认",
        "PULLBACK": "回踩企稳确认",
        "DEFENSIVE": "防御企稳确认",
        "WATCH_ONLY": "仅观察，不形成买入条件",
    }
    anchor_text = "" if anchor in {"无", "—", "FLEX"} else f"{anchor}附近"
    return f"{anchor_text}{setup_labels[setup]}"


def no_buy_condition(profile: dict[str, Any]) -> str:
    invalidation = profile.get("invalidation")
    if isinstance(invalidation, str) and invalidation.strip():
        return invalidation.strip()
    return "市场、主题或个股确认条件任一失效"


def t1_risk_plan(regime: str, position_tier: str) -> dict[str, str]:
    risk = "高" if regime in {"panic", "weak"} or position_tier == "WATCH_ONLY" else "中"
    return {
        "overnight_risk": risk,
        "gap_up_action": "冲高不追，按开盘承接强弱分批处理",
        "flat_open_action": "观察首根5分钟，确认延续才持有",
        "gap_down_action": "禁止补仓，弱于失效条件则退出",
    }


def profile_trace(profile: dict[str, Any]) -> str:
    return " / ".join(
        str(value)
        for value in (
            profile.get("playbook"),
            profile.get("preferred_anchor"),
            profile.get("chase_policy"),
            profile.get("entry_window"),
            profile.get("stop_policy"),
        )
        if value not in (None, "")
    )


def apply_plan_overrides(plan: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    for field, item in overrides.items():
        result[field] = item["value"]
    return result


def materialize_stock_plan(
    decision: dict[str, Any],
    profile: dict[str, Any],
    regime: str,
) -> dict[str, Any]:
    tier = decision["position_tier"]
    setup = decision["entry_setup"]
    invalidations = [
        no_buy_condition(profile),
        "大盘或所属主题未通过开盘确认",
    ]
    baseline = {
        "entry_trigger": entry_trigger(decision["anchor"], setup),
        "no_buy_condition": no_buy_condition(profile),
        "pre_entry_invalidations": invalidations,
        "t1_risk_plan": t1_risk_plan(regime, tier),
    }
    plan = apply_plan_overrides(baseline, decision.get("plan_overrides", {}))
    return {
        "entry_trigger": plan["entry_trigger"],
        "no_buy_condition": plan["no_buy_condition"],
        "horizon": "T+1",
        "preopen_plan": {
            "decision": "WATCH_ONLY" if tier == "WATCH_ONLY" else "CONDITIONAL",
            "earliest_entry_time": "09:35:05",
            "latest_entry_time": "10:00:00",
            "requires_first_bar": True,
            "requires_market_confirmation": True,
            "requires_theme_confirmation": True,
            "entry_setup": setup,
            "pre_entry_invalidations": plan["pre_entry_invalidations"],
        },
        "t1_risk_plan": plan["t1_risk_plan"],
        "profile_trace": profile_trace(profile),
    }
