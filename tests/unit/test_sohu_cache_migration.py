import unittest
from unittest.mock import patch


from ashare_pilot.market_data._datasources.sohu import SohuDataSource


def record(date):
    return {
        "date": date,
        "open": "1",
        "close": "1",
        "change": "0",
        "change_pct": "0",
        "low": "1",
        "high": "1",
        "volume": "1",
        "amount": "1",
        "turnover": "1",
    }


class SohuCacheTests(unittest.TestCase):
    def setUp(self):
        self.source = SohuDataSource()
        self.cached = [record("2026-07-16"), record("2026-07-17")]

    @patch("ashare_pilot.market_data._datasources.sohu.save_cache")
    @patch("ashare_pilot.market_data._datasources.sohu.load_cache")
    def test_false_coverage_is_refetched_and_repaired(self, load, save):
        load.return_value = {
            "records": self.cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-21",
        }
        delayed_record = record("2026-07-20")

        with patch.object(self.source, "_fetch_raw", return_value=[delayed_record]) as fetch:
            result = self.source.fetch_history(
                "sh600900", start="20260716", end="20260721"
            )

        fetch.assert_called_once_with("cn_600900", "20260718", "20260721")
        self.assertEqual([row["date"] for row in result], [
            "2026-07-16", "2026-07-17", "2026-07-20"
        ])
        self.assertEqual(save.call_args.kwargs["coverage_to"], "2026-07-20")
        self.assertEqual(save.call_args.kwargs["source"], "sohu")

    @patch("ashare_pilot.market_data._datasources.sohu.save_cache")
    @patch("ashare_pilot.market_data._datasources.sohu.load_cache")
    def test_empty_response_does_not_advance_coverage(self, load, save):
        load.return_value = {
            "records": self.cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-17",
        }

        with patch.object(self.source, "_fetch_raw", return_value=[]):
            result = self.source.fetch_history(
                "sh600900", start="20260718", end="20260721"
            )

        self.assertEqual(result, [])
        self.assertEqual(save.call_args.kwargs["coverage_to"], "2026-07-17")
        self.assertEqual(save.call_args.kwargs["checked_to"], "2026-07-21")

    @patch("ashare_pilot.market_data._datasources.sohu.save_cache")
    @patch("ashare_pilot.market_data._datasources.sohu.load_cache")
    def test_network_failure_does_not_stamp_successful_check(self, load, save):
        load.return_value = {
            "records": self.cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-17",
        }

        with patch.object(self.source, "_fetch_raw", return_value=None):
            result = self.source.fetch_history(
                "sh600900", start="20260716", end="20260721"
            )

        self.assertEqual(result, self.cached)
        save.assert_not_called()

    @patch("ashare_pilot.market_data._datasources.sohu.cache_checked_recently", return_value=True)
    @patch("ashare_pilot.market_data._datasources.sohu.save_cache")
    @patch("ashare_pilot.market_data._datasources.sohu.load_cache")
    def test_recent_empty_check_throttles_retry(self, load, save, _recent):
        load.return_value = {
            "records": self.cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-17",
            "checked_at": "2026-07-21T09:45:00+08:00",
            "checked_to": "2026-07-21",
        }

        with patch.object(self.source, "_fetch_raw") as fetch:
            result = self.source.fetch_history(
                "sh600900", start="20260716", end="20260721"
            )

        self.assertEqual(result, self.cached)
        fetch.assert_not_called()
        save.assert_not_called()

    @patch("ashare_pilot.market_data._datasources.sohu.save_cache")
    @patch("ashare_pilot.market_data._datasources.sohu.load_cache", return_value=None)
    def test_new_cache_uses_actual_record_dates(self, _load, save):
        rows = [record("2026-07-17"), record("2026-07-20")]

        with patch.object(self.source, "_fetch_raw", return_value=rows):
            self.source.fetch_history(
                "sh600900", start="20260716", end="20260721"
            )

        self.assertEqual(save.call_args.kwargs["coverage_from"], "2026-07-17")
        self.assertEqual(save.call_args.kwargs["coverage_to"], "2026-07-20")


if __name__ == "__main__":
    unittest.main()
