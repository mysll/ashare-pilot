from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_operation_snapshot import validate  # noqa: E402
from build_operation_decision import build as build_decision  # noqa: E402
from validate_operation_decision import validate as validate_decision  # noqa: E402
import json
import tempfile


def snapshot():
    return {
        "schema_version": "intraday_operation_snapshot.v2",
        "date": "2026-07-10",
        "generated_at": "2026-07-10T09:40:05+08:00",
        "snapshot_slot": "09:40",
        "market_confirmation": {
            "global_action": "SELECTIVE",
            "indices": {"sh000001": {}, "sz399001": {}, "sh000688": {}},
        },
        "delivery_confirmation": {
            "delivery_status": "ON_TIME_INITIAL", "execution_action": "EVALUATE",
            "late_initial_snapshot": False, "requires_second_confirmation": True,
        },
        "theme_confirmations": {
            "银行": {"theme_state": "CONFIRMED"}
        },
        "portfolio_allocation": {
            "limits": {
                "max_new_exposure": 0.1, "max_theme_exposure": 0.05,
                "max_single_stock": 0.02, "max_correlated_names": 2,
            },
            "allocated_exposure": 0.01,
        },
        "stocks": [{
            "code": "sz000001",
            "signals": {
                "first_bar": {"is_complete": True, "bar_end": "2026-07-10T09:35:00+08:00"},
                "latest_completed_bar": {"is_complete": True, "bar_end": "2026-07-10T09:40:00+08:00"},
            },
            "decision_guardrails": {
                "mechanical_class": "A",
                "max_allowed_class": "A",
                "position": {
                    "morning_budget": 0.02,
                    "market_adjusted_max": 0.01,
                    "signal_adjusted_max": 0.01,
                    "portfolio_adjusted_max": 0.01,
                    "final_max": 0.01,
                },
                "t1_controls": {"same_day_sell_allowed": False, "t1_exit_plan": {}},
            },
            "transition": {"previous_class": None, "current_class": "A", "transition": "INIT_TO_A", "adjusted": False},
        }],
    }


class SnapshotValidationTests(unittest.TestCase):
    def test_valid_snapshot(self):
        self.assertEqual(validate(snapshot()), [])

    def test_future_bar_rejected(self):
        doc = snapshot()
        doc["stocks"][0]["signals"]["latest_completed_bar"]["bar_end"] = "2026-07-10T09:45:00+08:00"
        self.assertTrue(any("after snapshot" in item for item in validate(doc)))

    def test_position_expansion_rejected(self):
        doc = snapshot()
        doc["stocks"][0]["decision_guardrails"]["position"]["final_max"] = 0.03
        self.assertTrue(any("monotonically decrease" in item for item in validate(doc)))

    def test_no_new_buy_rejects_a_cap(self):
        doc = deepcopy(snapshot())
        doc["market_confirmation"]["global_action"] = "NO_NEW_BUY"
        self.assertTrue(any("caps class at C" in item for item in validate(doc)))

    def test_decision_projection_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(snapshot()), encoding="utf-8")
            decision = build_decision(snapshot(), path)
            self.assertEqual(validate_decision(decision), [])
            self.assertEqual(decision["portfolio"]["actionable_exposure"], 0.01)

    def test_v2_snapshot_requires_preserved_limits_and_t1_plan(self):
        doc = snapshot()
        doc["source_strategy"] = {"schema_version": "daily_strategy.v2"}
        errors = validate(doc)
        self.assertTrue(any("preserve v2" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
