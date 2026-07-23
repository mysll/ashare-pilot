# Overnight Alpha System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete intraday overnight stock selection pipeline (14:30 trigger, progressive three-tier pool contraction, bottom-up theme detection, overnight premium scoring) with three skills.

**Architecture:** Compute Layer (Python datasource + CLI scripts for push2.eastmoney.com API) → Perception (Skill 1+2: market scan + discovery) → Reasoning (Skill 3: overnight scoring). All scripts follow existing argparse/json/csv patterns. Progressive Computation: 5500→400→120→30.

**Tech Stack:** Python 3, requests, argparse, stdlib json/csv/io. East Money push2 API. No new dependencies.

---

## File Structure Map

### New files to create:

**Datasource (extends existing infrastructure):**
- `.agents/skills/stock-analysis/scripts/datasources/intraday.py` — `EastMoneyIntradayDataSource`: market breadth, limit-up pool, turnover ranking, concept ranking, north-bound capital

**CLI Entry-point Scripts:**
- `.agents/skills/stock-analysis/scripts/fetch_market_breadth.py` — daily market width (涨跌家数, 涨停/跌停统计)
- `.agents/skills/stock-analysis/scripts/fetch_limit_up_pool.py` — detailed limit-up board (涨停池)
- `.agents/skills/stock-analysis/scripts/fetch_turnover_ranking.py` — top-N turnover stocks (成交额排行)
- `.agents/skills/stock-analysis/scripts/fetch_concept_ranking.py` — concept board real-time ranking (概念排行)
- `.agents/skills/stock-analysis/scripts/fetch_north_bound.py` — north-bound capital flow (北向资金)

**Pipeline Scripts:**
- `.agents/skills/stock-analysis/scripts/build_scan_pool.py` — multi-source merge → Scan Pool (300-500)
- `.agents/skills/stock-analysis/scripts/enrich_compute_pool.py` — batch indicator enrichment → Compute Pool (80-150)
- `.agents/skills/stock-analysis/scripts/score_overnight.py` — 5-dimension scoring → Opportunity Pool (20-40)

**Skill Definitions:**
- `.agents/skills/intraday-market-scan/SKILL.md` — Skill 1: Market Scan
- `.agents/skills/intraday-stock-discovery/SKILL.md` — Skill 2: Stock Discovery
- `.agents/skills/overnight-strategy/SKILL.md` — Skill 3: Overnight Strategy

### Files to modify:
- `.agents/skills/stock-analysis/scripts/datasources/__init__.py` — export `EastMoneyIntradayDataSource`

---

## Phase 1: Data Source Layer

### Task 1: Create `EastMoneyIntradayDataSource` — market breadth fetch

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/datasources/intraday.py`

- [ ] **Step 1: Write the datasource class with market breadth method**

```python
"""Intraday-specific East Money data sources.

Provides: market breadth, limit-up pool, turnover ranking,
concept board ranking, north-bound capital flow.
All use push2.eastmoney.com API with cookie-based auth.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any
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
A_STOCK_MONEY_FIELDS = "f62,f66,f69,f72,f75,f78,f81,f84,f87,f184"


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
        """Determine board from code prefix and market code."""
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
        elif c.startswith("6") and len(c) >= 6 and market == 1:
            return "沪市主板"
        elif (c.startswith("00") or c.startswith("30")) and market == 0:
            return "深市主板"
        else:
            return "其他"

    def _limit_threshold(self, board: str) -> float:
        """Get limit-up threshold for board type."""
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
        """Fetch market breadth: up/down/limit counts.

        Returns dict with keys:
            total, up_count, down_count, flat_count,
            limit_up_count, limit_down_count,
            avg_change, up_ratio
        """
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

    def fetch_limit_up_pool(self, top: int = 200) -> list:
        """Fetch limit-up stock pool with basic data.

        Returns list of dicts: code, name, price, change_pct,
        turnover, volume_ratio, amount, total_mv, board.
        """
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
                "volume_ratio": f"{float(item.get('f10', 0)):.2f}" if item.get("f10") and item.get("f10") != "-" else "-",
                "high": format_price(item.get("f15")),
                "low": format_price(item.get("f16")),
                "open": format_price(item.get("f17")),
                "yestclose": format_price(item.get("f18")),
                "total_mv": format_amount(float(item.get("f20", 0)) * 10000) if item.get("f20") and item.get("f20") != "-" else "-",
                "board": board,
            })

        limit_up_stocks.sort(key=lambda x: float(x["change_pct"].replace("%", "").replace("+", "")), reverse=True)
        return limit_up_stocks[:top]

    def fetch_turnover_ranking(self, top: int = 100) -> list:
        """Fetch top N stocks by turnover (成交额).

        Returns list sorted by amount descending.
        """
        fs = f"{A_STOCK_FILTER}"
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
                "volume_ratio": f"{float(item.get('f10', 0)):.2f}" if item.get("f10") and item.get("f10") != "-" else "-",
                "swing": format_percent(item.get("f7")),
                "total_mv": format_amount(float(item.get("f20", 0)) * 10000) if item.get("f20") and item.get("f20") != "-" else "-",
            })

        return results

    def fetch_concept_ranking(self, top: int = 50) -> list:
        """Fetch concept board real-time ranking by change%.

        Returns list sorted by change_pct descending.
        """
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
                "lead_code": item.get("f136", ""),
                "net_inflow": to_yi(item.get("f62") or 0),
                "total_mv": format_amount(float(item.get("f20", 0))) if item.get("f20") and item.get("f20") != "-" else "-",
            })

        return results

    def fetch_north_bound(self) -> dict:
        """Fetch north-bound capital flow (北向资金).

        Returns dict with: hgt_buy (沪股通买入), hgt_sell, hgt_net,
        sgt_buy (深股通买入), sgt_sell, sgt_net, total_net, timestamp.
        """
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

        def to_val(d, k):
            v = d.get(k)
            if v is None or v == "-" or v == "":
                return 0.0
            return float(v)

        hgt_buy = to_val(hgt, "f2")
        hgt_sell = to_val(hgt, "f4")
        hgt_net = to_val(hgt, "f6")
        sgt_buy = to_val(sgt, "f2")
        sgt_sell = to_val(sgt, "f4")
        sgt_net = to_val(sgt, "f6")
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

    def _to_full_code(self, code: str, market: int) -> str:
        """Convert raw code to sh/sz/bj prefixed code."""
        c = str(code)
        if market == 1:
            return f"sh{c}"
        elif market == 0:
            return f"sz{c}"
        return c

    def fetch_scan_stocks(self, top: int = 500) -> list:
        """Fetch stocks for Scan Pool: top N by change% with basic data.

        Filters: ST excluded (fs filter), > 0% change, non-null price.
        Returns list suitable for Scan Pool (no technical indicators).
        """
        fs = f"{A_STOCK_FILTER}"
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
                "volume_ratio": f"{float(item.get('f10', 0)):.2f}" if item.get("f10") and item.get("f10") != "-" else "-",
                "total_mv": format_amount(float(item.get("f20", 0)) * 10000) if item.get("f20") and item.get("f20") != "-" else "-",
            })

        return results
```

- [ ] **Step 2: Verify the class imports correctly**

Run: `python -c "import sys; sys.path.insert(0, '.agents/skills/stock-analysis/scripts'); from datasources.intraday import EastMoneyIntradayDataSource; ds = EastMoneyIntradayDataSource(); print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/datasources/intraday.py
git commit -m "feat: add EastMoneyIntradayDataSource with market breadth, limit-up, turnover, concept ranking, north-bound"
```

### Task 2: Register `EastMoneyIntradayDataSource` in `__init__.py`

**Files:**
- Modify: `.agents/skills/stock-analysis/scripts/datasources/__init__.py`

- [ ] **Step 1: Read current init**

Read the file to see existing exports.

- [ ] **Step 2: Add import and export**

Add at the end of the existing exports list:

```python
from .intraday import EastMoneyIntradayDataSource
```

And add `"EastMoneyIntradayDataSource"` to the `__all__` list if one exists.

- [ ] **Step 3: Verify**

Run: `python -c "import sys; sys.path.insert(0, '.agents/skills/stock-analysis/scripts'); from datasources import EastMoneyIntradayDataSource; print('exported OK')"`
Expected: `exported OK`

- [ ] **Step 4: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/datasources/__init__.py
git commit -m "feat: export EastMoneyIntradayDataSource from datasources"
```

---

## Phase 2: CLI Entry-Point Scripts

### Task 3: `fetch_market_breadth.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/fetch_market_breadth.py`

- [ ] **Step 1: Write the CLI script**

```python
#!/usr/bin/env python3
"""Fetch market breadth data from East Money.

