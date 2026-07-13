from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from market_confirmation import build_market_confirmation  # noqa: E402
from mechanical_classification import CLASS_RANK, compute_mechanical_decision  # noqa: E402
from operation_time import MARKET_TZ  # noqa: E402


def quote(code, current, open_price=100, previous=100):
    return {"code": code, "percent": current, "open": open_price, "yestclose": previous, "time": "2026-07-10 09:40:01"}


class MarketTests(unittest.TestCase):
    def test_weak_sz_forces_no_new_buy(self):
        market = build_market_confirmation([
            quote("sh000001", -0.3), quote("sz399001", -0.8), quote("sh000688", -1.2)
        ], "strong-sector")
        self.assertEqual(market["regime_live"], "weak")
        self.assertEqual(market["global_action"], "NO_NEW_BUY")

    def test_kcb_strength_does_not_override_sz_weakness(self):
        market = build_market_confirmation([
            quote("sh000001", -0.1), quote("sz399001", -0.4), quote("sh000688", 1.5)
        ], "strong-sector")
        self.assertEqual(market["regime_live"], "neutral")
        self.assertNotEqual(market["global_action"], "NORMAL")

    def test_missing_index_forces_wait(self):
        market = build_market_confirmation([quote("sh000001", 0.1)], "neutral")
        self.assertEqual(market["global_action"], "WAIT")


class ClassificationTests(unittest.TestCase):
    when = datetime(2026, 7, 10, 9, 40, 5, tzinfo=MARKET_TZ)
    strategy = {"direction": "看多", "profile": "趋势跟随", "position": 0.02, "no_buy": "破位取消"}
    signals = {
        "data_warning": [], "below_vwap": False, "high_open_fade": False,
        "extended_from_anchor": False, "near_ma5": True, "near_ma20": False,
        "first_bar": {"red_flag": False, "price_strength_confirmed": True},
        "latest_completed_bar": {"price_strength_confirmed": True, "volume_confirmed": True},
    }

    def test_no_new_buy_caps_at_c_and_zero_position(self):
        result = compute_mechanical_decision(self.strategy, self.signals, {"global_action": "NO_NEW_BUY"}, self.when)
        self.assertLessEqual(CLASS_RANK[result["max_allowed_class"]], CLASS_RANK["C"])
        self.assertEqual(result["position"]["final_max"], 0)

    def test_selective_never_expands_morning_budget(self):
        result = compute_mechanical_decision(self.strategy, self.signals, {"global_action": "SELECTIVE"}, self.when)
        caps = result["position"]
        self.assertLessEqual(caps["final_max"], caps["market_adjusted_max"])
        self.assertLessEqual(caps["market_adjusted_max"], caps["morning_budget"])
        self.assertFalse(result["t1_controls"]["same_day_sell_allowed"])

    def test_v2_t1_plan_is_preserved(self):
        strategy = dict(self.strategy)
        strategy.update({
            "strategy_schema_version": "daily_strategy.v2",
            "t1_risk_plan": {
                "overnight_risk": "high", "gap_up_action": "自定义高开",
                "flat_open_action": "自定义平开", "gap_down_action": "自定义低开",
                "max_holding_days": 3,
            },
        })
        result = compute_mechanical_decision(strategy, self.signals, {"global_action": "SELECTIVE"}, self.when)
        plan = result["t1_controls"]["t1_exit_plan"]
        self.assertEqual(plan["source"], "daily_strategy.v2")
        self.assertEqual(plan["gap_up_action"], "自定义高开")
        self.assertEqual(plan["max_holding_days"], 3)

    def test_v2_invalid_time_does_not_silently_fallback(self):
        strategy = dict(self.strategy)
        strategy.update({
            "strategy_schema_version": "daily_strategy.v2",
            "preopen_plan": {"earliest_entry_time": "10:99:00", "latest_entry_time": "11:00:00"},
        })
        with self.assertRaisesRegex(ValueError, "invalid v2"):
            compute_mechanical_decision(strategy, self.signals, {"global_action": "SELECTIVE"}, self.when)


if __name__ == "__main__":
    unittest.main()
