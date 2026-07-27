"""Tencent Finance data source for HK stocks and search."""

import json
from typing import Any

from ashare_pilot.http_settings import http_get
from .base import BaseDataSource, RateLimitConfig
from .utils import calc_price_precision, format_price


TENCENT_URL = "https://qt.gtimg.cn/q="
SEARCH_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/smartbox/search/get"


class TencentDataSource(BaseDataSource):
    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=40,
        min_interval=0.2,
        max_interval=0.5,
        retry_times=3,
    )

    def __init__(self, config: RateLimitConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://stockapp.finance.qq.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _make_request(self, url: str, encoding: str = "gbk") -> str:
        resp = http_get(url, headers=self._get_headers(), timeout=10)
        return resp.content.decode(encoding)

    def fetch_hk_quotes(self, codes: list) -> list:
        if not codes:
            return []
        tencent_codes = ",".join(f"r_{code}" for code in codes)
        url = f"{TENCENT_URL}{tencent_codes}&fmt=json"
        try:
            text = self._request_with_retry(url)
            data = json.loads(text)
        except Exception as e:
            return [{"code": c, "error": str(e)} for c in codes]
        results = []
        for code in codes:
            r_code = f"r_{code}"
            item = data.get(r_code)
            if not item or not isinstance(item, list) or len(item) < 38:
                results.append({"code": code, "error": "not supported"})
                continue
            name = item[1]
            price = item[3]
            yestclose = item[4]
            open_p = item[5]
            high = item[33]
            low = item[34]
            volume = item[36]
            amount = item[37]
            time_str = item[30]
            precision = calc_price_precision(open_p, yestclose, price, high, low)
            updown = float(price) - float(yestclose)
            percent = (updown / float(yestclose) * 100) if float(yestclose) != 0 else 0
            results.append(
                {
                    "code": code,
                    "name": name,
                    "price": format_price(price, precision),
                    "open": format_price(open_p, precision),
                    "yestclose": format_price(yestclose, precision),
                    "high": format_price(high, precision),
                    "low": format_price(low, precision),
                    "volume": format_price(volume, 0),
                    "amount": format_price(amount, 0),
                    "updown": f"{updown:+.{precision}f}",
                    "percent": f"{percent:+.2f}%",
                    "time": time_str,
                    "market": "HK",
                }
            )
        return results

    def search_stocks(self, keyword: str) -> list:
        if not keyword:
            return []
        url = f"{SEARCH_URL}?q={keyword}"
        headers = {
            "User-Agent": self._get_random_ua(),
        }
        try:
            resp = http_get(url, headers=headers, timeout=10)
            data = resp.json()
        except Exception as e:
            return [{"error": str(e)}]
        stocks = data.get("data", {}).get("stock", [])
        results = []
        for item in stocks:
            if len(item) >= 4:
                market = item[0].lower()
                code = item[1].lower()
                name = item[2]
                full_code = f"{market}{code}"
                market_label = {
                    "sz": "A",
                    "sh": "A",
                    "bj": "A",
                    "hk": "HK",
                    "us": "US",
                }.get(market, market)
                results.append(
                    {
                        "code": full_code,
                        "name": name,
                        "market": market_label,
                    }
                )
        return results
