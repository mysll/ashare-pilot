"""East Money data source for Dragon and Tiger List, Margin Trading, Money Flow, and all stocks."""

import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from ashare_pilot.http_settings import http_get
from ashare_pilot.market_data.runtime import workspace_path

from .base import BaseDataSource, RateLimitConfig
from .utils import format_price, format_volume, format_amount, format_percent, to_yi

LHB_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
RZYE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
MONEY_FLOW_URL = "https://push2.eastmoney.com/api/qt/clist/get"
STOCK_MONEY_FLOW_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f20,f21"
STOCK_MONEY_FLOW_FIELDS = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13"

# Custom cookie file path (can be set via --cookie argument)
_custom_cookie_file: Path | None = None


def set_cookie_file(path: str | Path) -> None:
    """Set custom cookie file path.

    Args:
        path: Path to cookie file (absolute or relative)
    """
    global _custom_cookie_file
    _custom_cookie_file = Path(path) if path else None


def load_cookie(key: str) -> str:
    """Load cookie value from .cookie file.

    Args:
        key: Cookie key name (e.g., 'EASTMONEY_COOKIE')

    Returns:
        Cookie value string, or empty string if not found
    """
    cookie_file = _custom_cookie_file or workspace_path(".cookie")
    if not cookie_file.exists():
        return ""
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line[len(f"{key}="):]
    except Exception:
        pass
    return ""


