"""Sohu Finance data source for historical K-line data."""

import json
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseDataSource, RateLimitConfig


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
        now = datetime.now()
        if range_str == "1y":
            return now - timedelta(days=365)
        elif range_str == "6m":
            return now - timedelta(days=182)
        elif range_str == "1m":
            return now - timedelta(days=30)
        elif range_str == "1w":
            return now - timedelta(days=7)
        else:
            return now - timedelta(days=90)

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

    def fetch_history(
        self, code: str, start: str = None, end: str = None, range_str: str = "3m"
    ) -> list:
        sohu_code = self._to_sohu_code(code)
        if not sohu_code:
            return []
        if not end:
            end = datetime.now().strftime("%Y%m%d")
        if not start:
            start_dt = self._calc_start_date(range_str)
            start = start_dt.strftime("%Y%m%d")
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
            return []