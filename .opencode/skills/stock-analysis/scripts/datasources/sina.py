"""Sina Finance data source for A/US stocks and futures."""

import json
import re
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseDataSource, RateLimitConfig
from .utils import calc_price_precision, format_price, format_amount


SINA_URL = "https://hq.sinajs.cn/list="
SINA_KLINE_URL = (
    "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
)
SINA_LIST_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"


class SinaDataSource(BaseDataSource):
    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=80,
        min_interval=0.05,
        max_interval=0.2,
        retry_times=3,
    )

    def __init__(self, config: RateLimitConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://finance.sina.com.cn/",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _make_request(self, url: str, encoding: str = "gb18030") -> str:
        resp = requests.get(url, headers=self._get_headers(), timeout=10)
        try:
            return resp.content.decode(encoding)
        except UnicodeDecodeError:
            return resp.content.decode("utf-8", errors="replace")

    def _parse_a_stock(self, code: str, params: list) -> dict:
        if len(params) < 32:
            return {"code": code, "error": "insufficient data"}
        name = params[0]
        open_p = params[1]
        yestclose = params[2]
        price = (
            params[3]
            if float(params[3]) != 0
            else (params[6] if float(params[6]) != 0 else yestclose)
        )
        high = params[4]
        low = params[5]
        volume = params[8]
        amount = params[9]
        date = params[30]
        time_str = params[31]
        precision = calc_price_precision(open_p, yestclose, price, high, low)
        updown = float(price) - float(yestclose)
        percent = (updown / float(yestclose) * 100) if float(yestclose) != 0 else 0
        return {
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
            "time": f"{date} {time_str}",
            "market": "A",
        }

    def _parse_us_stock(self, code: str, params: list) -> dict:
        if len(params) < 27:
            return {"code": code, "error": "insufficient data"}
        name = params[0]
        price = params[1]
        open_p = params[5]
        high = params[6]
        low = params[7]
        yestclose = params[26]
        volume = params[10]
        time_str = params[3]
        if len(params) > 21 and float(params[21]) != 0:
            price = params[21]
        precision = calc_price_precision(open_p, yestclose, price, high, low)
        updown = float(price) - float(yestclose)
        percent = (updown / float(yestclose) * 100) if float(yestclose) != 0 else 0
        return {
            "code": code,
            "name": name,
            "price": format_price(price, precision),
            "open": format_price(open_p, precision),
            "yestclose": format_price(yestclose, precision),
            "high": format_price(high, precision),
            "low": format_price(low, precision),
            "volume": format_price(volume, 0),
            "updown": f"{updown:+.{precision}f}",
            "percent": f"{percent:+.2f}%",
            "time": time_str,
            "market": "US",
        }

    def _parse_future(self, code: str, params: list) -> dict:
        if len(params) < 16:
            return {"code": code, "error": "insufficient data"}
        is_index_future = bool(re.search(r"nf_(IC|IF|IH|IM|TF|TS|T\d+|TL)", code))
        if is_index_future and len(params) >= 49:
            name = params[49].rstrip('"')
            open_p = params[0]
            high = params[1]
            low = params[2]
            price = params[3]
            yestclose = params[13]
            volume = params[4]
        else:
            name = params[0]
            open_p = params[2]
            high = params[3]
            low = params[4]
            price = params[8]
            yestclose = params[10]
            volume = params[14]
        precision = calc_price_precision(open_p, yestclose, price, high, low)
        updown = float(price) - float(yestclose)
        percent = (updown / float(yestclose) * 100) if float(yestclose) != 0 else 0
        return {
            "code": code,
            "name": name,
            "price": format_price(price, precision),
            "open": format_price(open_p, precision),
            "yestclose": format_price(yestclose, precision),
            "high": format_price(high, precision),
            "low": format_price(low, precision),
            "volume": format_price(volume, 0),
            "updown": f"{updown:+.{precision}f}",
            "percent": f"{percent:+.2f}%",
            "market": "Future",
        }

    def _parse_oversea_future(self, code: str, params: list) -> dict:
        if len(params) < 10:
            return {"code": code, "error": "insufficient data"}
        price = params[0]
        name = params[13].rstrip('"')
        time_str = params[6]
        date = params[12]
        open_p = params[8]
        high = params[4]
        low = params[5]
        yestclose = params[7]
        raw_volume = params[14] if len(params) > 14 else "0"
        raw_volume = raw_volume.replace('"', "").replace(";", "").strip()
        volume = raw_volume if raw_volume else "0"
        precision = calc_price_precision(open_p, yestclose, price, high, low)
        updown = float(price) - float(yestclose)
        percent = (updown / float(yestclose) * 100) if float(yestclose) != 0 else 0
        return {
            "code": code,
            "name": name,
            "price": format_price(price, precision),
            "open": format_price(open_p, precision),
            "yestclose": format_price(yestclose, precision),
            "high": format_price(high, precision),
            "low": format_price(low, precision),
            "volume": volume,
            "updown": f"{updown:+.{precision}f}",
            "percent": f"{percent:+.2f}%",
            "time": f"{date} {time_str}",
            "market": "OverseaFuture",
        }

    def fetch_quotes(self, codes: list) -> list:
        if not codes:
            return []
        url = SINA_URL + ",".join(codes)
        try:
            text = self._request_with_retry(url)
        except Exception as e:
            return [{"code": c, "error": str(e)} for c in codes]
        results = []
        blocks = text.strip().split('";\n')
        for block in blocks:
            if not block or '="' not in block:
                continue
            code = block.split('="')[0].split("var hq_str_")[1]
            code = code.replace("$", ".")
            params_str = block.split('="')[1]
            params = params_str.split(",")
            if len(params) <= 1:
                results.append({"code": code, "error": "not supported"})
                continue
            if re.match(r"^(sh|sz|bj)", code):
                results.append(self._parse_a_stock(code, params))
            elif re.match(r"^usr_", code):
                results.append(self._parse_us_stock(code, params))
            elif re.match(r"^nf_", code):
                results.append(self._parse_future(code, params))
            elif re.match(r"^hf_", code):
                results.append(self._parse_oversea_future(code, params))
            else:
                results.append({"code": code, "error": "unknown type"})
        return results

    def fetch_intraday(self, code: str, scale: int = 5, days: int = 1) -> list:
        if not re.match(r"^(sh|sz|bj)", code):
            return [
                {"error": "intraday kline only supports A stocks (sh/sz/bj prefix)"}
            ]
        days = max(1, min(days, 5))
        bars_per_day = 240 // scale
        datalen = bars_per_day * days + 10
        cutoff_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        url = f"{SINA_KLINE_URL}?symbol={code}&scale={scale}&datalen={datalen}"
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://quotes.sina.cn/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
        except Exception as e:
            return [{"error": str(e)}]
        if not data or not isinstance(data, list):
            return [{"error": "no data returned"}]
        results = []
        for item in data:
            time_str = item.get("day", "")
            if time_str and time_str >= cutoff_date:
                results.append(
                    {
                        "time": time_str,
                        "open": float(item.get("open", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "close": float(item.get("close", 0)),
                        "volume": int(item.get("volume", 0)),
                        "amount": float(item.get("amount", 0)),
                        "ma_price5": item.get("ma_price5"),
                        "ma_volume5": item.get("ma_volume5"),
                    }
                )
        return results

    def fetch_all_stocks(self, page_size: int = 80) -> list:
        results = []
        page = 1
        while True:
            url = f"{SINA_LIST_URL}?page={page}&num={page_size}&sort=symbol&asc=1&node=hs_a"
            try:
                text = self._request_with_retry(url)
                data = json.loads(text)
            except Exception:
                break
            if not data or not isinstance(data, list):
                break
            for item in data:
                symbol = item.get("symbol", "")
                name = item.get("name", "")
                if not symbol or not name:
                    continue
                price = item.get("trade")
                if price == "" or price is None:
                    continue
                pe = item.get("per")
                pb = item.get("pb")
                mktcap = item.get("mktcap")
                nmc = item.get("nmc")
                results.append(
                    {
                        "code": symbol,
                        "name": name,
                        "price": format_price(price),
                        "yestclose": format_price(item.get("settlement")),
                        "updown": format_price(item.get("pricechange")),
                        "percent": f"{float(item.get('changepercent', 0)):+.2f}%",
                        "high": format_price(item.get("high")),
                        "low": format_price(item.get("low")),
                        "open": format_price(item.get("open")),
                        "volume": item.get("volume"),
                        "amount": item.get("amount"),
                        "turnover": f"{float(item.get('turnoverratio', 0)):.2f}%"
                        if item.get("turnoverratio")
                        else "-",
                        "volume_ratio": "-",
                        "swing": "-",
                        "pe": format_price(pe) if pe else "-",
                        "pb": format_price(pb) if pb else "-",
                        "total_mv": format_amount(float(mktcap) * 10000) if mktcap else "-",
                        "float_mv": format_amount(float(nmc) * 10000) if nmc else "-",
                        "market": "A",
                        "source": "sina",
                    }
                )
            if len(data) < page_size:
                break
            page += 1
        return results
