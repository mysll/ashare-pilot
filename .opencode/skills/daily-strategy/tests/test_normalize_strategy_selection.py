from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalize_strategy_selection import normalize  # noqa: E402
from test_validate_strategy_json import v2_doc  # noqa: E402


class NormalizeSelectionTests(unittest.TestCase):
    def test_skip_none_rows_move_to_observation(self):
        doc = v2_doc()
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
        doc = v2_doc()
        doc["market"]["regime_prior"] = "weak"
        doc["stocks"] = [dict(deepcopy(doc["stocks"][0]), code=f"sz0000{i:02d}") for i in range(1, 10)]
        normalized, summary = normalize(doc)
        self.assertEqual(len(normalized["stocks"]), 7)
        self.assertEqual(summary["limit"], 7)
        self.assertEqual(len(normalized["observation_pool"]), 2)

    def test_non_buyable_rows_move_to_observation(self):
        doc = v2_doc()
        doc["stocks"][0]["direction"] = "看空"
        normalized, _ = normalize(doc)
        self.assertEqual(normalized["stocks"], [])
        self.assertIn("non_buyable_direction", normalized["observation_pool"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
