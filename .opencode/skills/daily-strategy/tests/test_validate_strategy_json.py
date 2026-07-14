from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_strategy_json import validate  # noqa: E402


ROOT = Path(__file__).resolve().parents[4]


def v2_doc():
    profile = {
        "playbook": "PULLBACK", "preferred_anchor": "MA5", "chase_policy": "MA5_ONLY",
        "entry_window": "MORNING_DIP", "stop_policy": "ATR_1.5", "time_horizon": "T+1",
    }
    stock = {
        "code": "sz000001", "name": "平安银行", "sector": "银行", "direction": "偏多",
        "rating": "3★", "entry_profile": "回调布局", "anchor": "MA5",
        "entry_trigger": "等待开盘确认", "no_buy_condition": "市场转弱则取消",
        "position_budget": 0.01, "horizon": "T+1", "profile": profile,
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
        "schema_version": "daily_strategy.v2", "date": "2026-07-13",
        "market": {"regime_prior": "neutral", "requires_open_confirmation": True},
        "portfolio_limits": {
            "max_new_exposure": 0.1, "max_theme_exposure": 0.04,
            "max_single_stock": 0.02, "max_correlated_names": 2,
        },
        "stocks": [stock],
        "observation_pool": [],
    }


class StrategyValidationTests(unittest.TestCase):
    def test_existing_v1_remains_valid(self):
        path = ROOT / "predict" / "2026-07-10" / "strategy.json"
        if not path.exists():
            self.skipTest("historical strategy fixture not present")
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(validate(doc), [])

    def test_v2_valid(self):
        self.assertEqual(validate(v2_doc(), require_v2=True), [])

    def test_v2_rejects_pre_0935_entry(self):
        doc = v2_doc()
        doc["stocks"][0]["preopen_plan"]["earliest_entry_time"] = "09:30:00"
        self.assertTrue(any("09:35:05" in item for item in validate(doc)))

    def test_v2_requires_source_basis_for_every_selected_stock(self):
        doc = v2_doc()
        doc["stocks"][0]["reasoning"]["source_basis"] = ""
        self.assertTrue(any("reasoning.source_basis" in item for item in validate(doc)))

    def test_v2_rejects_semantically_invalid_times(self):
        for field, value in (("earliest_entry_time", "10:99:00"), ("latest_entry_time", "25:00:00")):
            with self.subTest(field=field, value=value):
                doc = v2_doc()
                doc["stocks"][0]["preopen_plan"][field] = value
                self.assertTrue(any("must be a real time" in item for item in validate(doc)))

    def test_require_v2_rejects_v1(self):
        doc = v2_doc()
        doc["schema_version"] = "daily_strategy.v1"
        self.assertTrue(any("v2 required" in item for item in validate(doc, require_v2=True)))

    def test_v2_rejects_stock_budget_above_single_limit(self):
        doc = v2_doc()
        doc["stocks"][0]["position_budget"] = 0.03
        self.assertTrue(any("max_single_stock" in item for item in validate(doc)))

    def test_v2_enforces_regime_stock_limit(self):
        doc = v2_doc()
        doc["market"]["regime_prior"] = "panic"
        doc["stocks"] = [dict(doc["stocks"][0], code=f"sz00000{i}") for i in range(1, 7)]
        self.assertTrue(any("at most 5" in item for item in validate(doc)))

    def test_v2_moves_non_buyable_rows_to_observation_pool(self):
        for field, value in (("direction", "看空"), ("entry_profile", "暂不参与")):
            with self.subTest(field=field):
                doc = v2_doc()
                doc["stocks"][0][field] = value
                self.assertTrue(any("observation_pool" in item for item in validate(doc)))

    def test_v2_observation_rows_are_compact(self):
        doc = v2_doc()
        doc["observation_pool"] = [{"code": "sh600000", "name": "浦发银行", "reason": "观察", "anomaly": "extra"}]
        self.assertTrue(any("must contain only code, name, reason" in item for item in validate(doc)))


if __name__ == "__main__":
    unittest.main()