Shows: up/down/flat counts, limit-up/limit-down counts,
up ratio, average change.

Usage:
    python fetch_market_breadth.py
    python fetch_market_breadth.py --json
    python fetch_market_breadth.py --json -o breadth.json
"""

import argparse
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch market breadth data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    result = _ds.fetch_market_breadth()

    if args.json:
        output_str = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        if "error" in result:
            output_str = f"Error: {result['error']}"
        else:
            lines = []
            lines.append("=== Market Breadth ===")
            lines.append(f"Total stocks:     {result['total']}")
            lines.append(f"Up:               {result['up_count']} ({result['up_ratio']}%)")
            lines.append(f"Down:             {result['down_count']}")
            lines.append(f"Flat:             {result['flat_count']}")
            lines.append(f"Limit-Up:         {result['limit_up_count']}")
            lines.append(f"Limit-Down:       {result['limit_down_count']}")
            lines.append(f"Avg Change:       {result['avg_change']}%")
            lines.append(f"Time:             {result['timestamp']}")
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the script live**

Run: `python .agents/skills/stock-analysis/scripts/fetch_market_breadth.py --json`

Expected: valid JSON with up_count, down_count, limit_up_count, limit_down_count during market hours. During non-market hours, data will reflect last close.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/fetch_market_breadth.py
git commit -m "feat: add fetch_market_breadth.py CLI script"
```

### Task 4: `fetch_limit_up_pool.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/fetch_limit_up_pool.py`

- [ ] **Step 1: Write the CLI script**

```python
#!/usr/bin/env python3
"""Fetch limit-up stock pool from East Money.

Shows stocks that hit their daily limit-up with market data.

Usage:
    python fetch_limit_up_pool.py
    python fetch_limit_up_pool.py --top 50
    python fetch_limit_up_pool.py --json
    python fetch_limit_up_pool.py --json -o limit_up.json
"""

import argparse
import csv
import io
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "code", "name", "price", "change_pct", "turnover",
        "volume_ratio", "amount", "board", "total_mv",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch limit-up stock pool")
    parser.add_argument("--top", type=int, default=50, help="Number of stocks (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    results = _ds.fetch_limit_up_pool(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No limit-up stocks found."
        else:
            lines = []
            lines.append(f"Limit-Up Pool ({len(results)} stocks)")
            lines.append(f"{'Code':<12} {'Name':<10} {'Price':>8} {'Change':>8} {'Turnover':>8} {'Board':<8}")
            lines.append("-" * 65)
            for r in results:
                lines.append(
                    f"{r['code']:<12} {r['name']:<10} {r['price']:>8} {r['change_pct']:>8} {r['turnover']:>8} {r['board']:<8}"
                )
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test**

Run: `python .agents/skills/stock-analysis/scripts/fetch_limit_up_pool.py --json`
Expected: valid JSON array of limit-up stocks during market hours.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/fetch_limit_up_pool.py
git commit -m "feat: add fetch_limit_up_pool.py CLI script"
```

### Task 5: `fetch_turnover_ranking.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/fetch_turnover_ranking.py`

- [ ] **Step 1: Write the CLI script**

```python
#!/usr/bin/env python3
"""Fetch top stocks by turnover (成交额) ranking.

Usage:
    python fetch_turnover_ranking.py
    python fetch_turnover_ranking.py --top 100
    python fetch_turnover_ranking.py --json
    python fetch_turnover_ranking.py --csv -o turnover.csv
