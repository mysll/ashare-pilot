"""East Money data source for concept boards and concept stocks."""

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlencode

import requests

from ashare_pilot.http_settings import load_http_proxies
from ashare_pilot.themes.runtime import workspace_path

EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_CONCEPT_PAGE_SIZE = 50
EASTMONEY_MEMBER_PAGE_SIZE = 50
EASTMONEY_MEMBER_UT = "8dec03ba335b81bf4ebdf7b29ec27d15"
CONCEPT_FETCH_STATE_SCHEMA = "concept_fetch_state.v2"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]

COOKIE_FILE = workspace_path(".cookie")

_custom_cookie_file: Path | None = None


@dataclass(frozen=True)
class ConceptStocksFetchResult:
    """Explicit result for one concept's paginated member fetch."""

    status: Literal["complete", "partial", "failed"]
    stocks: list[dict[str, Any]]
    total: int | None
    next_page: int
    failed_page: int | None = None
    error: str | None = None


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

    def _request_with_retry(
        self,
        url: str,
        headers: dict,
        retries: int = 1,
        timeout: int = 30,
    ) -> dict | None:
        for attempt in range(retries):
            self._wait_for_rate_limit()
            self._check_rate_limit()
            try:
                proxies = load_http_proxies()
                kwargs: dict[str, Any] = {
                    "headers": headers,
                    "timeout": timeout,
                }
                if proxies is not None:
                    kwargs["proxies"] = proxies
                resp = requests.get(url, **kwargs)
                self._request_count += 1
                data = resp.json()
                return data
            except Exception:
                if attempt < retries - 1:
                    wait = 3 * (2 ** attempt) * random.uniform(0.7, 1.3)
                    self._log(
                        f"  Request failed (attempt {attempt+1}/{retries}), "
                        f"retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    return None
        return None

    def _fetch_page_with_retry(
        self,
        url: str,
        headers: dict,
        page_label: str = "",
    ) -> dict | None:
        """Fetch a single page. No retry — failure triggers checkpoint save and exit."""
        self._log(f"  Fetching page {page_label}...")
        data = self._request_with_retry(
            url,
            headers,
            retries=1,
        )
        if data and data.get("rc") == 0:
            return data
        if data:
            self._log(f"  Request failed: api_rc={data.get('rc')}")
        return None

    def fetch_concept_sectors(
        self,
        page_size: int = EASTMONEY_CONCEPT_PAGE_SIZE,
        resume: bool = True,
    ) -> list:
        """Fetch all concept sector list from East Money.

        Args:
            page_size: Number of concepts per page
            resume: If True, resume from last saved page on failure
        """
        fs = "m:90+t:3"
        ut = EASTMONEY_MEMBER_UT
        fields = (
            "f12,f13,f14,f2,f3,f4,f8,f20,f104,f105,f128,f136,f62,"
            "f184,f66,f69,f72,f75,f78,f81,f84,f87,f124,f204,f205,f206"
        )

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
        seen_codes = {
            str(item.get("code"))
            for item in results
            if isinstance(item, dict) and item.get("code")
        }

        while True:
            now = time.strftime("%H:%M:%S")
            if total:
                tp = (total + page_size - 1) // page_size
                print(f"  [{now}] Fetching page {page}/{tp}...", flush=True)
            else:
                print(f"  [{now}] Fetching page {page}...", flush=True)

            params = {
                "fid": "f62",
                "po": 1,
                "pz": page_size,
                "pn": page,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "ut": ut,
                "fs": fs,
                "fields": fields,
            }
            url = f"{EASTMONEY_LIST_URL}?{urlencode(params)}"
            data = self._fetch_page_with_retry(
                url,
                headers,
                page_label=str(page),
            )
            if not data or data.get("rc") != 0:
                if resume and state_file:
                    try:
                        state_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(state_file, "w", encoding="utf-8") as sf:
                            sf.write(json.dumps({
                                "schema_version": CONCEPT_FETCH_STATE_SCHEMA,
                                "next_page": page,
                                "total": total,
                                "results": results,
                            }, ensure_ascii=False, indent=2))
                    except Exception:
                        pass
                raise RuntimeError(
                    f"Concept board page {page} failed. "
                    f"{'Checkpoint saved for resume.' if resume and state_file else 'No checkpoint path configured.'}"
                )

            if total is None:
                total = data.get("data", {}).get("total", 0)
                total_pages = (total + page_size - 1) // page_size
                now = time.strftime("%H:%M:%S")
                print(f"  [{now}] Total concepts: {total}, fetching {total_pages} page(s)...", flush=True)

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                complete = total is not None and len(results) == total
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if not code or not name or code in seen_codes:
                    continue
                seen_codes.add(code)

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
                    "lead_stock": item.get("f128") or item.get("f204", ""),
                    "lead_stock_code": item.get("f136") or item.get("f205", ""),
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
                        sf.write(json.dumps({
                            "schema_version": CONCEPT_FETCH_STATE_SCHEMA,
                            "next_page": page + 1,
                            "total": total,
                            "results": results,
                        }, ensure_ascii=False, indent=2))
                except Exception:
                    pass

            if total is not None and len(results) == total:
                complete = True
                break
            if len(diff) < page_size:
                break

            page += 1

        if not complete:
            raise RuntimeError(
                "Concept board pagination incomplete: "
                f"{len(results)}/{total or '?'} unique boards."
            )

        # Clean up state file on successful completion
        if complete and resume and state_file and state_file.exists():
            try:
                state_file.unlink()
            except Exception:
                pass

        return results

    def fetch_concept_stocks(
        self,
        concept_code: str,
        page_size: int = EASTMONEY_MEMBER_PAGE_SIZE,
        *,
        start_page: int = 1,
        initial_stocks: list[dict[str, Any]] | None = None,
        known_total: int | None = None,
        on_page: Callable[[ConceptStocksFetchResult], None] | None = None,
        max_pages: int | None = None,
    ) -> ConceptStocksFetchResult:
        """Fetch stocks belonging to a specific concept sector.

        Args:
            concept_code: Concept sector code (e.g., "BK0493")
            page_size: Number of stocks per page
            start_page: First page to request when resuming.
            initial_stocks: Previously checkpointed, already de-duplicated members.
            known_total: Interface total captured by an earlier successful page.
            on_page: Called after every successful page with resumable state.
            max_pages: Maximum successful pages to fetch in this call. ``None``
                fetches through completion; ``1`` supports round-robin paging.
        """
        fs = f"b:{concept_code}"
        ut = EASTMONEY_MEMBER_UT
        fields = "f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f20,f21"

        results: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for stock in initial_stocks or []:
            code = stock.get("code") if isinstance(stock, dict) else None
            if isinstance(code, str) and code and code not in seen_codes:
                results.append(stock)
                seen_codes.add(code)
        page = max(1, int(start_page))
        total = int(known_total) if known_total is not None else None
        headers = self._get_push2_headers()
        pages_fetched = 0

        while True:
            params = {
                "fid": "f3",
                "po": 1,
                "pz": page_size,
                "pn": page,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "ut": ut,
                "fs": fs,
                "fields": fields,
            }
            url = f"{EASTMONEY_LIST_URL}?{urlencode(params)}"
            data = self._fetch_page_with_retry(
                url,
                headers,
                page_label=f"{concept_code}/p{page}",
            )
            if not data or data.get("rc") != 0:
                self._log(
                    f"\n  {concept_code} page {page} failed after retries. Cookie may have expired."
                )
                self._log("  Run: ashare-pilot market-data auth update-cookie")
                return ConceptStocksFetchResult(
                    status="partial" if results else "failed",
                    stocks=results,
                    total=total,
                    next_page=page,
                    failed_page=page,
                    error="request_failed",
                )

            payload = data.get("data")
            payload = payload if isinstance(payload, dict) else {}
            reported_total = payload.get("total")
            try:
                reported_total = int(reported_total)
            except (TypeError, ValueError):
                reported_total = None
            if reported_total is not None:
                if total is not None and reported_total != total:
                    return ConceptStocksFetchResult(
                        status="partial" if results else "failed",
                        stocks=results,
                        total=reported_total,
                        next_page=page,
                        failed_page=page,
                        error=f"total_changed:{total}->{reported_total}",
                    )
                total = reported_total

            diff = payload.get("diff", [])
            diff = diff if isinstance(diff, list) else []
            if not diff:
                if total == len(results):
                    return ConceptStocksFetchResult("complete", results, total, page)
                return ConceptStocksFetchResult(
                    status="partial" if results else "failed",
                    stocks=results,
                    total=total,
                    next_page=page,
                    failed_page=page,
                    error=f"incomplete_count:{len(results)}/{total}",
                )

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

                stock = {
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
                }
                if full_code not in seen_codes:
                    results.append(stock)
                    seen_codes.add(full_code)

            next_page = page + 1
            pages_fetched += 1
            page_result = ConceptStocksFetchResult(
                status="complete" if total is not None and len(results) == total else "partial",
                stocks=results,
                total=total,
                next_page=next_page,
            )
            if on_page:
                on_page(page_result)

            if total is not None and len(results) == total:
                return ConceptStocksFetchResult("complete", results, total, next_page)
            if total is not None and len(results) > total:
                return ConceptStocksFetchResult(
                    status="partial",
                    stocks=results,
                    total=total,
                    next_page=next_page,
                    failed_page=page,
                    error=f"count_exceeds_total:{len(results)}/{total}",
                )
            if max_pages is not None and pages_fetched >= max_pages:
                return page_result

            page = next_page


def _to_yi(val) -> str:
    if val is None or val == "-" or val == "":
        return "-"
    try:
        v = float(val)
        return f"{v / 100000000:.2f}"
    except (ValueError, TypeError):
        return "-"
