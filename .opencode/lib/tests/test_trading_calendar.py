import sys
import unittest
from datetime import date, datetime
from pathlib import Path


LIB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LIB_ROOT))

from lib.trading_calendar import expected_latest_bar, is_trading_day, previous_trading_day


class TradingCalendarTests(unittest.TestCase):
    def test_weekday_exchange_holiday_is_closed(self):
        self.assertFalse(is_trading_day(date(2026, 10, 5)))
        self.assertEqual(previous_trading_day(date(2026, 10, 8)), date(2026, 9, 30))

    def test_today_is_expected_only_after_publish_cutoff(self):
        before = datetime(2026, 7, 21, 15, 29)
        after = datetime(2026, 7, 21, 15, 31)

        self.assertEqual(expected_latest_bar(now=before), date(2026, 7, 20))
        self.assertEqual(expected_latest_bar(now=after), date(2026, 7, 21))

    def test_holiday_end_rolls_back_to_latest_session(self):
        now = datetime(2026, 10, 5, 16, 0)
        self.assertEqual(
            expected_latest_bar("20261005", now=now), date(2026, 9, 30)
        )


if __name__ == "__main__":
    unittest.main()
