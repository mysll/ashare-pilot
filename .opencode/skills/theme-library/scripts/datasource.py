"""East Money data source for concept boards and concept stocks."""

import json
import random
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]

EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

COOKIE_FILE = Path(__file__).parent.parent.parent.parent.parent / ".cookie"

_custom_cookie_file: Path | None = None


def set_cookie_file(path: str | Path) -> None:
    global _custom_cookie_file
    _custom_cookie_file = Path(path) if path else None


def load_cookie(key: str = "EASTMONEY_COOKIE") -> str:
    cookie_file = _custom_cookie_file or COOKIE_FILE
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


class EastMoneyConceptSource:
    """Data source for East Money concept boards and concept stocks."""

    def __init__(self, requests_per_minute: int = 20, min_interval: float = 1.0,
                 max_interval: float = 2.5, verbose: bool = False, state_dir: Path | None = None):
        self._last_request_time = 0.0
        self._request_count = 0
        self._minute_start = time.time()
        self._requests_per_minute = requests_per_minute
        self._min_interval = min_interval
        self._max_interval = max_interval
        self.verbose = verbose
        self._state_dir = state_dir

    def _log(self, msg: str):
        if self.verbose:
            print(msg, flush=True)

    def _get_random_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _get_push2_headers(self) -> dict:
        cookie = load_cookie()
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

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self._last_request_time
        wait_time = self._min_interval + random.uniform(0, self._max_interval - self._min_interval)
        if elapsed < wait_time:
            time.sleep(wait_time - elapsed)
        self._last_request_time = time.time()

    def _check_rate_limit(self):
        now = time.time()
        if now - self._minute_start >= 60:
            self._request_count = 0
            self._minute_start = now
        if self._request_count >= self._requests_per_minute:
            wait_seconds = 60 - (now - self._minute_start)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._request_count = 0
            self._minute_start = time.time()

    def _request_with_retry(self, url: str, headers: dict, retries: int = 1, timeout: int = 30) -> dict | None:
        for attempt in range(retries):
            self._wait_for_rate_limit()
            self._check_rate_limit()
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)
                self._request_count += 1
                data = resp.json()
                return data
            except Exception:
                if attempt < retries - 1:
                    wait = 3 * (2 ** attempt) * random.uniform(0.7, 1.3)
                    self._log(f"  Request failed (attempt {attempt+1}/{retries}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    return None
        return None

    def _fetch_page_with_retry(self, url: str, headers: dict, page_label: str = "") -> dict | None:
        """Fetch a single page. No retry — failure triggers checkpoint save and exit."""
        self._log(f"  Fetching page {page_label}...")
        data = self._request_with_retry(url, headers, retries=1)
        if data and data.get("rc") == 0:
            return data
        return None

    def fetch_concept_sectors(self, page_size: int = 100, resume: bool = True) -> list:
        """Fetch all concept sector list from East Money.

        Args:
            page_size: Number of concepts per page
            resume: If True, resume from last saved page on failure
        """
        fs = "m:90+t:3"
        ut = "fa5fd1947385f9554f5b7d918a9e"
        fields = "f12,f14,f2,f3,f4,f8,f20,f104,f105,f128,f136,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87"

        state_file = self._state_dir / "concepts_fetch_state.json" if self._state_dir else None

        # --- Resume from checkpoint ---
        results = []
        start_page = 1
        known_total = None

        if resume and state_file and state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as sf:
                    state = json.loads(sf.read())
                results = state.get("results", [])
                start_page = state.get("next_page", 1)
                known_total = state.get("total")
                if not self.verbose and known_total:
                    total_pages = (known_total + page_size - 1) // page_size
                    print(f"  Total concepts: {known_total}, fetching {total_pages} page(s)...", flush=True)
                if not self.verbose:
                    print(f"  Resuming from page {start_page} ({len(results)} concepts cached)...", flush=True)
            except Exception:
                pass

        page = start_page
        headers = self._get_push2_headers()
        total = known_total
        complete = False

        while True:
            now = time.strftime("%H:%M:%S")
            if total:
                tp = (total + page_size - 1) // page_size
                print(f"  [{now}] Fetching page {page}/{tp}...", flush=True)
            else:
                print(f"  [{now}] Fetching page {page}...", flush=True)

            url = f"{EASTMONEY_LIST_URL}?pn={page}&pz={page_size}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"
            data = self._fetch_page_with_retry(url, headers, page_label=str(page))
            if not data or data.get("rc") != 0:
                if resume and state_file:
                    try:
                        state_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(state_file, "w", encoding="utf-8") as sf:
                            sf.write(json.dumps({"next_page": page, "total": total, "results": results},
                                                  ensure_ascii=False, indent=2))
                    except Exception:
                        pass
                print(f"\n  Page {page} failed after retries. Cookie may have expired.", flush=True)
                print(f"  Run: python .opencode/skills/stock-analysis/scripts/refresh_cookie.py --refresh", flush=True)
                total_pages = (total + page_size - 1) // page_size if total else "?"
                print(f"  Partial data: {len(results)} concepts fetched (page {page}/{total_pages}).", flush=True)
                if resume and state_file:
                    print(f"  Checkpoint saved, next run will resume from page {page}.", flush=True)
                break

            if total is None:
                total = data.get("data", {}).get("total", 0)
                total_pages = (total + page_size - 1) // page_size
                now = time.strftime("%H:%M:%S")
                print(f"  [{now}] Total concepts: {total}, fetching {total_pages} page(s)...", flush=True)

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                complete = True
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name:
                    continue

                stock_count = item.get("f104")
                if stock_count is not None:
                    try:
                        stock_count = int(stock_count)
                    except (ValueError, TypeError):
                        stock_count = 0

                results.append({
                    "code": code,
                    "name": name,
                    "price": item.get("f2"),
                    "change_pct": item.get("f3"),
                    "change_amt": item.get("f4"),
                    "turnover": item.get("f8"),
                    "total_mv": item.get("f20"),
                    "stock_count": stock_count,
                    "up_count": item.get("f104"),
                    "down_count": item.get("f105"),
                    "lead_stock": item.get("f128", ""),
                    "lead_stock_code": item.get("f136", ""),
                    "net_inflow": _to_yi(item.get("f62") or 0),
                    "source": "eastmoney",
                })

            total_pages = (total + page_size - 1) // page_size
            now = time.strftime("%H:%M:%S")
            print(f"  [{now}] Page {page}/{total_pages} done ({len(results)} total)", flush=True)

            # Save checkpoint after each page
            if resume and state_file:
                try:
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(state_file, "w", encoding="utf-8") as sf:
                        sf.write(json.dumps({"next_page": page + 1, "total": total, "results": results},
                                              ensure_ascii=False, indent=2))
                except Exception:
                    pass

            if len(diff) < page_size:
                complete = True
                break

            page += 1
            headers = self._get_push2_headers()
            delay = random.uniform(4.0, 7.0) + page * 1.5
            now = time.strftime("%H:%M:%S")
            print(f"  [{now}] Waiting {delay:.1f}s before next page...", flush=True)
            time.sleep(delay)

        # Clean up state file on successful completion
        if complete and resume and state_file and state_file.exists():
            try:
                state_file.unlink()
            except Exception:
                pass

        return results

    def fetch_concept_stocks(self, concept_code: str, page_size: int = 200) -> list:
        """Fetch stocks belonging to a specific concept sector.

        Args:
            concept_code: Concept sector code (e.g., "BK0493")
            page_size: Number of stocks per page
        """
        fs = f"b:{concept_code}+f:!50"
        ut = "fa5fd1947385f9554f5b7d918a9e"
        fields = "f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f20,f21"

        results = []
        page = 1
        headers = self._get_push2_headers()

        while True:
            url = f"{EASTMONEY_LIST_URL}?pn={page}&pz={page_size}&po=1&np=1&ut={ut}&fltt=2&invt=2&fid=f3&fs={fs}&fields={fields}"
            data = self._fetch_page_with_retry(url, headers, page_label=f"{concept_code}/p{page}")
            if not data or data.get("rc") != 0:
                self._log(f"\n  {concept_code} page {page} failed after retries. Cookie may have expired.")
                self._log(f"  Run: python .opencode/skills/stock-analysis/scripts/refresh_cookie.py --refresh")
                break

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name:
                    continue

                market_code = item.get("f13", 0)
                if market_code == 1:
                    full_code = f"sh{code}"
                elif market_code == 0:
                    full_code = f"sz{code}"
                elif market_code == 2 or str(code).startswith("8") or str(code).startswith("4"):
                    full_code = f"bj{code}"
                else:
                    full_code = code

                total_mv = item.get("f20")
                if total_mv and total_mv != "-":
                    try:
                        total_mv = float(total_mv)
                    except (ValueError, TypeError):
                        total_mv = 0
                else:
                    total_mv = 0

                float_mv = item.get("f21")
                if float_mv and float_mv != "-":
                    try:
                        float_mv = float(float_mv)
                    except (ValueError, TypeError):
                        float_mv = 0
                else:
                    float_mv = 0

                results.append({
                    "code": full_code,
                    "name": name,
                    "price": item.get("f2"),
                    "change_pct": item.get("f3"),
                    "change_amt": item.get("f4"),
                    "volume": item.get("f5"),
                    "amount": item.get("f6"),
                    "swing": item.get("f7"),
                    "turnover": item.get("f8"),
                    "volume_ratio": item.get("f10"),
                    "high": item.get("f15"),
                    "low": item.get("f16"),
                    "open": item.get("f17"),
                    "yestclose": item.get("f18"),
                    "total_mv": total_mv,
                    "float_mv": float_mv,
                })

            if len(diff) < page_size:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.5))

        return results


def _to_yi(val) -> str:
    if val is None or val == "-" or val == "":
        return "-"
    try:
        v = float(val)
        return f"{v / 100000000:.2f}"
    except (ValueError, TypeError):
        return "-"
