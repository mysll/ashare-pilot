"""K-line data cache for Sohu historical data.

Caches fetched historical K-line records per stock as JSON files.
On subsequent fetches, only new data (gap between cache and today) is
requested from the API, then merged and written back.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / ".cache" / "kline"


def _fmt_to_date(date_str: str) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD (idempotent if already dashed)."""
    if len(date_str) == 8 and "-" not in date_str:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def _date_to_fmt(date_str: str) -> str:
    """Convert YYYY-MM-DD → YYYYMMDD."""
    return date_str.replace("-", "")


def next_day(date_str: str) -> str:
    d = datetime.strptime(date_str[:10], "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def prev_day(date_str: str) -> str:
    d = datetime.strptime(date_str[:10], "%Y-%m-%d") - timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def load_cache(code: str, cache_dir: Path = None) -> dict | None:
    """Load cached K-line data for a stock.

    Returns dict with keys 'records' (list, oldest-first),
    'coverage_from' (str, YYYY-MM-DD), 'coverage_to' (str, YYYY-MM-DD),
    or None on miss/corruption.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    path = cache_dir / f"{code}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        if not records:
            return None
        return {
            "records": records,
            "coverage_from": data.get("coverage_from", records[0]["date"]),
            "coverage_to": data.get("coverage_to", records[-1]["date"]),
        }
    except Exception:
        return None


def save_cache(code: str, records: list, coverage_from: str = None, coverage_to: str = None,
               cache_dir: Path = None) -> None:
    """Save K-line records to cache file."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = {
        "code": code,
        "updated_at": datetime.now().isoformat(),
        "coverage_from": coverage_from or (records[0]["date"] if records else ""),
        "coverage_to": coverage_to or (records[-1]["date"] if records else ""),
        "records": records,
    }
    path = cache_dir / f"{code}.json"
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_dedup(base: list, incoming: list) -> list:
    """Merge two sorted (oldest-first) lists, deduplicating by date."""
    seen = {r["date"] for r in base}
    merged = list(base)
    for r in incoming:
        if r["date"] not in seen:
            merged.append(r)
            seen.add(r["date"])
    merged.sort(key=lambda r: r["date"])
    return merged