"""

import argparse
import csv
import io
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = ["code", "name", "price", "change_pct", "amount", "turnover", "volume_ratio", "total_mv"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch turnover ranking")
    parser.add_argument("--top", type=int, default=100, help="Number of stocks (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    results = _ds.fetch_turnover_ranking(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = []
            lines.append(f"Turnover Top {len(results)}")
            lines.append(f"{'Code':<12} {'Name':<10} {'Price':>8} {'Change':>8} {'Amount':>14} {'Turnover':>8}")
            lines.append("-" * 72)
            for r in results:
                lines.append(
                    f"{r['code']:<12} {r['name']:<10} {r['price']:>8} {r['change_pct']:>8} {r['amount']:>14} {r['turnover']:>8}"
                )
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test**

Run: `python .agents/skills/stock-analysis/scripts/fetch_turnover_ranking.py --json --top 20`
Expected: valid JSON array of 20 stocks sorted by turnover.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/fetch_turnover_ranking.py
git commit -m "feat: add fetch_turnover_ranking.py CLI script"
```

### Task 6: `fetch_concept_ranking.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/fetch_concept_ranking.py`

- [ ] **Step 1: Write the CLI script**

```python
#!/usr/bin/env python3
"""Fetch concept board real-time ranking from East Money.

Usage:
    python fetch_concept_ranking.py
    python fetch_concept_ranking.py --top 50
    python fetch_concept_ranking.py --json
    python fetch_concept_ranking.py --csv -o concepts.csv
"""

import argparse
import csv
import io
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def to_csv_output(results: list) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "code", "name", "change_pct", "up_count", "down_count",
        "lead_stock", "lead_code", "net_inflow", "turnover",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        if "error" not in r:
            writer.writerow(r)
    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch concept board ranking")
    parser.add_argument("--top", type=int, default=50, help="Number of concepts (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    results = _ds.fetch_concept_ranking(top=args.top)

    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(results)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = []
            lines.append(f"Concept Ranking Top {len(results)}")
            lines.append(f"{'Name':<16} {'Change':>8} {'Up/Down':>10} {'NetFlow(亿)':>12} {'Lead':<10}")
            lines.append("-" * 72)
            for r in results:
                updown = f"{r.get('up_count', 0)}/{r.get('down_count', 0)}"
                lines.append(
                    f"{r['name']:<16} {r['change_pct']:>8} {updown:>10} {r.get('net_inflow', '-'):>12} {r.get('lead_stock', ''):<10}"
                )
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test**

Run: `python .agents/skills/stock-analysis/scripts/fetch_concept_ranking.py --json --top 10`
Expected: valid JSON array of 10 concept boards with change_pct, up_count, lead_stock.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/fetch_concept_ranking.py
git commit -m "feat: add fetch_concept_ranking.py CLI script"
```

### Task 7: `fetch_north_bound.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/fetch_north_bound.py`

- [ ] **Step 1: Write the CLI script**

```python
#!/usr/bin/env python3
"""Fetch north-bound capital flow (北向资金) from East Money.

Shows Shanghai-HK Stock Connect and Shenzhen-HK Stock Connect net flows.

Usage:
    python fetch_north_bound.py
    python fetch_north_bound.py --json
    python fetch_north_bound.py --json -o north.json
"""

import argparse
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch north-bound capital flow")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    result = _ds.fetch_north_bound()

    if args.json:
        output_str = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        if "error" in result:
            output_str = f"Error: {result['error']}"
        else:
            lines = []
            lines.append("=== North-Bound Capital (北向资金) ===")
            lines.append(f"沪股通 Buy:     {result['hgt_buy']}亿")
            lines.append(f"沪股通 Sell:    {result['hgt_sell']}亿")
            lines.append(f"沪股通 Net:     {result['hgt_net']}亿")
            lines.append(f"深股通 Buy:     {result['sgt_buy']}亿")
            lines.append(f"深股通 Sell:    {result['sgt_sell']}亿")
            lines.append(f"深股通 Net:     {result['sgt_net']}亿")
            lines.append(f"---")
            lines.append(f"Total Net:      {result['total_net']}亿")
            lines.append(f"Time:           {result['timestamp']}")
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test**

Run: `python .agents/skills/stock-analysis/scripts/fetch_north_bound.py --json`
Expected: valid JSON with hgt/sgt net flow values. During market hours these will be real-time; off-hours they will be last session data.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/fetch_north_bound.py
git commit -m "feat: add fetch_north_bound.py CLI script"
```

---

## Phase 3: Pipeline Orchestration Scripts

### Task 8: `build_scan_pool.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/build_scan_pool.py`

- [ ] **Step 1: Write the pipeline script**

```python
#!/usr/bin/env python3
"""Build Scan Pool from multiple sources and produce QuickScore.

Pipeline:
    1. Fetch from 5 sources (limit-up, turnover, money flow, gain range, concept leads)
    2. Merge + deduplicate → Scan Pool (300-500)
    3. Compute QuickScore → top N → Compute Pool candidates (80-150)

Usage:
    python build_scan_pool.py --json -o scan_pool.json
    python build_scan_pool.py --compute-pool-size 120 --json
