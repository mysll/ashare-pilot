import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


LIB_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LIB_ROOT))

from lib.datasources.kline_cache import cache_checked_recently, load_cache, save_cache


class KlineCacheTests(unittest.TestCase):
    def test_sources_use_separate_cache_files(self):
        records = [{"date": "2026-07-20"}]

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            save_cache("sh600900", records, cache_dir=cache_dir, source="sohu")
            save_cache("sh600900", records, cache_dir=cache_dir, source="sina")

            self.assertTrue((cache_dir / "sohu" / "sh600900.json").exists())
            self.assertTrue((cache_dir / "sina" / "sh600900.json").exists())
            self.assertEqual(load_cache(
                "sh600900", cache_dir=cache_dir, source="sohu"
            )["records"], records)
            self.assertEqual(load_cache(
                "sh600900", cache_dir=cache_dir, source="sina"
            )["records"], records)

    def test_source_cache_does_not_adopt_unknown_legacy_cache(self):
        records = [{"date": "2026-07-20"}]

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            save_cache("sh600900", records, cache_dir=cache_dir)

            self.assertIsNotNone(load_cache("sh600900", cache_dir=cache_dir))
            self.assertIsNone(load_cache(
                "sh600900", cache_dir=cache_dir, source="sohu"
            ))

    def test_recent_check_is_separate_from_data_watermark(self):
        checked = datetime(2026, 7, 21, 9, 45, tzinfo=timezone.utc)
        cache = {
            "coverage_to": "2026-07-20",
            "checked_to": "2026-07-21",
            "checked_at": checked.isoformat(),
        }

        self.assertTrue(cache_checked_recently(
            cache, "2026-07-21", now=checked + timedelta(minutes=10)
        ))
        self.assertFalse(cache_checked_recently(
            cache, "2026-07-21", now=checked + timedelta(minutes=16)
        ))
        self.assertEqual(cache["coverage_to"], "2026-07-20")


if __name__ == "__main__":
    unittest.main()
