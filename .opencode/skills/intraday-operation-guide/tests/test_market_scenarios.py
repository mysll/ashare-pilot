from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

from market_confirmation import build_market_confirmation  # noqa: E402


class RecordedScenarioTests(unittest.TestCase):
    def test_market_regression_scenarios(self):
        fixture_root = SKILL / "tests" / "fixtures"
        for date in ("2026-07-08", "2026-07-09", "2026-07-10"):
            with self.subTest(date=date):
                scenario = json.loads((fixture_root / date / "market_scenario.json").read_text(encoding="utf-8"))
                self.assertEqual(scenario["fixture_kind"], "regression_scenario_not_raw_market_capture")
                actual = build_market_confirmation(scenario["indices"], scenario["regime_prior"])
                self.assertEqual(actual["regime_live"], scenario["expected"]["regime_live"])
                self.assertEqual(actual["global_action"], scenario["expected"]["global_action"])


if __name__ == "__main__":
    unittest.main()