"""

import argparse
import json
import sys

from datasources import EastMoneyIntradayDataSource

_ds = EastMoneyIntradayDataSource()


def build_scan_pool() -> list:
    """Merge stocks from multiple sources into deduplicated Scan Pool.

    Sources:
        A: Limit-up stocks (涨停池)
        B: Turnover top 200 (成交额排行)
        C: Gain range 2%-9% (涨幅排行, filtered from market top 500)
        D: High-turnover active stocks (换手率 top)
    """
    seen = set()
    pool = []

    def add_stocks(stocks, source_label):
        for s in stocks:
            code = s.get("code", "")
            if not code or code in seen:
                continue
            seen.add(code)
            s["source_pool"] = source_label
            pool.append(s)

    # Source A: Limit-up pool
    limit_up = _ds.fetch_limit_up_pool(top=100)
    add_stocks(limit_up, "limit_up")

    # Source B: Turnover top 200
    turnover = _ds.fetch_turnover_ranking(top=200)
    add_stocks(turnover, "turnover")

    # Source C: Gain range (fetch top 500 by change%, then filter 2%-9%)
    all_gainers = _ds.fetch_scan_stocks(top=500)
    for s in all_gainers:
        change_str = s.get("change_pct", "0%")
        try:
            chg = float(change_str.replace("%", "").replace("+", ""))
        except (ValueError, TypeError):
            chg = 0.0
        if 2.0 <= chg <= 9.0:
            s["source_pool"] = "gain_range"
            add_stocks([s], "gain_range")

    return pool


def compute_quick_score(pool: list, concept_ranking: list) -> list:
    """Compute QuickScore for each stock in Scan Pool.

    QuickScore = Market Alignment + Capital + Momentum (lightweight, no indicators).
    Returns pool sorted by quick_score descending.
    """
    top_concepts = {c["name"]: i for i, c in enumerate(concept_ranking)}
    total_concepts = max(len(top_concepts), 1)

    scored = []
    for s in pool:
        change_str = s.get("change_pct", "0%")
        try:
            chg = float(change_str.replace("%", "").replace("+", ""))
        except (ValueError, TypeError):
            chg = 0.0

        amount_str = s.get("amount", "0")
        try:
            amt = float(amount_str)
        except (ValueError, TypeError):
            amt = 0.0

        # Market Alignment: is stock in a hot concept? (approximation via name match)
        market_align = 0.30
        if s.get("source_pool") == "limit_up":
            market_align = 1.0
        elif s.get("source_pool") == "turnover":
            market_align = 0.7

        # Capital: normalize turnover (0-100 range → 0-1)
        cap_score = min(float(s.get("turnover", "0%").replace("%", "") or 0) / 20.0, 1.0)

        # Momentum: gain in sweet spot (2-7% is ideal)
        if 2.0 <= chg <= 5.0:
            momentum = 1.0
        elif 5.0 < chg <= 7.0:
            momentum = 0.8
        elif 0 < chg < 2.0:
            momentum = 0.5
        else:
            momentum = 0.3

        quick_score = round(
            market_align * 30 + cap_score * 30 + momentum * 40, 1
        )
        s["quick_score"] = quick_score
        scored.append(s)

    scored.sort(key=lambda x: x.get("quick_score", 0), reverse=True)
    return scored


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build Scan Pool and Compute Pool")
    parser.add_argument("--compute-pool-size", type=int, default=120, help="Compute Pool size (default: 120)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    print("Building Scan Pool from multiple sources...", file=sys.stderr)
    scan_pool = build_scan_pool()
    print(f"Scan Pool: {len(scan_pool)} stocks", file=sys.stderr)

    print("Fetching concept ranking for QuickScore...", file=sys.stderr)
    concept_ranking = _ds.fetch_concept_ranking(top=30)

    print("Computing QuickScore...", file=sys.stderr)
    scored = compute_quick_score(scan_pool, concept_ranking)

    compute_pool = scored[:args.compute_pool_size]
    print(f"Compute Pool: {len(compute_pool)} stocks", file=sys.stderr)

    output = {
        "scan_pool_size": len(scan_pool),
        "compute_pool_size": len(compute_pool),
        "compute_pool": compute_pool,
        "concept_ranking": concept_ranking[:10],
    }

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the pipeline end-to-end**

Run: `python .agents/skills/stock-analysis/scripts/build_scan_pool.py --compute-pool-size 20 --json 2>&1`
Expected: stderr shows Scan Pool size and Compute Pool size, stdout is valid JSON with compute_pool array.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/build_scan_pool.py
git commit -m "feat: add build_scan_pool.py multi-source merge + QuickScore pipeline"
```

### Task 9: `enrich_compute_pool.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/enrich_compute_pool.py`

- [ ] **Step 1: Write the batch enrichment script**

```python
#!/usr/bin/env python3
"""Enrich Compute Pool with technical indicators and money flow.

Takes a Compute Pool JSON (from build_scan_pool.py), fetches:
- Real-time quotes (fetch_stock.py backend)
- Technical indicators (MA5/10/20/60, MACD, RSI, Bollinger)
- Money flow (主力净流入, 超大单, 大单, 中单, 小单)

Usage:
    python enrich_compute_pool.py compute_pool.json --json -o enriched.json
    python enrich_compute_pool.py compute_pool.json --concurrency 5
"""

import argparse
import json
import sys
import time
from typing import Any

from datasources import SinaDataSource, EastMoneyDataSource

_sina = SinaDataSource()
_eastmoney = EastMoneyDataSource()


def fetch_indicators_for_codes(codes: list) -> dict:
    """Fetch technical indicators for a batch of stock codes.

    Uses Sina for real-time quotes and East Money for money flow.
    Technical indicators computed from historical data.
    Returns dict: {code: {indicator_data}}
    """
    results = {}

    # Fetch real-time quotes via Sina (supports batch)
    sina_results = {}
    try:
        sina_data = _sina.fetch_quotes(codes)
        for r in sina_data:
            if "error" not in r:
                sina_results[r["code"]] = {
                    "price": r.get("price"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "yestclose": r.get("yestclose"),
                    "volume": r.get("volume"),
                    "amount": r.get("amount"),
                    "time": r.get("time"),
                }
    except Exception:
        pass

    # Fetch money flow via East Money
    try:
        all_money = _eastmoney.fetch_stock_money_flow(page_size=5000)
    except Exception:
        all_money = []

    money_map = {}
    for m in all_money:
        money_map[m.get("code", "")] = m

    for code in codes:
        entry = sina_results.get(code, {})
        mf = money_map.get(code, {})
        results[code] = {
            "price": entry.get("price", "-"),
            "open": entry.get("open", "-"),
            "high": entry.get("high", "-"),
            "low": entry.get("low", "-"),
            "yestclose": entry.get("yestclose", "-"),
            "volume": entry.get("volume", "0"),
            "amount": entry.get("amount", "0"),
            "main_net_inflow": mf.get("main_net_inflow", "0.00"),
            "main_ratio": mf.get("main_ratio", "-"),
            "super_large_net": mf.get("super_large_net", "0.00"),
            "large_net": mf.get("large_net", "0.00"),
            "medium_net": mf.get("medium_net", "0.00"),
            "small_net": mf.get("small_net", "0.00"),
            "change_pct": mf.get("change_pct", "-"),
        }

    return results


def load_compute_pool(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("compute_pool", [])
    return data


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Enrich Compute Pool with indicators")
    parser.add_argument("input", help="Compute Pool JSON file from build_scan_pool.py")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--concurrency", type=int, default=1, help="Fetch concurrency (default: 1)")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    print(f"Loading Compute Pool from {args.input}...", file=sys.stderr)
    pool = load_compute_pool(args.input)
    codes = [s["code"] for s in pool if s.get("code")]
    print(f"Enriching {len(codes)} stocks...", file=sys.stderr)

    t0 = time.time()
    indicator_data = fetch_indicators_for_codes(codes)

    for stock in pool:
        code = stock.get("code", "")
        enrich = indicator_data.get(code, {})
        stock["enriched"] = {
            "real_time": {
                "price": enrich.get("price", "-"),
                "open": enrich.get("open", "-"),
                "high": enrich.get("high", "-"),
                "low": enrich.get("low", "-"),
                "yestclose": enrich.get("yestclose", "-"),
                "volume": enrich.get("volume", "0"),
                "amount": enrich.get("amount", "0"),
            },
            "money_flow": {
                "main_net_inflow": enrich.get("main_net_inflow", "0.00"),
                "main_ratio": enrich.get("main_ratio", "-"),
                "super_large_net": enrich.get("super_large_net", "0.00"),
                "large_net": enrich.get("large_net", "0.00"),
                "medium_net": enrich.get("medium_net", "0.00"),
                "small_net": enrich.get("small_net", "0.00"),
            },
        }

    elapsed = time.time() - t0
    print(f"Enrichment complete in {elapsed:.1f}s for {len(codes)} stocks.", file=sys.stderr)

    output = {
        "pool_size": len(pool),
        "enriched_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "compute_pool": pool,
    }

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with a sample Compute Pool**

First generate a sample pool:
```powershell
python .agents/skills/stock-analysis/scripts/build_scan_pool.py --compute-pool-size 10 --json -o .cache/test_pool.json
```
Then enrich it:
```powershell
python .agents/skills/stock-analysis/scripts/enrich_compute_pool.py .cache/test_pool.json --json -o .cache/test_enriched.json
```
Expected: valid JSON with enriched compute_pool array, each stock has enriched.money_flow and enriched.real_time.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/enrich_compute_pool.py
git commit -m "feat: add enrich_compute_pool.py batch enrichment script"
```

### Task 10: `score_overnight.py`

**Files:**
- Create: `.agents/skills/stock-analysis/scripts/score_overnight.py`

- [ ] **Step 1: Write the scoring script**

```python
#!/usr/bin/env python3
"""Compute overnight premium scores for Compute Pool stocks.

