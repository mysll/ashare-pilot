from __future__ import annotations

import pytest

from ashare_pilot.operations.operation_transition import (
    apply_delivery_gate,
    apply_previous_snapshot,
)


def stock_without_position_tier() -> dict:
    return {
        "code": "sz000001",
        "decision_guardrails": {
            "mechanical_class": "B",
            "max_allowed_class": "B",
            "class_reasons": [],
        },
    }


def test_delivery_gate_fails_loud_when_position_tier_is_missing() -> None:
    with pytest.raises(KeyError, match="position_tier"):
        apply_delivery_gate([stock_without_position_tier()], "09:40", False)


def test_previous_snapshot_fails_loud_when_position_tier_is_missing() -> None:
    with pytest.raises(KeyError, match="position_tier"):
        apply_previous_snapshot([stock_without_position_tier()], {"stocks": []})
