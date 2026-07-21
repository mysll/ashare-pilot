import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


LIB_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LIB_ROOT))

from lib.fetch.fetch_history import fetch_history


def record(day, close="1"):
    return {"date": day, "close": close}


class FetchHistoryFallbackTests(unittest.TestCase):
    @patch("lib.fetch.fetch_history.expected_latest_bar", return_value=date(2026, 7, 20))
    @patch("lib.fetch.fetch_history._sina")
    @patch("lib.fetch.fetch_history._sohu")
    def test_empty_sohu_result_falls_back_to_sina(self, sohu, sina, _expected):
        latest = "2026-07-20"
        sohu.fetch_history.return_value = []
        sina.fetch_daily_history.return_value = [record(latest)]

        result = fetch_history("sh600900", range_str="5d")

        self.assertEqual(result, [record(latest)])
        sina.fetch_daily_history.assert_called_once()

    @patch("lib.fetch.fetch_history.expected_latest_bar", return_value=date(2026, 7, 20))
    @patch("lib.fetch.fetch_history._sina")
    @patch("lib.fetch.fetch_history._sohu")
    def test_stale_sohu_uses_full_sina_series(self, sohu, sina, _expected):
        stale = "2026-07-17"
        latest = "2026-07-20"
        sohu.fetch_history.return_value = [record(stale, "sohu")]
        sina.fetch_daily_history.return_value = [
            record(stale, "sina"),
            record(latest, "sina"),
        ]

        result = fetch_history("sh600900", range_str="5d")

        self.assertEqual([row["date"] for row in result], [
            stale, latest
        ])
        self.assertEqual(result[0]["close"], "sina")

    @patch("lib.fetch.fetch_history.expected_latest_bar", return_value=date(2026, 7, 20))
    @patch("lib.fetch.fetch_history._sina")
    @patch("lib.fetch.fetch_history._sohu")
    def test_current_sohu_result_does_not_call_sina(self, sohu, sina, _expected):
        latest = "2026-07-20"
        sohu.fetch_history.return_value = [record(latest)]

        result = fetch_history("sh600900", range_str="5d")

        self.assertEqual(result, [record(latest)])
        sina.fetch_daily_history.assert_not_called()

    @patch("lib.fetch.fetch_history.expected_latest_bar", return_value=date(2026, 7, 20))
    @patch("lib.fetch.fetch_history._sina")
    @patch("lib.fetch.fetch_history._sohu")
    def test_fresher_sina_can_start_later_than_primary(
        self, sohu, sina, _expected
    ):
        primary = [record("2026-07-10", "sohu"), record("2026-07-17", "sohu")]
        sohu.fetch_history.return_value = primary
        fallback = [record("2026-07-11", "sina"), record("2026-07-20", "sina")]
        sina.fetch_daily_history.return_value = fallback

        result = fetch_history("sh600900", range_str="1m")

        self.assertEqual(result, fallback)

    @patch("lib.fetch.fetch_history._sina")
    @patch("lib.fetch.fetch_history._sohu")
    def test_explicit_dates_filter_sina_fallback(self, sohu, sina):
        sohu.fetch_history.return_value = []
        sina.fetch_daily_history.return_value = [
            record("2026-07-17"), record("2026-07-20"), record("2026-07-21")
        ]

        result = fetch_history(
            "sh600900", start="20260718", end="20260720", range_str="5d"
        )

        self.assertEqual(result, [record("2026-07-20")])


if __name__ == "__main__":
    unittest.main()
