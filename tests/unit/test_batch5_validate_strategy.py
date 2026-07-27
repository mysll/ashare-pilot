from __future__ import annotations

import json
import unittest
from pathlib import Path


from ashare_pilot.strategy._commands.daily.validate_strategy import validate


ROOT = Path(__file__).resolve().parents[2]


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
        "stocks": [stock],
        "observation_pool": [],
    }


class StrategyValidationTests(unittest.TestCase):
    def test_v3_valid(self):
        self.assertEqual(validate(v3_doc()), [])

    def test_v3_rejects_pre_0935_entry(self):
        doc = v3_doc()
        doc["stocks"][0]["preopen_plan"]["earliest_entry_time"] = "09:30:00"
        self.assertTrue(any("09:35:05" in item for item in validate(doc)))

    def test_v3_requires_source_basis_for_every_selected_stock(self):
        doc = v3_doc()
        doc["stocks"][0]["reasoning"]["source_basis"] = ""
        self.assertTrue(any("reasoning.source_basis" in item for item in validate(doc)))

    def test_v3_rejects_semantically_invalid_times(self):
        for field, value in (("earliest_entry_time", "10:99:00"), ("latest_entry_time", "25:00:00")):
            with self.subTest(field=field, value=value):
                doc = v3_doc()
                doc["stocks"][0]["preopen_plan"][field] = value
                self.assertTrue(any("must be a real time" in item for item in validate(doc)))

    def test_v3_rejects_numeric_position_budget(self):
        doc = v3_doc()
        doc["stocks"][0]["position_budget"] = 0.03
        self.assertTrue(any("position_budget" in item and "forbidden" in item for item in validate(doc)))

    def test_v3_enforces_regime_stock_limit(self):
        doc = v3_doc()
        doc["market"]["regime_prior"] = "panic"
        doc["stocks"] = [dict(doc["stocks"][0], code=f"sz00000{i}") for i in range(1, 7)]
        self.assertTrue(any("at most 5" in item for item in validate(doc)))

    def test_v3_moves_non_buyable_rows_to_observation_pool(self):
        for field, value in (("direction", "看空"), ("entry_profile", "暂不参与")):
            with self.subTest(field=field):
                doc = v3_doc()
                doc["stocks"][0][field] = value
                self.assertTrue(any("observation_pool" in item for item in validate(doc)))

    def test_v3_observation_rows_are_compact(self):
        doc = v3_doc()
        doc["observation_pool"] = [{"code": "sh600000", "name": "浦发银行", "reason": "观察", "anomaly": "extra"}]
        self.assertTrue(any("must contain only code, name, reason" in item for item in validate(doc)))

    def test_v3_rejects_numeric_exposure_limits(self):
        doc = v3_doc()
        doc["portfolio_limits"]["max_new_exposure"] = 0.1
        self.assertTrue(any("numeric exposure limits forbidden" in item for item in validate(doc)))

    def test_v3_requires_tier_and_preopen_decision_to_agree(self):
        doc = v3_doc()
        doc["stocks"][0]["position_tier"] = "WATCH_ONLY"
        self.assertTrue(any("WATCH_ONLY position tier" in item for item in validate(doc)))


if __name__ == "__main__":
    unittest.main()
