"""Sohu Finance data source for historical K-line data."""

import json
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseDataSource, RateLimitConfig
from .kline_cache import (
    cache_checked_recently,
    load_cache,
    save_cache,
    next_day,
    prev_day,
    merge_dedup,
    _date_to_fmt,
    _fmt_to_date,
)
from .utils import parse_range_days


SOHU_URL = "https://q.stock.sohu.com/hisHq"


class SohuDataSource(BaseDataSource):
    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=20,
        min_interval=0.5,
        max_interval=1.0,
        retry_times=5,
    )

    def __init__(self, config: RateLimitConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://q.stock.sohu.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _make_request(self, url: str) -> str:
        resp = requests.get(url, headers=self._get_headers(), timeout=15)
        return resp.content.decode("utf-8", errors="replace")

    def _to_sohu_code(self, stock_code: str) -> str | None:
        code = stock_code.lower().strip()
        if code.startswith("sh") or code.startswith("sz"):
            return f"cn_{code[2:]}"
        return None

    def _calc_start_date(self, range_str: str) -> datetime:
        return datetime.now() - timedelta(days=parse_range_days(range_str))

    def _parse_jsonp_response(self, raw: str) -> list:
        start = raw.find("(")
        end = raw.rfind(")")
        if start == -1 or end == -1:
            return []
        json_str = raw[start + 1 : end]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list) or len(data) == 0:
            return []
        hq = data[0].get("hq", [])
        results = []
        for row in hq:
            if len(row) < 8:
                continue
            results.append(
                {
                    "date": row[0],
                    "open": row[1],
                    "close": row[2],
                    "change": row[3],
                    "change_pct": row[4],
                    "low": row[5],
                    "high": row[6],
                    "volume": row[7],
                    "amount": row[8] if len(row) > 8 else "",
                    "turnover": row[9] if len(row) > 9 else "",
                }
            )
        results.reverse()
        return results

    def _fetch_raw(self, sohu_code: str, start: str, end: str) -> list | None:
        """Raw API call — no cache. start/end in YYYYMMDD.

        Returns list of records on success (may be empty), None on failure.
        """
        url = (
            f"{SOHU_URL}?code={sohu_code}"
            f"&start={start}&end={end}"
            f"&stat=1&order=D&period=d"
            f"&callback=historySearchHandler&rt=jsonp"
        )
        try:
            raw = self._request_with_retry(url)
            return self._parse_jsonp_response(raw)
        except Exception:
            return None

    def fetch_history(
        self, code: str, start: str = None, end: str = None, range_str: str = "3m",
        use_cache: bool = True,
    ) -> list:
        sohu_code = self._to_sohu_code(code)
        if not sohu_code:
            return []
        if not end:
            end = datetime.now().strftime("%Y%m%d")
        if not start:
            start_dt = self._calc_start_date(range_str)
            start = start_dt.strftime("%Y%m%d")

        # ── Cache check ──────────────────────────────────────
        if use_cache:
            cache_data = load_cache(code, source="sohu")
            if cache_data:
                cached = cache_data["records"]
                cov_from = cache_data["coverage_from"]
                stored_cov_to = cache_data["coverage_to"]
                # coverage_to must describe records actually present in the
                # cache.  Older versions advanced it to the requested end date
                # even when Sohu returned no rows, which could permanently hide
                # a delayed trading day behind a false cache hit.
                cov_to = min(stored_cov_to, cached[-1]["date"])
                start_dashed = _fmt_to_date(start)
                end_dashed = _fmt_to_date(end)

                # Fully covered by cache in both directions
                if cov_from <= start_dashed and cov_to >= end_dashed:
                    return [r for r in cached if start_dashed <= r["date"] <= end_dashed]

                # Partial coverage — fetch gaps
                merged = list(cached)
                new_from = cov_from
                new_to = cov_to
                checked_newer = False

                # Gap: newer data (coverage_to hasn't reached end)
                if (cov_to < end_dashed
                        and not cache_checked_recently(cache_data, end_dashed)):
                    gap_start = _date_to_fmt(next_day(cov_to))
                    new_recs = self._fetch_raw(sohu_code, gap_start, end)
                    if new_recs is not None:
                        checked_newer = True
                        if new_recs:
                            merged = merge_dedup(merged, new_recs)
                            new_to = max(new_to, new_recs[-1]["date"])

                # Gap: older data (coverage_from hasn't reached start)
                if cov_from > start_dashed:
                    gap_end = _date_to_fmt(prev_day(cov_from))
                    old_recs = self._fetch_raw(sohu_code, start, gap_end)
                    if old_recs is not None:
                        if old_recs:
                            merged = merge_dedup(old_recs, merged)
                            new_from = min(new_from, old_recs[0]["date"])

                if (new_from != cov_from or new_to != cov_to
                        or cov_to != stored_cov_to or checked_newer):
                    save_cache(code, merged, coverage_from=new_from,
                               coverage_to=new_to, source="sohu",
                               checked_at=(None if checked_newer
                                           else cache_data.get("checked_at")),
                               checked_to=(end_dashed if checked_newer
                                           else cache_data.get("checked_to")))
                return [r for r in merged if start_dashed <= r["date"] <= end_dashed]

        # ── No cache — fetch full range ──────────────────────
        records = self._fetch_raw(sohu_code, start, end)
        if records and use_cache:
            save_cache(code, records,
                       coverage_from=records[0]["date"],
                       coverage_to=records[-1]["date"], source="sohu",
                       checked_to=_fmt_to_date(end))
        return records
