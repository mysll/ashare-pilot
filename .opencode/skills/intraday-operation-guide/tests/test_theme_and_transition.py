from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from operation_transition import apply_delivery_gate, apply_previous_snapshot  # noqa: E402
from theme_confirmation import apply_theme_caps, build_theme_confirmations  # noqa: E402


def stock(code, sector, percent, below_vwap=False, fade=False, klass="A", requires=False):
    return {
        "code": code,
        "strategy": {"sector": sector, "preopen_plan": {"requires_theme_confirmation": requires}},
        "quote": {"percent": percent},
        "signals": {"below_vwap": below_vwap, "high_open_fade": fade},
        "decision_guardrails": {
            "mechanical_class": klass, "max_allowed_class": "A", "class_reasons": [],
            "position": {"morning_budget": 0.02, "market_adjusted_max": 0.01, "signal_adjusted_max": 0.01, "final_max": 0.01},
        },
    }


class ThemeTests(unittest.TestCase):
    def test_confirmed_theme(self):
        stocks = [stock("sz000001", "银行", 1.0), stock("sh600000", "银行", 0.5)]
        themes = build_theme_confirmations(stocks)
        self.assertEqual(themes["银行"]["theme_state"], "CONFIRMED")

    def test_failed_theme_caps_a_at_c(self):
        stocks = [stock("sz000001", "银行", -1.0), stock("sh600000", "银行", -0.5)]
        themes = build_theme_confirmations(stocks)
        apply_theme_caps(stocks, themes)
        self.assertEqual(stocks[0]["decision_guardrails"]["max_allowed_class"], "C")
        self.assertEqual(stocks[0]["decision_guardrails"]["position"]["final_max"], 0)

    def test_unknown_required_theme_caps_at_b(self):
        stocks = [stock("sz000001", "银行", 1.0, requires=True)]
        themes = build_theme_confirmations(stocks)
        apply_theme_caps(stocks, themes)
        self.assertEqual(stocks[0]["decision_guardrails"]["max_allowed_class"], "B")


class TransitionTests(unittest.TestCase):
    def test_late_0940_initial_caps_at_b(self):
        current = [stock("sz000001", "银行", 1.0, klass="A")]
        delivery = apply_delivery_gate(current, "09:40", has_previous=False)
        self.assertEqual(delivery["execution_action"], "WAIT_SECOND_CONFIRMATION")
        self.assertEqual(current[0]["decision_guardrails"]["mechanical_class"], "B")
        self.assertEqual(current[0]["decision_guardrails"]["position"]["final_max"], 0)

    def test_late_0945_without_previous_is_observe_only(self):
        current = [stock("sz000001", "银行", 1.0, klass="A")]
        delivery = apply_delivery_gate(current, "09:45", has_previous=False)
        self.assertEqual(delivery["execution_action"], "OBSERVE_ONLY")
        self.assertEqual(current[0]["decision_guardrails"]["mechanical_class"], "C")

    def test_0945_with_previous_allows_evaluation(self):
        current = [stock("sz000001", "银行", 1.0, klass="A")]
        delivery = apply_delivery_gate(current, "09:45", has_previous=True)
        self.assertEqual(delivery["execution_action"], "EVALUATE")
        self.assertEqual(current[0]["decision_guardrails"]["mechanical_class"], "A")

    def test_b_to_a_allowed(self):
        current = [stock("sz000001", "银行", 1.0, klass="A")]
        previous = {"stocks": [stock("sz000001", "银行", 0.2, klass="B")]}
        warnings = apply_previous_snapshot(current, previous)
        self.assertEqual(warnings, [])
        self.assertEqual(current[0]["transition"]["transition"], "B_TO_A")

    def test_c_can_recover_to_b_but_not_jump_to_a(self):
        current = [stock("sz000001", "银行", 1.0, klass="B")]
        previous = {"stocks": [stock("sz000001", "银行", -0.2, klass="C")]}
        self.assertEqual(apply_previous_snapshot(current, previous), [])
        self.assertEqual(current[0]["transition"]["transition"], "C_TO_B")
        self.assertEqual(current[0]["decision_guardrails"]["position"]["final_max"], 0.0)

        jumping = [stock("sz000001", "银行", 1.0, klass="A")]
        warnings = apply_previous_snapshot(jumping, previous)
        self.assertTrue(warnings)
        self.assertEqual(jumping[0]["decision_guardrails"]["mechanical_class"], "C")

    def test_d_cannot_upgrade(self):
        current = [stock("sz000001", "银行", 1.0, klass="A")]
        previous = {"stocks": [stock("sz000001", "银行", -1.0, klass="D")]}
        warnings = apply_previous_snapshot(current, previous)
        self.assertTrue(warnings)
        self.assertEqual(current[0]["decision_guardrails"]["mechanical_class"], "D")


if __name__ == "__main__":
    unittest.main()
