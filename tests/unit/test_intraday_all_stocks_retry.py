"""Sina all-stock pagination retry and partial-cache contracts."""

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ashare_pilot.market_data._datasources.base import RateLimitConfig
from ashare_pilot.market_data._datasources.intraday import (
    AllStocksFetchResult,
    EastMoneyIntradayDataSource,
)


def sina_row(index: int) -> dict:
    return {
        "symbol": f"sh6{index:05d}",
        "name": f"样本{index}",
        "trade": "10.00",
        "changepercent": "1.00",
        "pricechange": "0.10",
        "volume": "100",
        "amount": "1000",
        "amplitude": "1",
        "turnoverratio": "2",
        "high": "10.10",
        "low": "9.90",
        "open": "10.00",
        "settlement": "9.90",
        "mktcap": "10",
        "nmc": "8",
    }


class Response:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def source_with_retries(retry_times: int = 3) -> EastMoneyIntradayDataSource:
    return EastMoneyIntradayDataSource(
        RateLimitConfig(
            requests_per_minute=80,
            min_interval=0,
            max_interval=0,
            retry_times=retry_times,
            retry_backoff=2,
        )
    )


def test_failed_page_retries_in_place_with_increasing_delay(monkeypatch):
    source = source_with_retries(3)
    calls = []
    page_two_attempts = 0

    def fake_get(url, **_kwargs):
        nonlocal page_two_attempts
        page = int(parse_qs(urlparse(url).query)["page"][0])
        calls.append(page)
        if page == 1:
            return Response([sina_row(i) for i in range(100)])
        page_two_attempts += 1
        if page_two_attempts < 3:
            return Response(ValueError("temporary"))
        return Response([sina_row(100)])

    sleeps = []
    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.http_get",
        fake_get,
    )
    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.random.uniform",
        lambda lower, _upper: lower,
    )
    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.time.sleep",
        sleeps.append,
    )

    result = source._fetch_all_sina_paginated_result()

    assert result.status == "complete"
    assert len(result.stocks) == 101
    assert calls == [1, 2, 2, 2]
    retry_delays = sleeps[-2:]
    assert retry_delays[0] > 0
    assert retry_delays[1] > retry_delays[0]


def test_exhausted_retries_write_explicit_partial_cache(monkeypatch, tmp_path: Path):
    source = source_with_retries(2)

    def fake_get(url, **_kwargs):
        page = int(parse_qs(urlparse(url).query)["page"][0])
        if page == 1:
            return Response([sina_row(i) for i in range(100)])
        return Response(ValueError("limited"))

    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.http_get",
        fake_get,
    )
    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.time.sleep",
        lambda _seconds: None,
    )

    stocks = source.fetch_all_astocks(
        cache_dir=str(tmp_path),
        resume_partial=True,
    )
    cached = json.loads(
        (tmp_path / "all_stocks_cache.json").read_text(encoding="utf-8")
    )

    assert len(stocks) == 100
    assert cached["schema_version"] == "intraday_all_stocks_cache.v2"
    assert cached["status"] == "partial"
    assert cached["pages_fetched"] == 1
    assert cached["failed_page"] == cached["next_page"] == 2
    assert cached["stock_count"] == 100
    assert cached["error"]


def test_empty_page_is_retried_and_never_marks_cache_complete(
    monkeypatch, tmp_path: Path
):
    source = source_with_retries(3)
    calls = 0

    def fake_get(_url, **_kwargs):
        nonlocal calls
        calls += 1
        return Response([])

    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.http_get",
        fake_get,
    )
    monkeypatch.setattr(
        "ashare_pilot.market_data._datasources.intraday.time.sleep",
        lambda _seconds: None,
    )

    assert source.fetch_all_astocks(
        cache_dir=str(tmp_path),
        resume_partial=True,
    ) == []
    cached = json.loads(
        (tmp_path / "all_stocks_cache.json").read_text(encoding="utf-8")
    )
    assert calls == 3
    assert cached["status"] == "partial"
    assert cached["failed_page"] == 1
    assert "empty_page" in cached["error"]


def test_downstream_consumer_reuses_partial_cache_without_refetch(
    monkeypatch, tmp_path: Path
):
    source = source_with_retries()
    cache = {
        "schema_version": "intraday_all_stocks_cache.v2",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "partial",
        "stock_count": 1,
        "page_size": 100,
        "pages_fetched": 1,
        "next_page": 2,
        "failed_page": 2,
        "error": "limited",
        "source": "sina",
        "stocks": [{"code": "600000", "market": 1, "name": "样本"}],
    }
    (tmp_path / "all_stocks_cache.json").write_text(
        json.dumps(cache, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        source,
        "_fetch_all_sina_paginated_result",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not refetch")),
    )

    stocks = source.fetch_all_astocks(cache_dir=str(tmp_path))

    assert len(stocks) == 1
    assert source.last_all_stocks_quality["status"] == "partial"


def test_phase_zero_resumes_partial_cache_at_failed_page(monkeypatch, tmp_path: Path):
    source = source_with_retries()
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [{"code": f"6{i:05d}", "market": 1} for i in range(100)]
    (tmp_path / "all_stocks_cache.json").write_text(
        json.dumps({
            "date": today,
            "status": "partial",
            "page_size": 100,
            "pages_fetched": 1,
            "next_page": 2,
            "failed_page": 2,
            "stocks": existing,
        }),
        encoding="utf-8",
    )
    captured = {}

    def fake_resume(**kwargs):
        captured.update(kwargs)
        return AllStocksFetchResult(
            "complete",
            list(kwargs["initial_stocks"]),
            kwargs["page_size"],
            kwargs["pages_fetched"],
            3,
        )

    monkeypatch.setattr(source, "_fetch_all_sina_paginated_result", fake_resume)
    source.fetch_all_astocks(cache_dir=str(tmp_path), resume_partial=True)

    assert captured["start_page"] == 2
    assert captured["pages_fetched"] == 1
    assert len(captured["initial_stocks"]) == 100
    cached = json.loads(
        (tmp_path / "all_stocks_cache.json").read_text(encoding="utf-8")
    )
    assert cached["status"] == "complete"


def test_legacy_same_day_cache_is_not_assumed_complete(monkeypatch, tmp_path: Path):
    source = source_with_retries()
    today = datetime.now().strftime("%Y-%m-%d")
    legacy = [{"code": f"{i:06d}", "market": 0} for i in range(1399)]
    (tmp_path / "all_stocks_cache.json").write_text(
        json.dumps({"date": today, "stock_count": 1399, "stocks": legacy}),
        encoding="utf-8",
    )
    captured = {}

    def fake_resume(**kwargs):
        captured.update(kwargs)
        return AllStocksFetchResult(
            "partial",
            list(kwargs["initial_stocks"]),
            kwargs["page_size"],
            kwargs["pages_fetched"],
            kwargs["start_page"],
            kwargs["start_page"],
            "limited",
        )

    monkeypatch.setattr(source, "_fetch_all_sina_paginated_result", fake_resume)
    source.fetch_all_astocks(cache_dir=str(tmp_path), resume_partial=True)

    assert captured["start_page"] == 15
    assert captured["pages_fetched"] == 14
