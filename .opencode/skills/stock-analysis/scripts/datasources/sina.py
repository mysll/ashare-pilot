"""Sina Finance data source for A/US stocks and futures."""

import json
import re
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseDataSource, RateLimitConfig
from .kline_cache import load_cache, save_cache, merge_dedup, _fmt_to_date
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

    def _fetch_rs_amount(self, code: str) -> list | None:
        """Fetch float-share change history (流通股本, 万股) from StockService."""
        url = (
            "http://stock.finance.sina.com.cn/stock/api/jsonp.php"
            f"/stockapi/StockService.getAmountBySymbol?_=26&symbol={code}"
        )
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://finance.sina.com.cn/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            text = resp.text
            if "(" not in text or ")" not in text.rstrip(";"):
                return None
            json_str = text[text.find("(") + 1:text.rfind(")")]
            data = json.loads(json_str)
            if isinstance(data, list) and data:
                return data
            return None
        except Exception:
            return None

    def _enrich_records(
        self, records: list, rs_amount: list | None
    ) -> list:
        """Compute change/change_pct, amount(元→万元), turnover from rsAmount."""
        prev_close = None
        for r in records:
            close_val = float(r.get("close", 0))
            open_val = float(r.get("open", 0))
            high_val = float(r.get("high", 0))
            low_val = float(r.get("low", 0))
            volume_val = float(r.get("volume", 0))
            raw_amount = float(r.get("amount", 0))

            if prev_close is not None and prev_close != 0:
                change_val = round(close_val - prev_close, 2)
                change_pct_val = round(change_val / prev_close * 100, 2)
            else:
                change_val = 0
                change_pct_val = 0

            # amount: 元 → 万元 (matching Sohu format)
            amt_str = str(round(raw_amount / 10000, 2)) if raw_amount else ""

            # turnover: volume(股) / floatShares(股) × 100
            turnover_str = ""
            if rs_amount and volume_val:
                share_amt = None
                for sa in rs_amount:
                    if r.get("date", "") >= sa.get("date", ""):
                        share_amt = float(sa.get("amount", 0))
                if share_amt and share_amt > 0:
                    turnover_val = volume_val / (share_amt * 10000) * 100
                    turnover_str = str(round(turnover_val, 2))

            r.update({
                "open": str(open_val),
                "close": str(close_val),
                "high": str(high_val),
                "low": str(low_val),
                "volume": str(int(volume_val)) if volume_val else "0",
                "change": str(change_val),
                "change_pct": str(change_pct_val),
                "amount": amt_str,
                "turnover": turnover_str,
            })
            prev_close = close_val
        return records

    def _fetch_daily_php(self, code: str, start_date: str) -> list | None:
        """Fetch daily K-line from DAYK_URL_PHP (cn market)."""
        url = (
            "https://quotes.sina.cn/hq/api/openapi.php/"
            f"MarketCenterService.getDailyK?market=cn&symbol={code}"
            f"&start={start_date}&asc=1"
        )
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://finance.sina.com.cn/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            text = resp.text.strip()
            if text.startswith("/*"):
                text = text[text.find("(") + 1:text.rfind(")")]
            data = json.loads(text)
            records = data.get("result", {}).get("data", [])
            if isinstance(records, list) and records:
                # Map day → date
                for r in records:
                    r["date"] = r.pop("day", "")
                return records
            return None
        except Exception:
            return None

    def _fetch_daily_scale240(self, code: str, datalen: int) -> list | None:
        """Fallback: fetch daily K-line via scale=240 on CN_MarketDataService."""
        url = f"{SINA_KLINE_URL}?symbol={code}&scale=240&datalen={datalen}"
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://quotes.sina.cn/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
        except Exception:
            return None
        if not data or not isinstance(data, list):
            return None
        results = []
        for item in data:
            day = item.get("day", "")
            if not day:
                continue
            results.append({
                "date": day,
                "open": str(item.get("open", 0)),
                "close": str(item.get("close", 0)),
                "high": str(item.get("high", 0)),
                "low": str(item.get("low", 0)),
                "volume": str(item.get("volume", 0)),
                "amount": "",
            })
        return results if results else None

    def fetch_daily_history(
        self, code: str, range_str: str = "3m", use_cache: bool = True
    ) -> list | None:
        """Fetch daily K-line history in Sohu-compatible format.

        Primary:  DAYK_URL_PHP + StockService.getAmountBySymbol (has amount + turnover)
        Fallback: scale=240 on CN_MarketDataService (OHLCV only)

        Returns list of dicts with keys: date, open, close, high, low,
        change, change_pct, volume, amount, turnover.
        Returns None on failure.
        """
        if not re.match(r"^(sh|sz|bj)", code):
            return None

        now = datetime.now()
        range_days = {"1y": 365, "6m": 182, "3m": 90, "1m": 30, "1w": 7}
        days = range_days.get(range_str, 90)
        cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        start_date = (now - timedelta(days=days + 10)).strftime("%Y-%m-%d")

        # ── Cache check ──────────────────────────────────────
        if use_cache:
            cache_data = load_cache(code)
            if cache_data:
                cached = cache_data["records"]
                cov_to = cache_data.get("coverage_to", cached[-1]["date"])
                end_dashed = now.strftime("%Y-%m-%d")
                if cov_to >= end_dashed:
                    return [r for r in cached if r["date"] >= cutoff_date]

        results = None

        # ── Primary: DAYK_URL_PHP ─────────────────────────────
        raw = self._fetch_daily_php(code, start_date)
        if raw:
            rs = self._fetch_rs_amount(code)
            results = self._enrich_records(raw, rs)
            # Filter to cutoff
            results = [r for r in results if r["date"] >= cutoff_date]

        # ── Fallback: scale=240 ────────────────────────────────
        if not results:
            datalen = days + 20
            raw = self._fetch_daily_scale240(code, datalen)
            if raw:
                results = self._enrich_records(raw, None)
                results = [r for r in results if r["date"] >= cutoff_date]

        if not results:
            return None

        # ── Update cache ──────────────────────────────────────
        if use_cache:
            if cache_data:
                merged = merge_dedup(cache_data["records"], results)
            else:
                merged = results
            now_str = now.strftime("%Y-%m-%d")
            save_cache(code, merged,
                       coverage_from=merged[0]["date"],
                       coverage_to=now_str)

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
