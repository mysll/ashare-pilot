from __future__ import annotations

import json
import unittest
from pathlib import Path

from ashare_pilot.strategy._commands.daily.compare_shadow import compare


def strategy(codes=("sz000001",), direction="看多", regime="neutral"):
    return {
        "market": {"regime_prior": regime},
        "stocks": [{"code": code, "direction": direction} for code in codes],
    }


class StrategyShadowTests(unittest.TestCase):
    def test_same_decisions_pass(self):
        self.assertTrue(compare(strategy(), strategy())["passed"])

    def test_selection_order_change_blocks(self):
        report = compare(strategy(("sz000001", "sh600000")), strategy(("sh600000", "sz000001")))
        self.assertFalse(report["passed"])
        self.assertIn("selected stock codes/order changed", report["blocked"])

    def test_direction_or_regime_change_blocks(self):
        self.assertFalse(compare(strategy(), strategy(direction="看空"))["passed"])
        self.assertFalse(compare(strategy(), strategy(regime="weak"))["passed"])

    def test_rating_budget_profile_anchor_and_rules_are_locked(self):
        before = strategy(("sh600001",))
        before["stocks"][0].update({
            "rating": "5★", "position_budget": 0.02, "entry_profile": "回调布局",
            "anchor": "MA20", "rules_applied": ["R70"], "profile": {"playbook": "PULLBACK"},
        })
        after = json.loads(json.dumps(before, ensure_ascii=False))
        after["stocks"][0]["rating"] = "4★"
        report = compare(before, after)
        self.assertFalse(report["passed"])
        self.assertIn("sh600001", report["field_differences"])

    def test_2026_07_14_source_grounding_change_is_reported(self):
        path = Path(__file__).resolve().parents[1] / "fixtures" / "strategy" / "strategy_shadow_2026-07-14.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        report = compare(fixture["before"], fixture["after"])
        self.assertFalse(report["passed"])
        self.assertTrue(report["source_grounding_differences"])
        self.assertEqual(len(report["after_codes"]), 10)

    def test_live_mode_ignores_reference_only_profile_noise(self):
        before = strategy(("sh600001",))
        before["stocks"][0]["profile"] = {
            "playbook": "PULLBACK", "preferred_anchor": "MA20", "chase_policy": "NO_CHASE",
            "entry_window": "ANY", "stop_policy": "ATR_1.5", "time_horizon": "T+1",
            "position_budget": 0.02, "ref_ma20": 10.0,
        }
        after = json.loads(json.dumps(before, ensure_ascii=False))
        after["stocks"][0]["profile"]["ref_ma20"] = 10.01
        self.assertFalse(compare(before, after, mode="frozen")["passed"])
        self.assertTrue(compare(before, after, mode="live")["passed"])


if __name__ == "__main__":
    unittest.main()
