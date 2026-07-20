from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_operation_snapshot as builder  # noqa: E402
from validate_operation_snapshot import validate  # noqa: E402


class OfflineReplayTests(unittest.TestCase):
    def test_cli_builds_valid_slot_snapshot_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predict = root / "predict" / "2026-07-10"
            intraday = root / "fixtures" / "intraday"
            predict.mkdir(parents=True)
            intraday.mkdir(parents=True)
            strategy = {
                "schema_version": "daily_strategy.v1", "date": "2026-07-10",
                "market": {"regime_hint": "strong-sector"},
                "stocks": [{
                    "code": "sz000001", "name": "测试", "sector": "银行", "direction": "看多",
                    "entry_profile": "趋势跟随", "anchor": "MA5", "entry_trigger": "确认后参与",
                    "no_buy_condition": "转弱取消", "position_budget": 0.02,
                }],
            }
            mapper = {
                "schema_version": "daily_mapper.v1", "date": "2026-07-10",
                "candidate_pool": [{
                    "code": "sz000001", "strategy_inputs": {
                        "price": 10, "price_source": "PrevClose", "ma20": 9.5, "ma5": 10,
                        "atr": 0.5, "atr_pct": 5, "high20": 11, "low20": 8,
                    },
                }],
                "observation_pool": [],
            }
            quotes = {
                "stocks": [{
                    "code": "sz000001", "name": "测试", "price": 10.2, "open": 10,
                    "high": 10.3, "low": 9.9, "percent": 2, "yestclose": 10,
                    "amount": 1020000, "volume": 100000, "time": "2026-07-10 09:40:01",
                }],
                "indices": [
                    {"code": "sh000001", "percent": 0.2, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
                    {"code": "sz399001", "percent": 0.5, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
                    {"code": "sh000688", "percent": 0.8, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
                ],
            }
            bars = [
                {"time": "2026-07-10 09:35:00", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 100},
                {"time": "2026-07-10 09:40:00", "open": 10.1, "high": 10.3, "low": 10, "close": 10.2, "volume": 160},
                {"time": "2026-07-10 09:45:00", "open": 10.2, "high": 10.4, "low": 10.1, "close": 10.3, "volume": 180},
            ]
            (predict / "strategy.json").write_text(json.dumps(strategy), encoding="utf-8")
            (predict / "mapper.json").write_text(json.dumps(mapper), encoding="utf-8")
            quotes_path = root / "fixtures" / "quotes.json"
            quotes_path.write_text(json.dumps(quotes), encoding="utf-8")
            (intraday / "sz000001.json").write_text(json.dumps(bars), encoding="utf-8")
            output = root / "operation" / "2026-07-10" / "operation_snapshot_0940.json"
            argv = [
                "build_operation_snapshot.py", "--date", "2026-07-10", "--slot", "09:40",
                "--as-of", "2026-07-10T09:40:10+08:00", "--quotes-fixture", str(quotes_path),
                "--intraday-fixture-dir", str(intraday), "--no-network", "-o", str(output),
            ]
            with patch.object(builder, "ROOT", root), patch.object(sys, "argv", argv):
                self.assertEqual(builder.main(), 0)
            doc = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(validate(doc), [])
            self.assertEqual(doc["snapshot_slot"], "09:40")
            self.assertEqual(doc["stocks"][0]["signals"]["completed_bar_count"], 2)
            self.assertEqual(doc["delivery_confirmation"]["execution_action"], "WAIT_SECOND_CONFIRMATION")
            self.assertEqual(doc["stocks"][0]["decision_guardrails"]["position"]["final_max"], 0)

            continuation = root / "operation" / "2026-07-10" / "operation_snapshot_0945.json"
            argv = [
                "build_operation_snapshot.py", "--date", "2026-07-10", "--slot", "09:45",
                "--as-of", "2026-07-10T09:45:10+08:00", "--quotes-fixture", str(quotes_path),
                "--intraday-fixture-dir", str(intraday), "--no-network",
                "--previous-snapshot", str(output), "-o", str(continuation),
            ]
            with patch.object(builder, "ROOT", root), patch.object(sys, "argv", argv):
                self.assertEqual(builder.main(), 0)
            continued = json.loads(continuation.read_text(encoding="utf-8"))
            self.assertEqual(validate(continued), [])
            self.assertEqual(continued["run_mode"], "RECHECK")
            self.assertEqual(continued["delivery_confirmation"]["execution_action"], "EVALUATE")
            self.assertEqual(continued["lineage"]["previous_snapshot"], str(output))
            self.assertEqual(
                continued["lineage"]["previous_snapshot_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
