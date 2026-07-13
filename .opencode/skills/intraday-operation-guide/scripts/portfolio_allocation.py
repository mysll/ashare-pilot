"""Deterministic aggregate allocation for actionable morning candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


RATING_RANK = {"5★": 5, "4★": 4, "3★": 3, "2★": 2, "1★": 1, "—": 0}


def normalize_limits(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "max_new_exposure": float(source.get("max_new_exposure", 1.0)),
        "max_theme_exposure": float(source.get("max_theme_exposure", 1.0)),
        "max_single_stock": float(source.get("max_single_stock", 1.0)),
        "max_correlated_names": int(source.get("max_correlated_names", 999999)),
        "source": "daily_strategy.v2" if isinstance(raw, dict) else "legacy_unbounded_fallback",
    }


def allocation_priority(stock: dict[str, Any]) -> tuple[Any, ...]:
    strategy = stock.get("strategy", {})
    theme = stock.get("theme_confirmation", {})
    transition = stock.get("transition", {})
    sustained = transition.get("transition") in {"A_TO_A", "B_TO_A"}
    guard = stock.get("decision_guardrails", {})
    requested = guard.get("position", {}).get("signal_adjusted_max", 0.0)
    return (
        -RATING_RANK.get(strategy.get("rating"), 0),
        -(1 if theme.get("theme_state") == "CONFIRMED" else 0),
        -(1 if sustained else 0),
        -float(requested or 0.0),
        str(stock.get("code") or ""),
    )


def apply_portfolio_limits(
    stocks: list[dict[str, Any]], raw_limits: Any
) -> dict[str, Any]:
    limits = normalize_limits(raw_limits)
    used_total = 0.0
    used_by_theme: dict[str, float] = defaultdict(float)
    names_by_theme: dict[str, int] = defaultdict(int)
    requested_total = 0.0
    excluded: list[dict[str, str]] = []

    for stock in stocks:
        position = stock.get("decision_guardrails", {}).get("position", {})
        requested_total += float(position.get("signal_adjusted_max") or 0.0)
        position["portfolio_adjusted_max"] = 0.0
        position["final_max"] = 0.0

    candidates = [
        stock for stock in stocks
        if stock.get("decision_guardrails", {}).get("mechanical_class") == "A"
        and float(stock.get("decision_guardrails", {}).get("position", {}).get("signal_adjusted_max") or 0.0) > 0
    ]
    candidates.sort(key=allocation_priority)

    for stock in candidates:
        guard = stock["decision_guardrails"]
        position = guard["position"]
        code = str(stock.get("code"))
        theme = str(stock.get("strategy", {}).get("sector") or "未分类")
        proposed = min(float(position["signal_adjusted_max"]), limits["max_single_stock"])
        reason = None
        if names_by_theme[theme] >= limits["max_correlated_names"]:
            allocated = 0.0
            reason = "max_correlated_names"
        else:
            theme_remaining = max(0.0, limits["max_theme_exposure"] - used_by_theme[theme])
            total_remaining = max(0.0, limits["max_new_exposure"] - used_total)
            allocated = min(proposed, theme_remaining, total_remaining)
            if allocated <= 0:
                reason = "theme_or_total_exposure_exhausted"
        allocated = round(max(0.0, allocated), 6)
        position["portfolio_adjusted_max"] = allocated
        position["final_max"] = allocated
        if allocated > 0:
            used_total = round(used_total + allocated, 6)
            used_by_theme[theme] = round(used_by_theme[theme] + allocated, 6)
            names_by_theme[theme] += 1
            if allocated < float(position["signal_adjusted_max"]):
                guard.setdefault("class_reasons", []).append("portfolio_position_reduced")
        else:
            guard["mechanical_class"] = "B"
            guard.setdefault("class_reasons", []).append(f"portfolio_cap:{reason}")
            transition = stock.get("transition")
            if isinstance(transition, dict):
                transition["current_class"] = "B"
                transition["transition"] = f"{transition.get('previous_class') or 'INIT'}_TO_B"
                transition["adjusted"] = True
                transition["adjustment_reason"] = f"portfolio_cap:{reason}"
            excluded.append({"code": code, "reason": reason or "portfolio_cap"})

    return {
        "limits": limits,
        "requested_exposure": round(requested_total, 6),
        "allocated_exposure": round(used_total, 6),
        "allocated_by_theme": dict(sorted(used_by_theme.items())),
        "allocated_names_by_theme": dict(sorted(names_by_theme.items())),
        "priority_order": [stock.get("code") for stock in candidates],
        "excluded": excluded,
    }