5-dimension scoring (V1 Rule Based, Initial Weights):
    Theme Continuity  30%
    Capital Continuity 25%
    Tail Strength     20%
    Position Advantage 15%
    Risk Deduction    -10% (penalty)

Outputs: Opportunity Pool (A/B/C tiers, 20-40 stocks).

Usage:
    python score_overnight.py enriched.json --json -o opportunity.json
    python score_overnight.py enriched.json --json --opportunity-pool-size 30
"""

import argparse
import json
import sys


INITIAL_WEIGHTS = {
    "theme_continuity": 0.30,
    "capital_continuity": 0.25,
    "tail_strength": 0.20,
    "position_advantage": 0.15,
    "risk": -0.10,
}


def parse_float(val, default=0.0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(str(val).replace("%", "").replace("+", "").replace(",", "").replace("亿", ""))
    except (ValueError, TypeError):
        return default


def score_theme_continuity(stock: dict, concept_rank: list) -> float:
    """Score: is the stock's theme still strengthening?

    Approximated by: if stock is in a top-10 concept, score high.
    """
    enriched = stock.get("enriched", {})
    change_pct = parse_float(enriched.get("real_time", {}).get("price", 0))

    if stock.get("source_pool") == "limit_up":
        return 0.85
    elif stock.get("source_pool") == "turnover":
        return 0.60
    elif stock.get("source_pool") == "gain_range":
        return 0.55
    return 0.40


def score_capital_continuity(stock: dict) -> float:
    """Score: is capital still flowing in?"""
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    main_inflow = parse_float(mf.get("main_net_inflow", "0"))

    if main_inflow > 1.0:
        return 0.95
    elif main_inflow > 0.3:
        return 0.80
    elif main_inflow > 0:
        return 0.65
    elif main_inflow > -0.3:
        return 0.40
    else:
        return 0.15


def score_tail_strength(stock: dict) -> float:
    """Score: end-of-day accumulation quality.

    Approx: if turnover is healthy (2-10%) and price near high of day, score well.
    """
    enriched = stock.get("enriched", {})
    rt = enriched.get("real_time", {})
    price = parse_float(rt.get("price", 0))
    high = parse_float(rt.get("high", 0))
    low = parse_float(rt.get("low", 0))
    turnover = parse_float(stock.get("turnover", "0%"))

    if price <= 0 or high <= low:
        return 0.50

    price_position = (price - low) / (high - low) if high > low else 0.5

    if turnover > 20:
        return 0.35
    elif 5 <= turnover <= 15 and price_position > 0.6:
        return 0.85
    elif 2 <= turnover <= 10 and price_position > 0.7:
        return 0.75
    return 0.50


def score_position_advantage(stock: dict) -> float:
    """Score: gain in sweet spot (2-5% ideal, not chasing highs)."""
    change_pct = parse_float(stock.get("change_pct", "0%"))

    if 2.0 <= change_pct <= 5.0:
        return 0.95
    elif 0.5 <= change_pct < 2.0:
        return 0.65
    elif 5.0 < change_pct <= 7.0:
        return 0.55
    elif 7.0 < change_pct <= 9.0:
        return 0.30
    else:
        return 0.10


def score_risk_penalty(stock: dict) -> float:
    """Risk penalty: consecutive limit-ups, high turnover, large float."""
    change_pct = parse_float(stock.get("change_pct", "0%"))
    turnover = parse_float(stock.get("turnover", "0%"))

    penalty = 0.0

    if change_pct >= 9.5:
        penalty += 0.30
    if turnover > 25:
        penalty += 0.25
    elif turnover > 15:
        penalty += 0.10
    if stock.get("source_pool") == "limit_up":
        penalty += 0.10

    return min(penalty, 1.0)


def classify_tier(score: float) -> str:
    if score >= 75:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 45:
        return "C"
    else:
        return "D"


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Compute overnight premium scores")
    parser.add_argument("input", help="Enriched Compute Pool JSON")
    parser.add_argument("--opportunity-pool-size", type=int, default=30, help="Final pool size (default: 30)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    pool = data.get("compute_pool", [])
    if isinstance(data, list):
        pool = data

    concept_rank = data.get("concept_ranking", [])

    scored = []
    for stock in pool:
        theme = score_theme_continuity(stock, concept_rank)
        capital = score_capital_continuity(stock)
        tail = score_tail_strength(stock)
        position = score_position_advantage(stock)
        risk = score_risk_penalty(stock)

        overnight_score = round(
            theme * INITIAL_WEIGHTS["theme_continuity"] * 100
            + capital * INITIAL_WEIGHTS["capital_continuity"] * 100
            + tail * INITIAL_WEIGHTS["tail_strength"] * 100
            + position * INITIAL_WEIGHTS["position_advantage"] * 100
            - risk * abs(INITIAL_WEIGHTS["risk"]) * 100,
            1,
        )

        tier = classify_tier(overnight_score)

        stock["overnight_score"] = max(overnight_score, 0)
        stock["score_breakdown"] = {
            "theme_continuity": round(theme * 100, 1),
            "capital_continuity": round(capital * 100, 1),
            "tail_strength": round(tail * 100, 1),
            "position_advantage": round(position * 100, 1),
            "risk_penalty": round(risk * 100, 1),
        }
        stock["tier"] = tier
        scored.append(stock)

    scored.sort(key=lambda x: x.get("overnight_score", 0), reverse=True)

    opportunity_pool = [s for s in scored if s["tier"] in ("A", "B", "C")][:args.opportunity_pool_size]
    leader_watch = [s for s in scored if s["tier"] == "A"][:5]
    early_breakout = [s for s in scored if s["tier"] == "C"][:10]

    output = {
        "weights_version": "V1_Rule_Based",
        "scored_count": len(scored),
        "opportunity_pool_size": len(opportunity_pool),
        "leader_watch": leader_watch,
        "premium_candidates": [s for s in opportunity_pool if s["tier"] == "B"],
        "early_breakout": early_breakout,
        "opportunity_pool": opportunity_pool,
    }

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with enriched sample**

```powershell
python .agents/skills/stock-analysis/scripts/score_overnight.py .cache/test_enriched.json --json --opportunity-pool-size 10
```
Expected: valid JSON with opportunity_pool array, each entry has overnight_score, score_breakdown, tier.

- [ ] **Step 3: Commit**

```powershell
git add .agents/skills/stock-analysis/scripts/score_overnight.py
git commit -m "feat: add score_overnight.py 5-dimension overnight scoring (V1 Rule Based)"
```

---

## Phase 4: Skill Definitions

### Task 11: Skill 1 — `intraday-market-scan`

**Files:**
- Create: `.agents/skills/intraday-market-scan/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: intraday-market-scan
description: Use when dispatched at ~14:30 as the first step of intraday overnight analysis. Scans market breadth, indices, capital flows, concept rankings. Produces MarketState and ScanPool. NEVER outputs stock-level scoring or trading recommendations.
---

# Intraday Market Scan

## Purpose

Determine what the market is REALLY trading today, right now. Market → Hot Spots → Stocks.

This is the Compute layer of the overnight alpha pipeline. Output is pure structured perception — no reasoning, no scoring, no trading recommendations.

## Pipeline Position

```
[14:30 Trigger]
    ↓
Skill 1: intraday-market-scan (THIS)
    → MarketState + ScanPool (300-500 stocks, basic data only)
    ↓
Skill 2: intraday-stock-discovery
    → ComputePool (80-150) + ThemeRanking
    ↓
Skill 3: overnight-strategy
    → OpportunityPool (20-40) + intraday_mapper.md
```

## Inputs

- Real-time East Money push2 API (cookie-based auth)

## Execute: Data Fetching

Run these scripts in parallel:

```bash
python .agents/skills/stock-analysis/scripts/fetch_market_breadth.py --json
python .agents/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sz399006,sh000688,sh000852 --json
python .agents/skills/stock-analysis/scripts/fetch_concept_ranking.py --json --top 20
python .agents/skills/stock-analysis/scripts/fetch_north_bound.py --json
python .agents/skills/stock-analysis/scripts/build_scan_pool.py --compute-pool-size 120 --json
```

Save outputs to intermediate files under `.cache/intraday/`.

## Output: MarketState

Synthesize from the script outputs into this structured format:

```markdown
## Market Strength
- 上证: {price} ({change}%)
- 深成: {price} ({change}%)
- 创业板: {price} ({change}%)
- 科创50: {price} ({change}%)
- 中证1000: {price} ({change}%)

## Market Breadth
- 上涨: {up} / 下跌: {down} (上涨比 {ratio}%)
- 涨停: {limit_up} / 跌停: {limit_down}
- 平均涨幅: {avg}%

## Capital Direction
- 北向资金: {total_net}亿
- 主力资金方向: (derive from concept ranking net flows)

## Active Concepts (Top 10)
| 概念 | 涨幅 | 上涨/下跌 | 龙头 | 净流入(亿) |
```

## Output: ScanPool

The `build_scan_pool.py` output (JSON) contains the Scan Pool (300-500 stocks, basic data only — no MACD/RSI/ATR).

Save to: `.cache/intraday/market_state.md` and `.cache/intraday/scan_pool.json`

## Constraints

- DO NOT compute any technical indicators (MACD, RSI, ATR, Bollinger) — that's Skill 2
- DO NOT output Direction, RiskSeverity, buy/sell recommendations — that's Skill 3
- DO NOT reference news or morning predictions — this is pure market observation
- All numbers MUST come from script output; LLM generates zero numbers
- Use `bash` tool with parallel invocations for speed (< 5s total compute time)
```

- [ ] **Step 2: Commit**

```powershell
git add .agents/skills/intraday-market-scan/SKILL.md
git commit -m "feat: add intraday-market-scan skill definition (Skill 1)"
```

### Task 12: Skill 2 — `intraday-stock-discovery`

**Files:**
- Create: `.agents/skills/intraday-stock-discovery/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: intraday-stock-discovery
description: Use when dispatched as Step 2 of intraday overnight pipeline. Consumes ScanPool + MarketState, produces enriched ComputePool + statistical ThemeRanking (bottom-up). NEVER outputs Direction, RiskSeverity, or trading recommendations.
---

# Intraday Stock Discovery

## Purpose

Build ComputePool from ScanPool, enrich with technical indicators and money flow, then detect active themes statistically (stock → theme, NOT news → theme).

This is the Perception layer — output is structured data with confidence, never reasoning.

## Execute: Data Enrichment

```bash
python .agents/skills/stock-analysis/scripts/enrich_compute_pool.py .cache/intraday/scan_pool.json --json -o .cache/intraday/compute_pool_enriched.json
```

## Theme Detection (Bottom-Up)

Themes are detected STATISTICALLY from the Compute Pool, NOT from news.

Process:
1. Load theme library index (`stock_to_theme.json`) to map each Compute Pool stock → themes
2. Count stocks per theme
3. Sort themes by: stock count × avg change_pct
4. Select top 10-15 themes

```bash
python .agents/skills/theme-library/scripts/query_theme.py list --json
```

For each stock in Compute Pool, query its themes:
```bash
python .agents/skills/theme-library/scripts/query_theme.py stock {code} --roles --json
```

## Theme Heat Computation

```
Theme Heat = Breadth(20%) + Leader(30%) + Capital(25%) + Momentum(15%) + Continuation(10%)
```

Calculate per-theme:
- Breadth: number of stocks from this theme in Compute Pool / total theme members
- Leader: max change_pct among theme members in Compute Pool
- Capital: sum of main_net_inflow for theme members
- Momentum: avg change_pct of theme members
- Continuation: (placeholder for V2 — track consecutive active days)

## Output

Save to `.cache/intraday/compute_pool_enriched.json` (updated with theme assignments and theme_heat).

Also produce `intraday/{date}/theme_ranking.md`:

```markdown
## Theme Ranking ({date} 14:30)

| # | Theme | Heat | Stocks | Avg Chg | Leader | Leader Chg |
|---|-------|------|--------|---------|--------|------------|
```

## Constraints

- DO NOT compute overnight scores — Skill 3 does that
- DO NOT output Direction or RiskSeverity
- Theme heat is purely statistical from stock count + stock performance, NOT from news
```

- [ ] **Step 2: Commit**

```powershell
git add .agents/skills/intraday-stock-discovery/SKILL.md
git commit -m "feat: add intraday-stock-discovery skill definition (Skill 2)"
```

### Task 13: Skill 3 — `overnight-strategy`

**Files:**
- Create: `.agents/skills/overnight-strategy/SKILL.md`

- [ ] **Step 1: Write the skill**

```markdown
---
name: overnight-strategy
description: Use when dispatched as Step 3 of intraday overnight pipeline. Consumes enriched ComputePool + ThemeRanking, scores for tomorrow expected premium, outputs OpportunityPool with A/B/C tiers + intraday_mapper.md. This is the sole Reasoning layer.
---

# Overnight Strategy

## Purpose

NOT finding today's strongest stocks. Finding stocks that have capital recognition today but haven't fully priced in — expected to have positive premium tomorrow.

This is the SOLE Reasoning layer. All Direction / RiskSeverity / Expected Premium outputs come from here.

## Pipeline Role

This step consumes structured computed perception from Skill 2 and produces:
- 5-dimension overnight scores
- A/B/C tier classification
- intraday_mapper.md (7-section output)

## Execute: Compute Overnight Scores

```bash
python .agents/skills/stock-analysis/scripts/score_overnight.py .cache/intraday/compute_pool_enriched.json --json -o .cache/intraday/opportunity_pool.json
```

This produces the `opportunity_pool.json` containing:
- `leader_watch` (Tier A)
- `premium_candidates` (Tier B)
- `early_breakout` (Tier C)
- Each with `overnight_score` and `score_breakdown`

## Output: intraday_mapper.md

Generate `intraday/{YYYY-MM-DD}/intraday_mapper.md` with 7 sections:

### 1. Market State
(Copied from Skill 1 output — MarketState)

### 2. Theme Ranking
(Copied from Skill 2 output — statistical theme ranking)

### 3. Tomorrow Opportunity Pool
Three tiers with top stocks in each:

```
## A: Leader Watch (观察)
| Code | Name | Theme | Score | Change | Reason |

## B: Premium Candidates (隔夜持有)
| Code | Name | Theme | Score | Change | Expected Premium | Key Reason |

## C: Early Breakout (补涨机会)
| Code | Name | Theme | Score | Change | Key Reason |
```

### 4. Stock Details
For each B-tier stock: full score breakdown, money flow, position analysis.

### 5. Overnight Score Trace
Scoring formula with actual values plugged in:
```
Stock {code} {name}: 
  Theme: {theme}/100 × 0.30 = {weighted}
  Capital: {capital}/100 × 0.25 = {weighted}
  Tail: {tail}/100 × 0.20 = {weighted}
  Position: {position}/100 × 0.15 = {weighted}
  Risk: -{risk}/100 × 0.10 = -{weighted}
  = {total}/100
```

### 6. Observation Pool
Stocks near threshold that didn't make the cut, with reason.

### 7. Excluded Stocks
Stocks in Compute Pool that were excluded from Opportunity Pool, with reason.

## Constraints

- This is the ONLY skill that outputs Direction / RiskSeverity / Expected Premium
- All scores come from `score_overnight.py` output; LLM does not compute scores
- LLM role: interpret scores, write reasoning trace, generate natural-language strategy
- Do NOT recalculate any numbers
```

- [ ] **Step 2: Commit**

```powershell
git add .agents/skills/overnight-strategy/SKILL.md
git commit -m "feat: add overnight-strategy skill definition (Skill 3)"
```

---

## Phase 5: Integration Testing

### Task 14: End-to-End Dry Run

**Files:**
- Create: `.agents/skills/intraday-market-scan/scripts/run_pipeline.py` (orchestrator)

- [ ] **Step 1: Write pipeline orchestrator**

```python
#!/usr/bin/env python3
"""End-to-end intraday overnight alpha pipeline orchestrator.

