import unittest
from datetime import datetime as RealDateTime
from unittest.mock import patch


from ashare_pilot.market_data._datasources.sina import SinaDataSource


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


class FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 21, 9, 47, 0, tzinfo=tz)


class FixedAfterCloseDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 21, 15, 31, 0, tzinfo=tz)


class SinaCacheTests(unittest.TestCase):
    @patch("ashare_pilot.market_data._datasources.sina.save_cache")
    @patch("ashare_pilot.market_data._datasources.sina.load_cache")
    @patch("ashare_pilot.market_data._datasources.sina.datetime", FixedDateTime)
    def test_delayed_nonempty_data_does_not_claim_today(self, load, save):
        cached = [record("2026-07-16"), record("2026-07-17")]
        load.return_value = {
            "records": cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-21",
        }
        delayed = [record("2026-07-17"), record("2026-07-20")]
        source = SinaDataSource()

        with patch.object(source, "_fetch_daily_php", return_value=[{"day": "raw"}]), \
                patch.object(source, "_fetch_rs_amount", return_value=None), \
                patch.object(source, "_enrich_records", return_value=delayed):
            result = source.fetch_daily_history("sh600900", "5d")

        self.assertEqual(result[-1]["date"], "2026-07-20")
        self.assertEqual(save.call_args.kwargs["coverage_to"], "2026-07-20")
        self.assertEqual(save.call_args.kwargs["checked_to"], "2026-07-20")
        self.assertEqual(save.call_args.kwargs["source"], "sina")

    @patch("ashare_pilot.market_data._datasources.sina.cache_checked_recently", return_value=True)
    @patch("ashare_pilot.market_data._datasources.sina.load_cache")
    @patch("ashare_pilot.market_data._datasources.sina.datetime", FixedDateTime)
    def test_recent_check_returns_cache_without_network(self, load, _recent):
        cached = [record("2026-07-16"), record("2026-07-20")]
        load.return_value = {
            "records": cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-17",
            "checked_at": "2026-07-21T09:45:00+08:00",
            "checked_to": "2026-07-20",
        }
        source = SinaDataSource()

        with patch.object(source, "_fetch_daily_php") as fetch:
            result = source.fetch_daily_history("sh600900", "5d")

        self.assertEqual(result, cached)
        fetch.assert_not_called()

    @patch("ashare_pilot.market_data._datasources.sina.cache_checked_recently", return_value=True)
    @patch("ashare_pilot.market_data._datasources.sina.save_cache")
    @patch("ashare_pilot.market_data._datasources.sina.load_cache")
    @patch("ashare_pilot.market_data._datasources.sina.datetime", FixedDateTime)
    def test_short_cache_does_not_satisfy_longer_range(
        self, load, save, _recent
    ):
        cached = [record("2026-07-16"), record("2026-07-20")]
        load.return_value = {
            "records": cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-20",
            "checked_at": "2026-07-21T09:45:00+08:00",
            "checked_to": "2026-07-21",
        }
        full_range = [record("2026-04-22"), record("2026-07-20")]
        source = SinaDataSource()

        with patch.object(source, "_fetch_daily_php", return_value=[{"day": "raw"}]), \
                patch.object(source, "_fetch_rs_amount", return_value=None), \
                patch.object(source, "_enrich_records", return_value=full_range):
            result = source.fetch_daily_history("sh600900", "3m")

        self.assertEqual(result, full_range)
        save.assert_called_once()

    @patch("ashare_pilot.market_data._datasources.sina.save_cache")
    @patch("ashare_pilot.market_data._datasources.sina.load_cache")
    @patch("ashare_pilot.market_data._datasources.sina.datetime", FixedDateTime)
    def test_short_cache_is_not_returned_after_fetch_failure(self, load, save):
        cached = [record("2026-07-16"), record("2026-07-20")]
        load.return_value = {
            "records": cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-20",
        }
        source = SinaDataSource()

        with patch.object(source, "_fetch_daily_php", return_value=None), \
                patch.object(source, "_fetch_daily_scale240", return_value=None):
            result = source.fetch_daily_history("sh600900", "3m")

        self.assertIsNone(result)
        save.assert_not_called()

    @patch("ashare_pilot.market_data._datasources.sina.save_cache")
    @patch("ashare_pilot.market_data._datasources.sina.load_cache")
    @patch("ashare_pilot.market_data._datasources.sina.datetime", FixedAfterCloseDateTime)
    def test_after_close_expects_todays_bar(self, load, save):
        cached = [record("2026-07-16"), record("2026-07-20")]
        load.return_value = {
            "records": cached,
            "coverage_from": "2026-07-16",
            "coverage_to": "2026-07-20",
        }
        current = [record("2026-07-20"), record("2026-07-21")]
        source = SinaDataSource()

        with patch.object(source, "_fetch_daily_php", return_value=[{"day": "raw"}]), \
                patch.object(source, "_fetch_rs_amount", return_value=None), \
                patch.object(source, "_enrich_records", return_value=current):
            result = source.fetch_daily_history("sh600900", "5d")

        self.assertEqual(result[-1]["date"], "2026-07-21")
        self.assertEqual(save.call_args.kwargs["checked_to"], "2026-07-21")


if __name__ == "__main__":
    unittest.main()
