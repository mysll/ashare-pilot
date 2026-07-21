"""K-line data cache for historical data.

Caches fetched historical K-line records per source and stock as JSON files.
On subsequent fetches, only new data (gap between cache and today) is
requested from the API, then merged and written back.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".cache" / "kline"
RECENT_CHECK_TTL_SECONDS = 15 * 60


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


def _cache_path(code: str, cache_dir: Path, source: str = None) -> Path:
    """Return a source-scoped cache path, preserving legacy callers."""
    if source:
        return cache_dir / source / f"{code}.json"
    return cache_dir / f"{code}.json"


def load_cache(code: str, cache_dir: Path = None, source: str = None) -> dict | None:
    """Load cached K-line data for a stock.

    Returns dict with keys 'records' (list, oldest-first),
    'coverage_from' (str, YYYY-MM-DD), 'coverage_to' (str, YYYY-MM-DD),
    or None on miss/corruption.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    path = _cache_path(code, cache_dir, source)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        if not records:
            return None
        return {
            "records": records,
            "coverage_from": data.get(
                "data_from", data.get("coverage_from", records[0]["date"])
            ),
            "coverage_to": data.get(
                "data_to", data.get("coverage_to", records[-1]["date"])
            ),
            "checked_at": data.get("checked_at"),
            "checked_to": data.get("checked_to"),
        }
    except Exception:
        return None


def save_cache(code: str, records: list, coverage_from: str = None, coverage_to: str = None,
               cache_dir: Path = None, source: str = None, checked_at: str = None,
               checked_to: str = None) -> None:
    """Save K-line records to cache file."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    path = _cache_path(code, cache_dir, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    now_text = datetime.now().astimezone().isoformat()
    data_from = coverage_from or (records[0]["date"] if records else "")
    data_to = coverage_to or (records[-1]["date"] if records else "")
    cache = {
        "code": code,
        "source": source or "legacy",
        "updated_at": now_text,
        "data_from": data_from,
        "data_to": data_to,
        "coverage_from": data_from,
        "coverage_to": data_to,
        "checked_at": checked_at or now_text,
        "checked_to": checked_to or data_to,
        "records": records,
    }
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_checked_recently(
    cache_data: dict,
    requested_end: str,
    ttl_seconds: int = RECENT_CHECK_TTL_SECONDS,
    now: datetime = None,
) -> bool:
    """Return whether the requested upper bound was checked within the TTL."""
    checked_at = cache_data.get("checked_at")
    checked_to = cache_data.get("checked_to")
    if not checked_at or not checked_to or checked_to < requested_end:
        return False
    try:
        checked_time = datetime.fromisoformat(checked_at)
    except (TypeError, ValueError):
        return False
    if now is None:
        now = datetime.now(checked_time.tzinfo) if checked_time.tzinfo else datetime.now()
    elif checked_time.tzinfo and not now.tzinfo:
        now = now.replace(tzinfo=checked_time.tzinfo)
    return timedelta(0) <= now - checked_time <= timedelta(seconds=ttl_seconds)


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
