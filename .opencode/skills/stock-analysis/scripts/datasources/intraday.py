"""Intraday-specific East Money data sources.

Provides: market breadth, limit-up pool, turnover ranking,
concept board ranking, north-bound capital flow.
All use push2.eastmoney.com API with cookie-based auth.
"""

import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from .base import BaseDataSource, RateLimitConfig
from .utils import format_price, format_volume, format_amount, format_percent, to_yi
from .eastmoney import load_cookie

PUSH2_URL = "https://push2.eastmoney.com/api/qt/clist/get"
NORTH_BOUND_URL = "https://push2.eastmoney.com/api/qt/kamt.rt/get"

A_STOCK_FILTER = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23"
CONCEPT_FILTER = "m:90+t:3"
MARKET_OVERVIEW_UT = "fa5fd1943385f9554f5b7d918a9e"

A_STOCK_BASIC_FIELDS = "f2,f3,f4,f5,f6,f7,f8,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21"


class EastMoneyIntradayDataSource(BaseDataSource):
    """Intraday data fetcher for East Money push2 API."""

    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=15,
        min_interval=1.5,
        max_interval=3.0,
        retry_times=3,
    )

    def __init__(self, config: RateLimitConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def _get_push2_headers(self) -> dict:
        cookie = load_cookie("EASTMONEY_COOKIE")
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "connection": "keep-alive",
            "host": "push2.eastmoney.com",
            "referer": "https://quote.eastmoney.com/",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-site",
            "user-agent": self._get_random_ua(),
            "cookie": cookie,
        }

    def _get_headers(self) -> dict:
        return self._get_push2_headers()

    def _make_request(self, url: str) -> dict:
        try:
            resp = requests.get(url, headers=self._get_push2_headers(), timeout=30)
            return resp.json()
        except Exception:
            return {}

    def _classify_stock(self, code: str, market: int) -> str:
        c = str(code)
        if c.startswith("30"):
            return "创业板"
        elif c.startswith("688"):
            return "科创板"
        elif c.startswith("68"):
            return "科创板"
        elif c.startswith("8") and len(c) >= 4 and market == 0:
            return "北交所"
        elif c.startswith("4") and len(c) >= 6 and market == 0:
            return "北交所"
        elif c.startswith("6") and market == 1:
            return "沪市主板"
        elif (c.startswith("00") or c.startswith("30")) and market == 0:
            return "深市主板"
        else:
            return "其他"

    def _limit_threshold(self, board: str) -> float:
        if board == "北交所":
            return 29.5
        elif board in ("创业板", "科创板"):
            return 19.5
        else:
            return 9.5

    def _is_limit_up(self, change_pct: float, board: str) -> bool:
        thresh = self._limit_threshold(board)
        return change_pct >= thresh and change_pct <= (thresh + 1.0)

    def _is_limit_down(self, change_pct: float, board: str) -> bool:
        thresh = self._limit_threshold(board)
        return change_pct <= -thresh and change_pct >= -(thresh + 1.0)

    def fetch_market_breadth(self) -> dict:
        """Fetch market breadth: up/down/limit counts."""
        fs = A_STOCK_FILTER
        fields = "f2,f3,f12,f13,f14"
        ut = MARKET_OVERVIEW_UT
        url = f"{PUSH2_URL}?pn=1&pz=6000&po=0&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"

        try:
            data = self._request_with_retry(url)
        except Exception:
            return {"error": "fetch failed"}

        if not data or data.get("rc") != 0:
            return {"error": "api returned error", "rc": data.get("rc") if data else None}

        diff = data.get("data", {}).get("diff", [])
        if not diff:
            return {"error": "no data"}

        total = len(diff)
        up_count = 0
        down_count = 0
        flat_count = 0
        limit_up_count = 0
        limit_down_count = 0
        total_change = 0.0

        for item in diff:
            change = item.get("f3")
            if change is None or change == "-" or change == "":
                flat_count += 1
                continue
            try:
                change = float(change)
            except (ValueError, TypeError):
                flat_count += 1
                continue

            total_change += change
            code = str(item.get("f12", ""))
            market = item.get("f13", 0)
            board = self._classify_stock(code, market)

            if change > 0.001:
                up_count += 1
                if self._is_limit_up(change, board):
                    limit_up_count += 1
            elif change < -0.001:
                down_count += 1
                if self._is_limit_down(change, board):
                    limit_down_count += 1
            else:
                flat_count += 1

        avg_change = round(total_change / total, 2) if total > 0 else 0.0
        up_ratio = round(up_count / total * 100, 2) if total > 0 else 0.0

        return {
            "total": total,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "up_ratio": up_ratio,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "avg_change": avg_change,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _to_full_code(self, code: str, market: int) -> str:
        c = str(code)
        if market == 1:
            return f"sh{c}"
        elif market == 0:
            return f"sz{c}"
        return c

    def fetch_limit_up_pool(self, top: int = 200) -> list:
        """Fetch limit-up stock pool with basic market data."""
        fs = A_STOCK_FILTER
        fields = A_STOCK_BASIC_FIELDS
        ut = MARKET_OVERVIEW_UT
        url = f"{PUSH2_URL}?pn=1&pz=6000&po=0&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"

        try:
            data = self._request_with_retry(url)
        except Exception:
            return []

        if not data or data.get("rc") != 0:
            return []

        diff = data.get("data", {}).get("diff", [])
        limit_up_stocks = []

        for item in diff:
            change = item.get("f3")
            if change is None or change == "-" or change == "":
                continue
            try:
                change = float(change)
            except (ValueError, TypeError):
                continue

            code = str(item.get("f12", ""))
            market = item.get("f13", 0)
            board = self._classify_stock(code, market)

            if not self._is_limit_up(change, board):
                continue

            full_code = self._to_full_code(code, market)
            limit_up_stocks.append({
                "code": full_code,
                "name": item.get("f14", ""),
                "price": format_price(item.get("f2")),
                "change_pct": format_percent(item.get("f3")),
                "change_amt": format_price(item.get("f4")),
                "volume": format_volume(item.get("f5")),
                "amount": format_amount(item.get("f6")),
                "swing": format_percent(item.get("f7")),
                "turnover": format_percent(item.get("f8")),
                "volume_ratio": (
                    f"{float(item.get('f10', 0)):.2f}"
                    if item.get("f10") and item.get("f10") != "-"
                    else "-"
                ),
                "high": format_price(item.get("f15")),
                "low": format_price(item.get("f16")),
                "open": format_price(item.get("f17")),
                "yestclose": format_price(item.get("f18")),
                "total_mv": (
                    format_amount(float(item.get("f20", 0)) * 10000)
                    if item.get("f20") and item.get("f20") != "-"
                    else "-"
                ),
                "board": board,
            })

        limit_up_stocks.sort(
            key=lambda x: float(x["change_pct"].replace("%", "").replace("+", "")),
            reverse=True,
        )
        return limit_up_stocks[:top]

    def fetch_turnover_ranking(self, top: int = 100) -> list:
        """Fetch top N stocks by turnover (成交额)."""
        fs = A_STOCK_FILTER
        fields = A_STOCK_BASIC_FIELDS
        ut = MARKET_OVERVIEW_UT
        url = f"{PUSH2_URL}?pn=1&pz={top}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f6&fs={fs}&fields={fields}"

        try:
            data = self._request_with_retry(url)
        except Exception:
            return []

        if not data or data.get("rc") != 0:
            return []

        diff = data.get("data", {}).get("diff", [])
        results = []

        for item in diff:
            code = str(item.get("f12", ""))
            market = item.get("f13", 0)
            full_code = self._to_full_code(code, market)
            results.append({
                "code": full_code,
                "name": item.get("f14", ""),
                "price": format_price(item.get("f2")),
                "change_pct": format_percent(item.get("f3")),
                "amount": format_amount(item.get("f6")),
                "turnover": format_percent(item.get("f8")),
                "volume_ratio": (
                    f"{float(item.get('f10', 0)):.2f}"
                    if item.get("f10") and item.get("f10") != "-"
                    else "-"
                ),
                "swing": format_percent(item.get("f7")),
                "total_mv": (
                    format_amount(float(item.get("f20", 0)) * 10000)
                    if item.get("f20") and item.get("f20") != "-"
                    else "-"
                ),
            })

        return results

    def fetch_concept_ranking(self, top: int = 50) -> list:
        """Fetch concept board real-time ranking by change%."""
        fs = CONCEPT_FILTER
        fields = "f2,f3,f4,f8,f12,f14,f20,f104,f105,f128,f136,f62"
        ut = MARKET_OVERVIEW_UT
        url = f"{PUSH2_URL}?pn=1&pz={top}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"

        try:
            data = self._request_with_retry(url)
        except Exception:
            return []

        if not data or data.get("rc") != 0:
            return []

        diff = data.get("data", {}).get("diff", [])
        results = []

        for item in diff:
            results.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "change_pct": format_percent(item.get("f3")),
                "change_amt": format_price(item.get("f4")),
                "turnover": format_percent(item.get("f8")),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
                "lead_stock": item.get("f128", ""),
                "lead_change": item.get("f136", ""),
                "net_inflow": to_yi(item.get("f62") or 0),
                "total_mv": (
                    format_amount(float(item.get("f20", 0)))
                    if item.get("f20") and item.get("f20") != "-"
                    else "-"
                ),
            })

        return results

    def fetch_north_bound(self) -> dict:
        """Fetch north-bound capital flow (北向资金)."""
        params = {
            "ktype": "1",
            "pagesize": "1",
            "pageindex": "1",
            "ut": "fa5fd1943385f9554f5b7d918a9e",
            "fields1": "f2,f4,f6",
            "fields2": "f2,f4,f6",
        }
        url = f"{NORTH_BOUND_URL}?{urlencode(params)}"

        try:
            resp = requests.get(url, headers=self._get_push2_headers(), timeout=15)
            data = resp.json()
        except Exception:
            return {"error": "fetch failed", "total_net": "-"}

        if not data or data.get("rc") != 0:
            return {"error": "api error", "total_net": "-"}

        result_data = data.get("data", {})
        hgt = result_data.get("s2n", [{}])[-1] if result_data.get("s2n") else {}
        sgt = result_data.get("n2s", [{}])[-1] if result_data.get("n2s") else {}

        def _val(d, k):
            v = d.get(k)
            if v is None or v == "-" or v == "":
                return 0.0
            return float(v)

        hgt_buy = _val(hgt, "f2")
        hgt_sell = _val(hgt, "f4")
        hgt_net = _val(hgt, "f6")
        sgt_buy = _val(sgt, "f2")
        sgt_sell = _val(sgt, "f4")
        sgt_net = _val(sgt, "f6")
        total_net = hgt_net + sgt_net

        return {
            "hgt_buy": to_yi(hgt_buy * 10000),
            "hgt_sell": to_yi(hgt_sell * 10000),
            "hgt_net": to_yi(hgt_net * 10000),
            "sgt_buy": to_yi(sgt_buy * 10000),
            "sgt_sell": to_yi(sgt_sell * 10000),
            "sgt_net": to_yi(sgt_net * 10000),
            "total_net": to_yi(total_net * 10000),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "eastmoney",
        }

    def fetch_scan_stocks(self, top: int = 500) -> list:
        """Fetch stocks for Scan Pool: top N by change% with basic data.

        Filters: positive change, non-null price, non-ST (via fs filter).
        Returns list suitable for Scan Pool with NO technical indicators.
        """
        fs = A_STOCK_FILTER
        fields = A_STOCK_BASIC_FIELDS
        ut = MARKET_OVERVIEW_UT
        url = f"{PUSH2_URL}?pn=1&pz={top}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"

        try:
            data = self._request_with_retry(url)
        except Exception:
            return []

        if not data or data.get("rc") != 0:
            return []

        diff = data.get("data", {}).get("diff", [])
        results = []

        for item in diff:
            change = item.get("f3")
            if change is None or change == "-" or change == "":
                continue
            try:
                change = float(change)
            except (ValueError, TypeError):
                continue
            if change <= 0.001:
                continue

            price = item.get("f2")
            if price is None or price == "-" or price == "":
                continue

            code = str(item.get("f12", ""))
            market = item.get("f13", 0)
            full_code = self._to_full_code(code, market)
            results.append({
                "code": full_code,
                "name": item.get("f14", ""),
                "price": format_price(price),
                "change_pct": format_percent(item.get("f3")),
                "change_amt": format_price(item.get("f4")),
                "volume": format_volume(item.get("f5")),
                "amount": format_amount(item.get("f6")),
                "swing": format_percent(item.get("f7")),
                "turnover": format_percent(item.get("f8")),
                "volume_ratio": (
                    f"{float(item.get('f10', 0)):.2f}"
                    if item.get("f10") and item.get("f10") != "-"
                    else "-"
                ),
                "total_mv": (
                    format_amount(float(item.get("f20", 0)) * 10000)
                    if item.get("f20") and item.get("f20") != "-"
                    else "-"
                ),
            })

        return results
