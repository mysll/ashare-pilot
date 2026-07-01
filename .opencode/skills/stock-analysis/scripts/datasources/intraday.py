"""Intraday-specific East Money data sources.

Provides: market breadth, limit-up pool, turnover ranking,
concept board ranking, north-bound capital flow.
All use push2.eastmoney.com API with cookie-based auth.
"""

import json
import os
import random
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from .base import BaseDataSource, RateLimitConfig
from .utils import format_price, format_volume, format_amount, format_percent, to_yi
from .eastmoney import load_cookie

PUSH2_URL = "https://push2.eastmoney.com/api/qt/clist/get"
INDEX_URL = "https://push2.eastmoney.com/api/qt/stock/get"
NORTH_BOUND_URL = "https://push2.eastmoney.com/api/qt/kamt.rt/get"

A_STOCK_FILTER = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23"
CONCEPT_FILTER = "m:90+t:3"
MARKET_OVERVIEW_UT = "fa5fd1943385f9554f5b7d918a9e"
INDEX_UT = "fa5fd1943c7b386f172d6893dbfba10b"
SINA_LIST_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

INDEX_FIELDS = "f43,f46,f60,f113,f114,f115,f116"

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

    def _fetch_index_snapshot(self, secid: str) -> dict:
        """Fetch a single index snapshot from the qt/stock/get endpoint.

        Returns {price, yestclose, up, down, flat} partial dict,
        or None on failure.
        """
        url = f"{INDEX_URL}?ut={INDEX_UT}&fields={INDEX_FIELDS}&secid={secid}"
        try:
            resp = requests.get(url, headers=self._get_push2_headers(), timeout=10)
            data = resp.json()
        except Exception:
            return None

        if not data or data.get("rc") != 0:
            return None

        d = data.get("data", {})
        if not d:
            return None

        return {
            "price": d.get("f43"),
            "yestclose": d.get("f60"),
            "up": d.get("f113", 0) or 0,
            "down": d.get("f114", 0) or 0,
            "flat": d.get("f115", 0) or 0,
        }

    def fetch_market_breadth(self, all_stocks: list = None, cache_dir: str = None) -> dict:
        """Fetch market breadth from index snapshot API.

        Uses qt/stock/get for Shanghai (1.000001) and Shenzhen (0.399001)
        to get pre-computed up/down/flat counts. Limit-up/limit-down counts
        are derived from the cached all_stocks list (fetched once).
        """
        sh = self._fetch_index_snapshot("1.000001")
        sz = self._fetch_index_snapshot("0.399001")

        if not sh and not sz:
            return {"error": "both index snapshots failed"}

        up_count = (sh.get("up", 0) if sh else 0) + (sz.get("up", 0) if sz else 0)
        down_count = (sh.get("down", 0) if sh else 0) + (sz.get("down", 0) if sz else 0)
        flat_count = (sh.get("flat", 0) if sh else 0) + (sz.get("flat", 0) if sz else 0)
        total = up_count + down_count + flat_count

        up_ratio = round(up_count / total * 100, 2) if total > 0 else 0.0

        if all_stocks is None and cache_dir:
            all_stocks = self.fetch_all_astocks(cache_dir=cache_dir)

        limit_up = self.fetch_limit_up_pool(top=500, all_stocks=all_stocks)
        limit_up_count = len(limit_up)

        limit_down = self.fetch_limit_down_pool(top=500, all_stocks=all_stocks)
        limit_down_count = len(limit_down) if limit_down else 0

        return {
            "total": total,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "up_ratio": up_ratio,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "avg_change": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "index_snapshot",
            "partial": (sh is None or sz is None),
        }

    def _to_full_code(self, code: str, market: int) -> str:
        c = str(code)
        if market == 1:
            return f"sh{c}"
        elif market == 0:
            return f"sz{c}"
        return c

    def _format_stock_item(self, rec: dict, include_board: bool = False) -> dict:
        """Format a readable stock record into output dict with formatted strings."""
        code = rec.get("code", "")
        market = rec.get("market", 0)
        full_code = self._to_full_code(code, market)
        result = {
            "code": full_code,
            "name": rec.get("name", ""),
            "price": format_price(rec.get("price")),
            "change_pct": format_percent(rec.get("chg_pct")),
            "change_amt": format_price(rec.get("chg_amt")),
            "volume": format_volume(rec.get("volume")),
            "amount": format_amount(rec.get("amount")),
            "swing": format_percent(rec.get("swing")),
            "turnover": format_percent(rec.get("turnover")),
            "volume_ratio": (
                f"{float(rec.get('vol_ratio', 0)):.2f}"
                if rec.get("vol_ratio") and rec.get("vol_ratio") != "-"
                and str(rec.get("vol_ratio", "")).replace(".", "").replace("-", "").isdigit()
                else "-"
            ),
            "total_mv": (
                format_amount(float(rec.get("total_mv", 0)) * 10000)
                if rec.get("total_mv") and rec.get("total_mv") != "-"
                else "-"
            ),
        }
        if include_board:
            result["board"] = self._classify_stock(code, market)
        return result

    def _push2_to_stock_rec(self, item: dict) -> dict:
        """Convert a push2 API raw diff item to readable stock record."""
        return {
            "code": str(item.get("f12", "")),
            "market": item.get("f13", 0),
            "name": item.get("f14", ""),
            "price": item.get("f2"),
            "chg_pct": item.get("f3"),
            "chg_amt": item.get("f4"),
            "volume": item.get("f5"),
            "amount": item.get("f6"),
            "swing": item.get("f7"),
            "turnover": item.get("f8"),
            "vol_ratio": item.get("f10"),
            "high": item.get("f15"),
            "low": item.get("f16"),
            "open": item.get("f17"),
            "preclose": item.get("f18"),
            "total_mv": item.get("f20"),
            "float_mv": item.get("f21"),
        }

    @staticmethod
    def _sina_to_stock_rec(item: dict) -> dict:
        """Convert a Sina API raw item to readable stock record."""
        symbol = item.get("symbol", "")
        if symbol.startswith("sh"):
            code = symbol[2:]
            market = 1
        elif symbol.startswith("sz"):
            code = symbol[2:]
            market = 0
        elif symbol.startswith("bj"):
            code = symbol[2:]
            market = 0
        else:
            code = symbol
            market = 0

        def _f(key):
            v = item.get(key)
            if v is None or v == "" or v == "-":
                return 0.0
            try:
                return float(v)
            except (ValueError, TypeError):
                return 0.0

        return {
            "code": code,
            "market": market,
            "name": item.get("name", ""),
            "price": _f("trade"),
            "chg_pct": _f("changepercent"),
            "chg_amt": _f("pricechange"),
            "volume": int(_f("volume")),
            "amount": _f("amount"),
            "swing": _f("amplitude"),
            "turnover": _f("turnoverratio"),
            "vol_ratio": None,
            "high": _f("high"),
            "low": _f("low"),
            "open": _f("open"),
            "preclose": _f("settlement"),
            "total_mv": _f("mktcap"),
            "float_mv": _f("nmc"),
        }

    def fetch_all_astocks(self, cache_dir: str = None) -> list:
        """Fetch full A-stock list once, with file-based caching.

        Primary: Sina API pagination (reliable, ~55s for ~5500 stocks).
        Caches converted stock records to all_stocks_cache.json.

        Returns list of readable stock record dicts.
        """
        cache_path = None
        today = datetime.now().strftime("%Y-%m-%d")
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "all_stocks_cache.json")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    if cached.get("date") == today:
                        return cached.get("stocks", [])
                except (json.JSONDecodeError, KeyError):
                    pass

        all_stocks = self._fetch_all_sina_paginated()

        if cache_path and all_stocks:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "date": today,
                        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "stock_count": len(all_stocks),
                        "source": "sina",
                        "stocks": all_stocks,
                    }, f, ensure_ascii=False)
            except Exception:
                pass

        return all_stocks

    def _fetch_all_sina_paginated(self) -> list:
        """Fetch all A-stocks from Sina API with pagination.

        Sina caps at 100 per page. Uses 0.5–1.0s random delay between
        pages to avoid rate limiting. Returns list of stock record dicts.
        """
        PAGE_SIZE = 100
        all_stocks = []
        page = 1
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://finance.sina.com.cn/",
            "Accept": "text/html,application/xhtml+xml",
        }

        while True:
            url = f"{SINA_LIST_URL}?page={page}&num={PAGE_SIZE}&sort=symbol&asc=1&node=hs_a"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                data = resp.json()
            except Exception:
                break

            if not data or not isinstance(data, list) or len(data) == 0:
                break

            for item in data:
                rec = self._sina_to_stock_rec(item)
                if rec.get("name") and rec.get("price") and rec.get("price") != 0:
                    all_stocks.append(rec)

            if len(data) < PAGE_SIZE:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.0))

        return all_stocks

    def fetch_limit_up_pool(self, top: int = 200, all_stocks: list = None) -> list:
        """Fetch limit-up stock pool with formatted market data.

        If all_stocks is provided (stock records from cache), no API call.
        """
        if all_stocks is not None:
            records = all_stocks
        else:
            fs = A_STOCK_FILTER
            fields = A_STOCK_BASIC_FIELDS
            ut = MARKET_OVERVIEW_UT
            url = f"{PUSH2_URL}?pn=1&pz=6000&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"
            try:
                data = self._request_with_retry(url)
            except Exception:
                return []
            if not data or data.get("rc") != 0:
                return []
            records = [self._push2_to_stock_rec(item) for item in data.get("data", {}).get("diff", [])]

        limit_up_stocks = []
        for rec in records:
            chg = rec.get("chg_pct")
            if chg is None or chg == "-" or chg == "":
                continue
            try:
                chg = float(chg)
            except (ValueError, TypeError):
                continue

            board = self._classify_stock(rec.get("code", ""), rec.get("market", 0))

            if not self._is_limit_up(chg, board):
                continue

            limit_up_stocks.append(self._format_stock_item(rec, include_board=True))

        limit_up_stocks.sort(
            key=lambda x: float(x["change_pct"].replace("%", "").replace("+", "")),
            reverse=True,
        )
        return limit_up_stocks[:top]

    def fetch_limit_down_pool(self, top: int = 200, all_stocks: list = None) -> list:
        """Fetch limit-down stock pool with formatted market data.

        If all_stocks is provided (stock records from cache), no API call.
        """
        if all_stocks is not None:
            records = all_stocks
        else:
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
            records = [self._push2_to_stock_rec(item) for item in data.get("data", {}).get("diff", [])]

        limit_down_stocks = []
        for rec in records:
            chg = rec.get("chg_pct")
            if chg is None or chg == "-" or chg == "":
                continue
            try:
                chg = float(chg)
            except (ValueError, TypeError):
                continue

            board = self._classify_stock(rec.get("code", ""), rec.get("market", 0))

            if not self._is_limit_down(chg, board):
                continue

            limit_down_stocks.append(self._format_stock_item(rec, include_board=True))

        limit_down_stocks.sort(
            key=lambda x: float(x["change_pct"].replace("%", "").replace("+", "")),
        )
        return limit_down_stocks[:top]

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
            rec = self._push2_to_stock_rec(item)
            results.append(self._format_stock_item(rec))

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

    def fetch_scan_stocks(self, top: int = 500, all_stocks: list = None) -> list:
        """Fetch stocks for Scan Pool: top N by change% with basic data.

        Filters: positive change, non-null price.
        Returns list suitable for Scan Pool with NO technical indicators.

        If all_stocks is provided, no API call is made.
        """
        if all_stocks is not None:
            records = all_stocks
        else:
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
            records = [self._push2_to_stock_rec(item) for item in data.get("data", {}).get("diff", [])]

        results = []
        for rec in records:
            chg = rec.get("chg_pct")
            if chg is None or chg == "-" or chg == "":
                continue
            try:
                chg = float(chg)
            except (ValueError, TypeError):
                continue
            if chg <= 0.001:
                continue

            price = rec.get("price")
            if price is None or price == "-" or price == "" or float(price) == 0:
                continue

            results.append(self._format_stock_item(rec))

        if all_stocks is not None:
            results.sort(
                key=lambda x: float(x["change_pct"].replace("%", "").replace("+", "")),
                reverse=True,
            )
            results = results[:top]

        return results
