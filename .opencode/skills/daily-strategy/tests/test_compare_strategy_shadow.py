from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compare_strategy_shadow import compare  # noqa: E402


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

    def test_2026_07_14_frozen_source_basis_shadow_preserves_decisions(self):
        path = Path(__file__).parent / "fixtures" / "strategy_shadow_2026-07-14.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        report = compare(fixture["before"], fixture["after"])
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["after_codes"]), 10)


if __name__ == "__main__":
    unittest.main()