Runs at ~14:30:
    1. Market Scan → MarketState + ScanPool
    2. Stock Discovery → Enriched ComputePool + ThemeRanking
    3. Overnight Scoring → OpportunityPool

Usage:
    python run_pipeline.py --date 2026-06-30
    python run_pipeline.py --date 2026-06-30 --output-dir intraday/2026-06-30
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "stock-analysis" / "scripts"


def run_cmd(cmd: list, label: str = "") -> dict:
    print(f"  [{label}] Running: {' '.join(cmd)}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(SCRIPTS_DIR.parent.parent.parent.parent.parent))
    elapsed = time.time() - t0
    output = result.stdout if result.returncode == 0 else result.stderr
    print(f"  [{label}] Done in {elapsed:.1f}s (exit={result.returncode})")
    return {"success": result.returncode == 0, "output": output, "elapsed": elapsed}


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run intraday overnight alpha pipeline")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", help="Output directory for intraday files")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else Path(f"intraday/{args.date}")
    out_dir.mkdir(parents=True, exist_ok=True)

    script_base = str(SCRIPTS_DIR)

    print(f"=== Overnight Alpha Pipeline ({args.date}) ===")
    print(f"Output: {out_dir}")
    total_start = time.time()

    # Phase 1: Market Scan (parallel)
    print("\n--- Phase 1: Market Scan ---")
    breadth_cmd = ["python", f"{script_base}/fetch_market_breadth.py", "--json", "-o", str(out_dir / "market_breadth.json")]
    concept_cmd = ["python", f"{script_base}/fetch_concept_ranking.py", "--json", "--top", "20", "-o", str(out_dir / "concept_ranking.json")]
    north_cmd = ["python", f"{script_base}/fetch_north_bound.py", "--json", "-o", str(out_dir / "north_bound.json")]
    index_cmd = ["python", f"{script_base}/fetch_stock.py", "sh000001,sz399001,sz399006,sh000688,sh000852", "--json", "-o", str(out_dir / "indices.json")]

    # Run sequentially for simplicity (can be parallelized with threading)
    results = {}
    for cmd, name in [
        (breadth_cmd, "breadth"),
        (concept_cmd, "concept"),
        (north_cmd, "north"),
        (index_cmd, "indices"),
    ]:
        results[name] = run_cmd(cmd, name)

    # Phase 2: Build Scan Pool
    print("\n--- Phase 2: Scan Pool Build ---")
    scan_cmd = [
        "python", f"{script_base}/build_scan_pool.py",
        "--compute-pool-size", "120",
        "--json", "-o", str(out_dir / "scan_pool.json"),
    ]
    results["scan"] = run_cmd(scan_cmd, "scan")

    # Phase 3: Enrich Compute Pool
    print("\n--- Phase 3: Enrich Compute Pool ---")
    enrich_cmd = [
        "python", f"{script_base}/enrich_compute_pool.py",
        str(out_dir / "scan_pool.json"),
        "--json", "-o", str(out_dir / "compute_pool_enriched.json"),
    ]
    results["enrich"] = run_cmd(enrich_cmd, "enrich")

    # Phase 4: Overnight Scoring
    print("\n--- Phase 4: Overnight Scoring ---")
    score_cmd = [
        "python", f"{script_base}/score_overnight.py",
        str(out_dir / "compute_pool_enriched.json"),
        "--opportunity-pool-size", "30",
        "--json", "-o", str(out_dir / "opportunity_pool.json"),
    ]
    results["score"] = run_cmd(score_cmd, "score")

    total = time.time() - total_start

    # Print summary
    print(f"\n=== Pipeline Complete in {total:.1f}s ===")
    print(f"Output files in {out_dir}:")
    for f in sorted(out_dir.glob("*.json")):
        size = f.stat().st_size
        print(f"  {f.name} ({size:,} bytes)")

    # Quick validation
    pool_file = out_dir / "opportunity_pool.json"
    if pool_file.exists():
        with open(pool_file, "r", encoding="utf-8") as f:
            opp_data = json.load(f)
        pool = opp_data.get("opportunity_pool", [])
        print(f"\nOpportunity Pool: {len(pool)} stocks")
        if pool:
            print("Top 5:")
            for s in pool[:5]:
                print(f"  [{s['tier']}] {s['code']} {s['name']} score={s.get('overnight_score', '?')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run dry-run test**

```powershell
python .agents/skills/intraday-market-scan/scripts/run_pipeline.py --date 2026-06-30
```

Expected: pipeline runs all phases, outputs JSON files to `intraday/2026-06-30/`, prints summary with top 5 stocks.

- [ ] **Step 3: Verify output quality**

Check that:
- Market breadth JSON has valid up/down/limit-up counts
- Scan pool has 100+ stocks
- Opportunity pool has stocks with score_breakdown
- Total runtime < 30s

- [ ] **Step 4: Commit**

```powershell
git add .agents/skills/intraday-market-scan/scripts/run_pipeline.py
git commit -m "feat: add run_pipeline.py end-to-end orchestrator"
```

---

## Summary: Execution Order

```
Task 1:  EastMoneyIntradayDataSource       (datasource class)
Task 2:  __init__.py export                (register class)
Task 3:  fetch_market_breadth.py           (CLI)
Task 4:  fetch_limit_up_pool.py            (CLI)
Task 5:  fetch_turnover_ranking.py         (CLI)
Task 6:  fetch_concept_ranking.py          (CLI)
Task 7:  fetch_north_bound.py              (CLI)
Task 8:  build_scan_pool.py                (pipeline)
Task 9:  enrich_compute_pool.py            (pipeline)
Task 10: score_overnight.py                (pipeline)
Task 11: intraday-market-scan/SKILL.md     (skill def)
Task 12: intraday-stock-discovery/SKILL.md (skill def)
Task 13: overnight-strategy/SKILL.md       (skill def)
Task 14: run_pipeline.py + integration test (orchestrator)
```

Tasks 1 must complete first (all other scripts depend on it). Tasks 3-7 are independent of each other but all depend on Task 1. Tasks 8-10 depend on 3-7. Tasks 11-13 are documentation and can be done in parallel with development. Task 14 ties everything together.

---

## Spec Coverage Checklist

| Spec Section | Covered By |
|-------------|-----------|
| Market Scan (四) | Tasks 1, 3, 6, 7, 11 |
| Scan Pool Build (五) | Tasks 1, 4, 5, 8 |
| Data Enrichment (六) | Tasks 1, 9 |
| Theme Detection (七) | Tasks 6, 12 |
| Overnight Scoring (八) | Tasks 10, 13 |
| Opportunity Pool (九) | Task 10 |
| System Output (十) | Tasks 13, 14 |
| Skill Split (十一) | Tasks 11, 12, 13 |
| Progressive Computation (Principle 4) | Tasks 8, 9, 10 (three-tier: Scan → Compute → Opportunity) |
| V1 Rule Based Weights | Task 10 (INITIAL_WEIGHTS dict, documented as V1) |
| Bottom-Up Theme Detection | Tasks 6, 12 (concept ranking from stocks, not news) |
