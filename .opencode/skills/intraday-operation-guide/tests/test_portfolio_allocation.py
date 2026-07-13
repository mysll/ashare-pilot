from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from portfolio_allocation import apply_portfolio_limits  # noqa: E402


def candidate(code, sector, rating="4★", amount=0.02):
    return {
        "code": code,
        "strategy": {"sector": sector, "rating": rating},
        "theme_confirmation": {"theme_state": "CONFIRMED"},
        "transition": {"previous_class": "B", "current_class": "A", "transition": "B_TO_A", "adjusted": False},
        "decision_guardrails": {
            "mechanical_class": "A", "max_allowed_class": "A", "class_reasons": [],
            "position": {
                "morning_budget": amount, "market_adjusted_max": amount,
                "signal_adjusted_max": amount, "final_max": amount,
            },
        },
    }


class PortfolioAllocationTests(unittest.TestCase):
    def test_total_exposure_is_enforced(self):
        stocks = [candidate(f"sz00000{i}", f"主题{i}") for i in range(1, 6)]
        result = apply_portfolio_limits(stocks, {
            "max_new_exposure": 0.04, "max_theme_exposure": 0.04,
            "max_single_stock": 0.02, "max_correlated_names": 2,
        })
        self.assertEqual(result["allocated_exposure"], 0.04)
        self.assertEqual(sum(s["decision_guardrails"]["position"]["final_max"] for s in stocks), 0.04)
        self.assertEqual(sum(s["decision_guardrails"]["mechanical_class"] == "A" for s in stocks), 2)

    def test_theme_and_correlated_limits_are_enforced(self):
        stocks = [candidate("sz000001", "银行"), candidate("sz000002", "银行"), candidate("sz000003", "银行")]
        result = apply_portfolio_limits(stocks, {
            "max_new_exposure": 0.10, "max_theme_exposure": 0.025,
            "max_single_stock": 0.02, "max_correlated_names": 2,
        })
        self.assertEqual(result["allocated_by_theme"]["银行"], 0.025)
        self.assertLessEqual(result["allocated_names_by_theme"]["银行"], 2)
        self.assertEqual(stocks[0]["decision_guardrails"]["position"]["final_max"], 0.02)
        self.assertEqual(stocks[1]["decision_guardrails"]["position"]["final_max"], 0.005)
        self.assertEqual(stocks[2]["decision_guardrails"]["mechanical_class"], "B")
        self.assertEqual(stocks[2]["transition"]["current_class"], "B")

    def test_single_stock_limit_is_enforced(self):
        stocks = [candidate("sz000001", "银行", amount=0.03)]
        apply_portfolio_limits(stocks, {
            "max_new_exposure": 0.10, "max_theme_exposure": 0.10,
            "max_single_stock": 0.01, "max_correlated_names": 2,
        })
        self.assertEqual(stocks[0]["decision_guardrails"]["position"]["final_max"], 0.01)


if __name__ == "__main__":
    unittest.main()
