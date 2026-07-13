"""Exchange-time helpers for intraday operation snapshots."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo


MARKET_TZ = ZoneInfo("Asia/Shanghai")
MORNING_OPEN = time(9, 30)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)


def now_market() -> datetime:
    return datetime.now(MARKET_TZ)


def parse_market_datetime(value: Any, trade_date: date | None = None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%H:%M:%S")
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%H:%M:%S":
                if trade_date is None:
                    return None
                parsed = datetime.combine(trade_date, parsed.time())
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=MARKET_TZ)
            return parsed.astimezone(MARKET_TZ)
        except ValueError:
            continue
    return None


def iso_market(value: datetime | None) -> str | None:
    return value.astimezone(MARKET_TZ).isoformat(timespec="seconds") if value else None


def session_bar_start(bar_end: datetime, scale_minutes: int = 5) -> datetime:
    """Sina labels intraday buckets by their end time."""
    return bar_end - timedelta(minutes=scale_minutes)


def is_trading_bar(bar_start: datetime, bar_end: datetime) -> bool:
    start = bar_start.timetz().replace(tzinfo=None)
    end = bar_end.timetz().replace(tzinfo=None)
    morning = start >= MORNING_OPEN and end <= MORNING_CLOSE
    afternoon = start >= AFTERNOON_OPEN and end <= AFTERNOON_CLOSE
    return morning or afternoon


def select_completed_bars(
    raw_bars: list[dict[str, Any]],
    snapshot_time: datetime,
    trade_date: date,
    scale_minutes: int = 5,
) -> list[dict[str, Any]]:
    by_end: dict[datetime, dict[str, Any]] = {}
    for raw in raw_bars:
        if not isinstance(raw, dict) or "error" in raw:
            continue
        bar_end = parse_market_datetime(raw.get("time"), trade_date)
        if bar_end is None or bar_end.date() != trade_date or bar_end > snapshot_time:
            continue
        bar_start = session_bar_start(bar_end, scale_minutes)
        if not is_trading_bar(bar_start, bar_end):
            continue
        normalized = dict(raw)
        normalized["bar_start"] = iso_market(bar_start)
        normalized["bar_end"] = iso_market(bar_end)
        normalized["is_complete"] = True
        by_end[bar_end] = normalized
    return [by_end[key] for key in sorted(by_end)]


def first_session_bar(completed: list[dict[str, Any]], trade_date: date) -> dict[str, Any] | None:
    expected_end = datetime.combine(trade_date, time(9, 35), MARKET_TZ)
    expected = iso_market(expected_end)
    return next((bar for bar in completed if bar.get("bar_end") == expected), None)


def snapshot_slot(snapshot_time: datetime) -> str:
    minute = snapshot_time.hour * 60 + snapshot_time.minute
    if minute < 9 * 60 + 35:
        return "EARLY"
    if minute < 9 * 60 + 40:
        return "09:35"
    if minute < 9 * 60 + 45:
        return "09:40"
    if minute < 10 * 60:
        return "09:45"
    return "LATE"
