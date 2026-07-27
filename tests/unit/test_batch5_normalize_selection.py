from __future__ import annotations

import unittest
from copy import deepcopy


from ashare_pilot.strategy._commands.daily.normalize_selection import normalize


def v3_doc():
    profile = {
        "playbook": "PULLBACK", "preferred_anchor": "MA5", "chase_policy": "MA5_ONLY",
        "entry_window": "MORNING_DIP", "stop_policy": "ATR_1.5", "time_horizon": "T+1",
    }
    stock = {
        "code": "sz000001", "name": "平安银行", "sector": "银行", "direction": "偏多",
        "rating": "3★", "entry_profile": "回调布局", "anchor": "MA5",
        "entry_trigger": "等待开盘确认", "no_buy_condition": "市场转弱则取消",
        "position_tier": "LIGHT", "horizon": "T+1", "profile": profile,
        "reasoning": {"source_basis": "银行主题候选，来自 ThemeLibrary"},
        "preopen_plan": {
            "decision": "CONDITIONAL", "earliest_entry_time": "09:40:05",
            "latest_entry_time": "10:00:00", "requires_first_bar": True,
            "requires_market_confirmation": True, "requires_theme_confirmation": True,
            "entry_setup": "PULLBACK", "pre_entry_invalidations": ["市场转弱则取消"],
        },
        "t1_risk_plan": {
            "overnight_risk": "medium", "gap_up_action": "承接不足兑现",
            "flat_open_action": "反弹失败退出", "gap_down_action": "禁止补仓优先退出",
            "max_holding_days": 2,
        },
    }
    return {
        "schema_version": "daily_strategy.v3", "date": "2026-07-13",
        "market": {"regime_prior": "neutral", "requires_open_confirmation": True},
        "portfolio_limits": {
            "max_new_positions": 7, "max_theme_positions": 3,
            "max_correlated_names": 2,
        },
        "stocks": [stock], "observation_pool": [],
    }


class NormalizeSelectionTests(unittest.TestCase):
    def test_skip_none_rows_move_to_observation(self):
        doc = v3_doc()
        skipped = deepcopy(doc["stocks"][0])
        skipped["code"] = "sz000002"
        skipped["preopen_plan"]["decision"] = "SKIP"
        skipped["preopen_plan"]["entry_setup"] = "NONE"
        doc["stocks"].append(skipped)
        normalized, summary = normalize(doc)
        self.assertEqual(len(normalized["stocks"]), 1)
        self.assertEqual(normalized["observation_pool"][0]["code"], "sz000002")
        self.assertIn("unsupported_decision", normalized["observation_pool"][0]["reason"])
        self.assertEqual(summary["moved_to_observation"], 1)

    def test_weak_regime_truncates_to_seven(self):
        doc = v3_doc()
        doc["market"]["regime_prior"] = "weak"
        doc["stocks"] = [dict(deepcopy(doc["stocks"][0]), code=f"sz0000{i:02d}") for i in range(1, 10)]
        normalized, summary = normalize(doc)
        self.assertEqual(len(normalized["stocks"]), 7)
        self.assertEqual(summary["limit"], 7)
        self.assertEqual(len(normalized["observation_pool"]), 2)

    def test_non_buyable_rows_move_to_observation(self):
        doc = v3_doc()
        doc["stocks"][0]["direction"] = "看空"
        normalized, _ = normalize(doc)
        self.assertEqual(normalized["stocks"], [])
        self.assertIn("non_buyable_direction", normalized["observation_pool"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
