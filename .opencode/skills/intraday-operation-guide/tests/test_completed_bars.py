from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from operation_time import MARKET_TZ, first_session_bar, select_completed_bars  # noqa: E402


def bars():
    return [
        {"time": "2026-07-10 09:35:00", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 100},
        {"time": "2026-07-10 09:40:00", "open": 10.1, "high": 10.3, "low": 10, "close": 10.2, "volume": 120},
    ]


class CompletedBarTests(unittest.TestCase):
    trade_date = date(2026, 7, 10)

    def at(self, hour, minute, second):
        return datetime(2026, 7, 10, hour, minute, second, tzinfo=MARKET_TZ)

    def test_093459_has_no_completed_first_bar(self):
        completed = select_completed_bars(bars(), self.at(9, 34, 59), self.trade_date)
        self.assertEqual(completed, [])

    def test_093505_includes_only_first_bar(self):
        completed = select_completed_bars(bars(), self.at(9, 35, 5), self.trade_date)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["bar_end"], "2026-07-10T09:35:00+08:00")

    def test_093600_excludes_094000_bucket(self):
        completed = select_completed_bars(bars(), self.at(9, 36, 0), self.trade_date)
        self.assertEqual(len(completed), 1)

    def test_094005_includes_second_bar(self):
        completed = select_completed_bars(bars(), self.at(9, 40, 5), self.trade_date)
        self.assertEqual(len(completed), 2)
        self.assertEqual(first_session_bar(completed, self.trade_date), completed[0])


if __name__ == "__main__":
    unittest.main()
