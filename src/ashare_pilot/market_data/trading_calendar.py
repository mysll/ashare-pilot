"""A-share trading-session helpers backed by official annual closures."""

import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from ashare_pilot.market_data.runtime import workspace_path


def _calendar_config() -> dict:
    return _load_calendar(str(workspace_path("config", "trading-calendar.json")))


@lru_cache(maxsize=8)
def _load_calendar(path: str) -> dict:
    with open(path, encoding="utf-8") as calendar_file:
        return json.load(calendar_file)


def _closure_dates() -> frozenset[date]:
    closures = set()
    for year in _calendar_config().get("years", {}).values():
        for start_text, end_text in year.get("closures", []):
            current = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
            while current <= end:
                closures.add(current)
                current += timedelta(days=1)
    return frozenset(closures)


def calendar_year_known(day: date) -> bool:
    return str(day.year) in _calendar_config().get("years", {})


def is_trading_day(day: date) -> bool:
    """Return whether *day* is an A-share session.

    Unknown years fall back to weekdays so callers continue to work until the
    next annual exchange notice is added to the local calendar.
    """
    return day.weekday() < 5 and day not in _closure_dates()


def previous_trading_day(day: date, include_current: bool = False) -> date:
    current = day if include_current else day - timedelta(days=1)
    while not is_trading_day(current):
        current -= timedelta(days=1)
    return current


def _publish_cutoff() -> time:
    return time.fromisoformat(_calendar_config()["daily_bar_publish_cutoff"])


def _shanghai_now(now: datetime | None = None) -> datetime:
    timezone = ZoneInfo(_calendar_config()["timezone"])
    if now is None:
        return datetime.now(timezone)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone)
    return now.astimezone(timezone)


def expected_latest_bar(
    requested_end: date | str | None = None,
    now: datetime | None = None,
) -> date:
    """Return the latest daily bar expected for a request at *now*.

    Today's bar becomes expected only on a trading day after the configured
    publication cutoff. Historical end dates are rolled back to a real session.
    """
    current = _shanghai_now(now)
    today = current.date()
    if is_trading_day(today) and current.time().replace(tzinfo=None) >= _publish_cutoff():
        latest_available = today
    else:
        latest_available = previous_trading_day(today)

    if requested_end is None:
        end = today
    elif isinstance(requested_end, date):
        end = requested_end
    else:
        compact_end = requested_end.replace("-", "")
        end = datetime.strptime(compact_end, "%Y%m%d").date()

    return previous_trading_day(min(end, latest_available), include_current=True)