class EastMoneyDataSource(BaseDataSource):
    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=20,
        min_interval=1.0,
        max_interval=2.0,
        retry_times=5,
    )

    def __init__(self, config: RateLimitConfig = None):
        super().__init__(config or self.DEFAULT_CONFIG)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://data.eastmoney.com/",
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _make_request(self, url: str) -> dict:
        try:
            resp = http_get(url, headers=self._get_headers(), timeout=15)
            return resp.json()
        except Exception:
            return {}

    def fetch_lhb(
        self, date_str: str = None, page: int = 1, page_size: int = 50
    ) -> list:
        params = {
            "sortColumns": "TRADE_DATE,SECURITY_CODE",
            "sortTypes": "-1,-1",
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
        }
        if date_str:
            params["filter"] = f"(TRADE_DATE='{date_str} 00:00:00')"
        url = f"{LHB_URL}?{urlencode(params)}"
        try:
            data = self._request_with_retry(url)
        except Exception:
            return []
        if not data.get("success"):
            return []
        items = data.get("result", {}).get("data", [])
        results = []
        for item in items:
            results.append(
                {
                    "date": item.get("TRADE_DATE", "")[:10],
                    "code": item.get("SECURITY_CODE", ""),
                    "name": item.get("SECURITY_NAME_ABBR", ""),
                    "close": item.get("CLOSE_PRICE"),
                    "change_pct": item.get("CHANGE_RATE"),
                    "turnover_rate": item.get("TURNOVERRATE"),
                    "deal_ratio": item.get("DEAL_AMOUNT_RATIO"),
                    "net_buy": to_yi(item.get("BILLBOARD_NET_AMT")),
                    "buy_amt": to_yi(item.get("BILLBOARD_BUY_AMT")),
                    "sell_amt": to_yi(item.get("BILLBOARD_SELL_AMT")),
                    "buy_ratio": item.get("BUY_RATIO"),
                    "sell_ratio": item.get("SELL_RATIO"),
                    "abnormal": item.get("EXPLANATION", ""),
                    "reason": item.get("CHANGE_REASON", ""),
                    "market": item.get("MARKET", ""),
                }
            )
        return results

    def fetch_lhb_stock(self, code: str, date_str: str = None) -> dict | None:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        pure_code = code.replace("sh", "").replace("sz", "").replace("bj", "")
        params = {
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "pageSize": "10",
            "pageNumber": "1",
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(SECURITY_CODE='{pure_code}')",
        }
        url = f"{LHB_URL}?{urlencode(params)}"
        try:
            data = self._request_with_retry(url)
        except Exception:
            return None
        if not data or not data.get("success"):
            return None
        items = data.get("result", {}).get("data", []) if data.get("result") else []
        if not items:
            return None
        item = items[0]
        return {
            "date": item.get("TRADE_DATE", "")[:10],
            "code": item.get("SECURITY_CODE", ""),
            "name": item.get("SECURITY_NAME_ABBR", ""),
            "close": item.get("CLOSE_PRICE"),
            "change_pct": item.get("CHANGE_RATE"),
            "turnover_rate": item.get("TURNOVERRATE"),
            "deal_ratio": item.get("DEAL_AMOUNT_RATIO"),
            "net_buy": to_yi(item.get("BILLBOARD_NET_AMT")),
            "buy_amt": to_yi(item.get("BILLBOARD_BUY_AMT")),
            "sell_amt": to_yi(item.get("BILLBOARD_SELL_AMT")),
            "buy_ratio": item.get("BUY_RATIO"),
            "sell_ratio": item.get("SELL_RATIO"),
            "abnormal": item.get("EXPLANATION", ""),
            "market": item.get("MARKET", ""),
        }

    def fetch_rzye(self, top: int = 10) -> list:
        params = {
            "sortColumns": "DIM_DATE",
            "sortTypes": "-1",
            "pageSize": str(top),
            "pageNumber": "1",
            "reportName": "RPTA_WEB_RZRQ_LSSH",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
        }
        url = f"{RZYE_URL}?{urlencode(params)}"
        try:
            data = self._request_with_retry(url)
        except Exception:
            return []
        if not data.get("success"):
            return []
        items = data.get("result", {}).get("data", [])
        results = []
        market_map = {"001": "深市", "002": "北交所", "007": "沪市"}
        for item in items:
            scdm = str(item.get("SCDM", ""))
            results.append(
                {
                    "date": item.get("DIM_DATE", "")[:10],
                    "market_code": scdm,
                    "market": market_map.get(scdm, f"未知({scdm})"),
                    "rzye": to_yi(item.get("RZYE")),
                    "rzmre": to_yi(item.get("RZMRE")),
                    "rzche": to_yi(item.get("RZCHE")),
                    "rzjme": to_yi(item.get("RZJME")),
                    "rqyl": item.get("RQYL"),
                    "rqye": to_yi(item.get("RQYE")),
                    "rzrqye": to_yi(item.get("RZRQYE")),
                }
            )
        return results

    def fetch_all_stocks(self, page_size: int = 50) -> list:
        results = []
        page = 1
        # 限制 page_size 不超过 50
        page_size = min(page_size, 50)
        fs = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23"
        ut = "fa5fd1943c747385f9554f5b7d918a9e"
        headers = self._get_push2_headers()
        while True:
            url = f"{EASTMONEY_LIST_URL}?pn={page}&pz={page_size}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f12&fs={fs}&fields={EASTMONEY_FIELDS}"
            try:
                self._wait_for_rate_limit()
                self._check_rate_limit()
                resp = http_get(url, headers=headers, timeout=30)
                data = resp.json()
                self._request_count += 1
            except Exception:
                break
            if not data or data.get("rc") != 0:
                break
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break
            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name:
                    continue
                price = item.get("f2")
                if price is None or price == "-" or price == "":
                    continue
                if code.startswith("6"):
                    full_code = f"sh{code}"
                elif code.startswith("0") or code.startswith("3"):
                    full_code = f"sz{code}"
                elif code.startswith("8") or code.startswith("4"):
                    full_code = f"bj{code}"
                else:
                    full_code = code
                results.append(
                    {
                        "code": full_code,
                        "name": name,
                        "price": format_price(price),
                        "yestclose": format_price(item.get("f18")),
                        "updown": format_price(item.get("f4")),
                        "percent": format_percent(item.get("f3")),
                        "high": format_price(item.get("f15")),
                        "low": format_price(item.get("f16")),
                        "open": format_price(item.get("f17")),
                        "volume": format_volume(item.get("f5")),
                        "amount": format_amount(item.get("f6")),
                        "turnover": format_percent(item.get("f8")),
                        "volume_ratio": f"{float(item.get('f10', 0)): .2f}"
                        if item.get("f10") and item.get("f10") != "-"
                        else "-",
                        "swing": format_percent(item.get("f7")),
                        "total_mv": format_amount(float(item.get("f20", 0)) * 10000)
                        if item.get("f20")
                        else "-",
                        "float_mv": format_amount(float(item.get("f21", 0)) * 10000)
                        if item.get("f21")
                        else "-",
                        "market": "A",
                        "source": "eastmoney",
                    }
                )
            if len(diff) < page_size:
                break
            page += 1
            time.sleep(random.uniform(1, 3))
        return results

    def fetch_board_money_flow_by_field(
        self, field: str = "f174", board_type: str = "concept", top: int = 100,
    ) -> list:
        """Fetch board-level money flow by arbitrary field from East Money.

        Args:
            field: Sort field (f62=主力净流入, f174=unknown metric)
            board_type: 'concept' (t:3), 'industry' (t:2), or 'all' (s:4)
            top: Number of top results to return

        Returns sorted list of {code, name, value, source}.
        """
        board_map = {
            "concept": "m%3A90%2Bt%3A3",
            "industry": "m%3A90%2Bt%3A2",
            "all": "m%3A90%2Bs%3A4",
        }
        code_param = board_map.get(board_type, board_map["all"])
        url = f"https://data.eastmoney.com/dataapi/bkzj/getbkzj?key={field}&code={code_param}"
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://data.eastmoney.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            self._wait_for_rate_limit()
            self._check_rate_limit()
            resp = http_get(url, headers=headers, timeout=15)
            data = resp.json()
            self._request_count += 1
        except Exception:
            return []
        if not data or data.get("rc") != 0:
            return []
        diff = data.get("data", {}).get("diff", [])
        diff = sorted(diff, key=lambda x: x.get(field, 0) or 0, reverse=True)[:top]
        results = []
        for item in diff:
            val = item.get(field, 0)
            if val == "-" or val is None:
                val = 0
            results.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "value": to_yi(val),
                "field": field,
                "board_type": board_type,
                "source": "eastmoney",
            })
        return results

    def fetch_concept_money_flow(self, field: str = "f174", top: int = 100) -> list:
        """Fetch concept board money flow (概念板块资金流向)."""
        return self.fetch_board_money_flow_by_field(field=field, board_type="concept", top=top)

    def fetch_industry_money_flow_by_field(self, field: str = "f174", top: int = 100) -> list:
        """Fetch industry sector money flow (行业板块资金流向)."""
        return self.fetch_board_money_flow_by_field(field=field, board_type="industry", top=top)

    def fetch_industry_money_flow(self, top: int = 100) -> list:
        """Fetch industry money flow data from East Money.

        Returns industry-level capital flow data (主力净流入 f62, all boards).
        """
        headers = {
            "User-Agent": self._get_random_ua(),
            "Referer": "https://data.eastmoney.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bs%3A4"
        try:
            self._wait_for_rate_limit()
            self._check_rate_limit()
            resp = http_get(url, headers=headers, timeout=15)
            data = resp.json()
            self._request_count += 1
        except Exception:
            return []
        if not data or data.get("rc") != 0:
            return []
        diff = data.get("data", {}).get("diff", [])
        diff = sorted(diff, key=lambda x: x.get("f62", 0) or 0, reverse=True)[:top]
        results = []
        for item in diff:
            net_inflow = item.get("f62", 0)
            if net_inflow == "-" or net_inflow is None:
                net_inflow = 0
            results.append(
                {
                    "code": item.get("f12", ""),
                    "type": item.get("f13", 0),
                    "industry": item.get("f14", ""),
                    "net_inflow": to_yi(net_inflow),
                    "source": "eastmoney",
                }
            )
        return results

    def _get_stock_money_flow_headers(self) -> dict:
        """Headers for stock money flow API (sec-ch-ua must match user-agent)."""
        # sec-ch-ua 必须与 user-agent 版本号一致
        # 从 .cookie 文件读取 cookie
        # 注意：不要手动设置 accept-encoding，让 requests 自动处理 gzip 解压
        cookie = load_cookie("EASTMONEY_COOKIE")
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
            "connection": "keep-alive",
            "host": "push2.eastmoney.com",
            "referer": "https://data.eastmoney.com/zjlx/detail.html",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "cookie": cookie,
        }

    def _get_push2_headers(self) -> dict:
        """Headers for push2.eastmoney.com API (sec-ch-ua must match user-agent)."""
        # sec-ch-ua 必须与 user-agent 版本号一致
        # 注意：不要手动设置 accept-encoding，让 requests 自动处理 gzip 解压
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
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "cookie": cookie,
        }

    def fetch_stock_money_flow(
        self,
        page: int = 1,
        page_size: int = 50,
        sort_field: str = "f62",
        sort_desc: bool = True,
    ) -> list:
        """Fetch individual stock money flow data from East Money.

        Args:
            page: Page number (default 1)
            page_size: Number of stocks per page (default 50, max ~5000)
            sort_field: Field to sort by (default f62 = 主力净流入)
            sort_desc: Sort descending (default True)

        Returns stock-level capital flow data with:
            - f62: 主力净流入
            - f66: 超大单净流入
            - f72: 大单净流入
            - f78: 中单净流入
            - f84: 小单净流入
        """
        # fs: 股票筛选条件
        # m:0 = 深市, m:1 = 沪市
        # t:6=A股, t:13=创业板, t:80=科创板, t:2=主板, t:23=科创板注册制, t:7=创业板注册制, t:3=创业板注册制
        # f:!2 = 过滤掉ST股票
        fs = "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
        ut = "8dec03ba335b81bf4ebdf7b29ec27d15"

        params = {
            "cb": "jQuery_callback",
            "fid": sort_field,
            "po": "1" if sort_desc else "0",
            "pz": str(page_size),
            "pn": str(page),
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "ut": ut,
            "fs": fs,
            "fields": STOCK_MONEY_FLOW_FIELDS,
        }
        url = f"{STOCK_MONEY_FLOW_URL}?{urlencode(params)}"

        headers = self._get_stock_money_flow_headers()

        try:
            self._wait_for_rate_limit()
            self._check_rate_limit()
            resp = http_get(url, headers=headers, timeout=30)
            self._request_count += 1
            text = resp.text
        except Exception:
            return []

        # Parse JSONP response
        if not text.startswith("jQuery_callback"):
            return []
        json_str = text[len("jQuery_callback("):-2]  # Remove callback wrapper and trailing ");"
        try:
            data = eval(json_str)  # JSON is valid Python dict
        except Exception:
            return []

        if not data or data.get("rc") != 0:
            return []

        diff = data.get("data", {}).get("diff", [])
        results = []
        for item in diff:
            code = item.get("f12", "")
            name = item.get("f14", "")
            if not code:
                continue

            # Add market prefix
            market_code = item.get("f13", 0)
            if market_code == 1:
                full_code = f"sh{code}"
            elif market_code == 0:
                full_code = f"sz{code}"
            else:
                full_code = code

            # Parse numeric values
            def parse_val(key):
                val = item.get(key)
                if val == "-" or val is None:
                    return 0
                return float(val)

            results.append(
                {
                    "code": full_code,
                    "name": name,
                    "price": format_price(item.get("f2")),
                    "change_pct": format_percent(item.get("f3")),
                    "main_net_inflow": to_yi(parse_val("f62")),  # 主力净流入
                    "main_ratio": format_percent(parse_val("f184")),  # 主力净流入占比
                    # 分档资金流向
                    "super_large_net": to_yi(parse_val("f66")),  # 超大单净流入
                    "super_large_ratio": format_percent(parse_val("f69")),
                    "large_net": to_yi(parse_val("f72")),  # 大单净流入
                    "large_ratio": format_percent(parse_val("f75")),
                    "medium_net": to_yi(parse_val("f78")),  # 中单净流入
                    "medium_ratio": format_percent(parse_val("f81")),
                    "small_net": to_yi(parse_val("f84")),  # 小单净流入
                    "small_ratio": format_percent(parse_val("f87")),
                    "source": "eastmoney",
                }
            )
        return results
