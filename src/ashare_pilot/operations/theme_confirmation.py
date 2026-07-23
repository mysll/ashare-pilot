"""Theme confirmation from the bounded daily strategy pool."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ashare_pilot.operations.mechanical_classification import CLASS_RANK, cap_class


THEME_STATES = {"CONFIRMED", "NARROW", "FADING", "FAILED", "UNKNOWN"}


def build_theme_confirmations(stocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in stocks:
        strategy = stock.get("strategy") if isinstance(stock.get("strategy"), dict) else {}
        theme = strategy.get("sector") or "未分类"
        grouped[str(theme)].append(stock)

    output: dict[str, dict[str, Any]] = {}
    for theme, members in grouped.items():
        valid = [item for item in members if isinstance(item.get("quote", {}).get("percent"), (int, float))]
        count = len(valid)
        advances = sum(item["quote"]["percent"] > 0 for item in valid)
        above_vwap = sum(not item.get("signals", {}).get("below_vwap", True) for item in valid)
        fades = sum(bool(item.get("signals", {}).get("high_open_fade")) for item in valid)
        advance_ratio = advances / count if count else None
        above_ratio = above_vwap / count if count else None
        fade_ratio = fades / count if count else None
        if count < 2:
            state = "UNKNOWN"
        elif fade_ratio is not None and fade_ratio >= 0.5:
            state = "FADING"
        elif advance_ratio is not None and advance_ratio >= 0.6 and above_ratio is not None and above_ratio >= 0.5:
            state = "CONFIRMED"
        elif advance_ratio is not None and advance_ratio <= 0.3:
            state = "FAILED"
        else:
            state = "NARROW"
        output[theme] = {
            "theme": theme,
            "source": "daily_strategy_pool",
            "expected_member_n": len(members),
            "valid_member_n": count,
            "member_codes": [item.get("code") for item in members],
            "member_advance_ratio": round(advance_ratio, 4) if advance_ratio is not None else None,
            "member_above_vwap_ratio": round(above_ratio, 4) if above_ratio is not None else None,
            "high_open_fade_ratio": round(fade_ratio, 4) if fade_ratio is not None else None,
            "theme_state": state,
            "theme_confirmed": state == "CONFIRMED",
        }
    return output


def apply_theme_caps(stocks: list[dict[str, Any]], themes: dict[str, dict[str, Any]]) -> None:
    for stock in stocks:
        strategy = stock.get("strategy") if isinstance(stock.get("strategy"), dict) else {}
        theme = str(strategy.get("sector") or "未分类")
        confirmation = themes.get(theme, {"theme_state": "UNKNOWN"})
        state = confirmation.get("theme_state")
        guard = stock.get("decision_guardrails", {})
        maximum = guard.get("max_allowed_class", "D")
        requires = bool(strategy.get("preopen_plan", {}).get("requires_theme_confirmation"))
        if state in {"FAILED", "FADING"}:
            maximum = cap_class(maximum, "C")
            guard.setdefault("class_reasons", []).append(f"theme_{str(state).lower()}")
        elif state == "NARROW":
            maximum = cap_class(maximum, "B")
            guard.setdefault("class_reasons", []).append("theme_narrow")
        elif state == "UNKNOWN" and requires:
            maximum = cap_class(maximum, "B")
            guard.setdefault("class_reasons", []).append("theme_confirmation_unknown")
        guard["max_allowed_class"] = maximum
        mechanical = guard.get("mechanical_class", "D")
        if CLASS_RANK.get(mechanical, 0) > CLASS_RANK.get(maximum, 0):
            guard["mechanical_class"] = maximum
            guard["position"]["signal_adjusted_max"] = 0.0
            guard["position"]["final_max"] = 0.0
        stock["theme_confirmation"] = confirmation
