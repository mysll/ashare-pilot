"""State transition rules across intraday operation snapshots."""

from __future__ import annotations

from typing import Any

from mechanical_classification import CLASS_RANK, cap_class


ALLOWED_TRANSITIONS = {
    "A": {"A", "B", "C", "D"},
    "B": {"A", "B", "C", "D"},
    "C": {"C", "D"},
    "D": {"D"},
}


def apply_delivery_gate(
    stocks: list[dict[str, Any]], snapshot_slot: str, has_previous: bool
) -> dict[str, Any]:
    if has_previous:
        return {
            "delivery_status": "CONTINUATION",
            "execution_action": "EVALUATE",
            "late_initial_snapshot": False,
            "requires_second_confirmation": False,
        }
    if snapshot_slot == "09:35":
        return {
            "delivery_status": "ON_TIME_INITIAL",
            "execution_action": "EVALUATE",
            "late_initial_snapshot": False,
            "requires_second_confirmation": True,
        }
    if snapshot_slot == "09:40":
        maximum = "B"
        status = "LATE_0940_INITIAL"
        action = "WAIT_SECOND_CONFIRMATION"
    else:
        maximum = "C"
        status = "LATE_OBSERVE_ONLY"
        action = "OBSERVE_ONLY"
    for stock in stocks:
        guard = stock.get("decision_guardrails", {})
        guard["max_allowed_class"] = cap_class(guard.get("max_allowed_class", "D"), maximum)
        guard["mechanical_class"] = cap_class(guard.get("mechanical_class", "D"), maximum)
        guard.setdefault("class_reasons", []).append(f"delivery_gate:{status.lower()}")
        position = guard.get("position", {})
        position["signal_adjusted_max"] = 0.0
        position["final_max"] = 0.0
    return {
        "delivery_status": status,
        "execution_action": action,
        "late_initial_snapshot": True,
        "requires_second_confirmation": snapshot_slot == "09:40",
    }


def apply_previous_snapshot(
    stocks: list[dict[str, Any]], previous: dict[str, Any] | None
) -> list[str]:
    if not previous:
        for stock in stocks:
            current = stock.get("decision_guardrails", {}).get("mechanical_class")
            stock["transition"] = {
                "previous_class": None,
                "current_class": current,
                "transition": f"INIT_TO_{current}",
                "adjusted": False,
            }
        return []
    previous_by_code = {
        item.get("code"): item for item in previous.get("stocks", []) if isinstance(item, dict)
    }
    warnings: list[str] = []
    for stock in stocks:
        code = stock.get("code")
        guard = stock.get("decision_guardrails", {})
        current = guard.get("mechanical_class", "D")
        old_stock = previous_by_code.get(code)
        old = old_stock.get("decision_guardrails", {}).get("mechanical_class") if old_stock else None
        adjusted = False
        if old in ALLOWED_TRANSITIONS and current not in ALLOWED_TRANSITIONS[old]:
            allow_reassessment = bool(stock.get("strategy", {}).get("preopen_plan", {}).get("allow_reassessment"))
            if not (old == "C" and current == "A" and allow_reassessment):
                warnings.append(f"{code}:illegal_transition_{old}_to_{current}")
                current = old
                guard["mechanical_class"] = old
                guard["max_allowed_class"] = old
                if old != "A":
                    guard["position"]["signal_adjusted_max"] = 0.0
                    guard["position"]["final_max"] = 0.0
                adjusted = True
        stock["transition"] = {
            "previous_class": old,
            "current_class": current,
            "transition": f"{old or 'INIT'}_TO_{current}",
            "adjusted": adjusted,
        }
    return warnings
