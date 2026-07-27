"""Deterministic count-based allocation for qualitative morning candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ashare_pilot.position_tier import POSITION_TIER_RANK


RATING_RANK = {"5★": 5, "4★": 4, "3★": 3, "2★": 2, "1★": 1, "—": 0}


def normalize_limits(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("daily_strategy.v3 requires qualitative portfolio_limits")
    return {
        "max_new_positions": int(raw["max_new_positions"]),
        "max_theme_positions": int(raw["max_theme_positions"]),
        "max_correlated_names": int(raw["max_correlated_names"]),
        "source": "daily_strategy.v3",
    }


def allocation_priority(stock: dict[str, Any]) -> tuple[Any, ...]:
    strategy = stock.get("strategy", {})
    theme = stock.get("theme_confirmation", {})
    transition = stock.get("transition", {})
    sustained = transition.get("transition") in {"A_TO_A", "B_TO_A"}
    tier = stock.get("decision_guardrails", {}).get("position_tier", {}).get("signal_adjusted")
    return (
        -RATING_RANK.get(strategy.get("rating"), 0),
        -(1 if theme.get("theme_state") == "CONFIRMED" else 0),
        -(1 if sustained else 0),
        -POSITION_TIER_RANK.get(tier, 0),
        str(stock.get("code") or ""),
    )


def apply_portfolio_limits(
    stocks: list[dict[str, Any]], raw_limits: Any
) -> dict[str, Any]:
    limits = normalize_limits(raw_limits)
    used_total = 0
    used_by_theme: dict[str, int] = defaultdict(int)
    names_by_theme: dict[str, int] = defaultdict(int)
    requested_total = 0
    excluded: list[dict[str, str]] = []

    for stock in stocks:
        tiers = stock.get("decision_guardrails", {}).get("position_tier", {})
        if tiers.get("signal_adjusted") != "WATCH_ONLY":
            requested_total += 1
        tiers["portfolio_adjusted"] = "WATCH_ONLY"
        tiers["final"] = "WATCH_ONLY"

    candidates = [
        stock for stock in stocks
        if stock.get("decision_guardrails", {}).get("mechanical_class") == "A"
        and stock.get("decision_guardrails", {}).get("position_tier", {}).get("signal_adjusted") != "WATCH_ONLY"
    ]
    candidates.sort(key=allocation_priority)

    for stock in candidates:
        guard = stock["decision_guardrails"]
        tiers = guard["position_tier"]
        code = str(stock.get("code"))
        theme = str(stock.get("strategy", {}).get("sector") or "未分类")
        reason = None
        if used_total >= limits["max_new_positions"]:
            reason = "max_new_positions"
        elif used_by_theme[theme] >= limits["max_theme_positions"]:
            reason = "max_theme_positions"
        elif names_by_theme[theme] >= limits["max_correlated_names"]:
            reason = "max_correlated_names"

        if reason is None:
            tiers["portfolio_adjusted"] = tiers["signal_adjusted"]
            tiers["final"] = tiers["signal_adjusted"]
            used_total += 1
            used_by_theme[theme] += 1
            names_by_theme[theme] += 1
        else:
            guard["mechanical_class"] = "B"
            guard.setdefault("class_reasons", []).append(f"portfolio_cap:{reason}")
            transition = stock.get("transition")
            if isinstance(transition, dict):
                transition["current_class"] = "B"
                transition["transition"] = f"{transition.get('previous_class') or 'INIT'}_TO_B"
                transition["adjusted"] = True
                transition["adjustment_reason"] = f"portfolio_cap:{reason}"
            excluded.append({"code": code, "reason": reason})

    return {
        "limits": limits,
        "requested_positions": requested_total,
        "allocated_positions": used_total,
        "allocated_by_theme": dict(sorted(used_by_theme.items())),
        "allocated_names_by_theme": dict(sorted(names_by_theme.items())),
        "priority_order": [stock.get("code") for stock in candidates],
        "excluded": excluded,
    }
