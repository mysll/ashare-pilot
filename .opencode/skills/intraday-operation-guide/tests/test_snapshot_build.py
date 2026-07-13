from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_operation_snapshot as builder  # noqa: E402
from operation_time import MARKET_TZ  # noqa: E402


class SnapshotBuildTests(unittest.TestCase):
    def test_build_stock_uses_only_completed_bar_and_caps_position(self):
        raw_bars = [
            {"time": "2026-07-10 09:35:00", "open": 10, "high": 10.2, "low": 9.9, "close": 10.15, "volume": 100},
            {"time": "2026-07-10 09:40:00", "open": 10.15, "high": 10.4, "low": 10.1, "close": 10.35, "volume": 130},
        ]
        strategy = {
            "code": "sz000001", "name": "测试", "direction": "看多",
            "profile": "趋势跟随", "anchor": "MA5", "position": 0.02,
            "no_buy": "跌破MA5取消",
        }
        mapper = {"ma5": 10, "ma20": 9.5, "atr": 0.5, "high20": 11, "low20": 8}
        quote = {
            "code": "sz000001", "name": "测试", "price": 10.2, "open": 10,
            "high": 10.3, "low": 9.9, "percent": 2, "yestclose": 10,
            "amount": 1020000, "volume": 100000, "time": "2026-07-10 09:36:00",
        }
        market = {"global_action": "SELECTIVE"}
        at = datetime(2026, 7, 10, 9, 36, 0, tzinfo=MARKET_TZ)
        with patch.object(builder, "fetch_intraday_kline", return_value=raw_bars):
            stock = builder.build_stock_snapshot("sz000001", strategy, mapper, quote, at, market)
        self.assertEqual(stock["signals"]["completed_bar_count"], 1)
        self.assertEqual(stock["signals"]["latest_completed_bar"]["bar_end"], "2026-07-10T09:35:00+08:00")
        caps = stock["decision_guardrails"]["position"]
        self.assertLessEqual(caps["final_max"], caps["morning_budget"])


if __name__ == "__main__":
    unittest.main()
