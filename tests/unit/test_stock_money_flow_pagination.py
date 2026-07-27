"""Adaptive East Money stock-money-flow pagination and degradation tests."""

import json

from ashare_pilot.mapping._commands.intraday import compute_pool
from ashare_pilot.market_data._datasources.eastmoney import EastMoneyDataSource
from ashare_pilot.market_data._datasources.eastmoney import (
    StockMoneyFlowFetchResult,
)
from ashare_pilot.market_data.settings import (
    DEFAULT_STOCK_MONEY_FLOW_MIN_INFLOW_YUAN,
    load_stock_money_flow_min_inflow_yuan,
)
from ashare_pilot.strategy._commands.overnight import render_report, score


def money_rows(start: int, count: int) -> list[dict]:
    return [
        {"code": f"sz{index:06d}", "main_net_inflow": "1.00"}
        for index in range(start, start + count)
    ]


def test_adaptive_money_flow_uses_100_then_50_and_keeps_partial(monkeypatch):
    source = EastMoneyDataSource()
    calls = []

    def fake_page(*, page, page_size, sort_field, sort_desc):
        calls.append((page, page_size))
        if page == 1:
            return money_rows(0, 100), 300, None
        if page == 3:
            return money_rows(100, 50), 300, None
        return [], None, "api_rc:429"

    monkeypatch.setattr(source, "_fetch_stock_money_flow_page", fake_page)
    result = source.fetch_stock_money_flow_adaptive(
        target_codes={"sz999999"}
    )

    assert calls == [(1, 100), (3, 50), (4, 50)]
    assert result.status == "partial"
    assert result.failed_page == 4
    assert len(result.rows) == 150
    assert len({row["code"] for row in result.rows}) == 150
    assert result.quality({"sz000001", "sz999999"})["matched_stock_count"] == 1


def test_adaptive_money_flow_stops_when_analysis_pool_is_covered(monkeypatch):
    source = EastMoneyDataSource()
    calls = []

    def fake_page(*, page, page_size, sort_field, sort_desc):
        calls.append((page, page_size))
        if page == 1:
            return money_rows(0, 100), 300, None
        return money_rows(100, 50), 300, None

    monkeypatch.setattr(source, "_fetch_stock_money_flow_page", fake_page)
    targets = {"sz000001", "sz000120"}
    result = source.fetch_stock_money_flow_adaptive(target_codes=targets)

    assert calls == [(1, 100), (3, 50)]
    assert result.status == "complete"
    assert result.quality(targets)["coverage_pct"] == 100.0


def test_single_page_money_flow_clamps_requested_size_to_100(monkeypatch):
    source = EastMoneyDataSource()
    captured = {}

    def fake_page(**kwargs):
        captured.update(kwargs)
        return [], 0, None

    monkeypatch.setattr(source, "_fetch_stock_money_flow_page", fake_page)
    source.fetch_stock_money_flow(page_size=5000)
    assert captured["page_size"] == 100


def test_adaptive_money_flow_stops_and_filters_at_configured_threshold(monkeypatch):
    source = EastMoneyDataSource()
    calls = []

    def fake_page(*, page, page_size, sort_field, sort_desc):
        calls.append((page, page_size))
        if page == 1:
            return [
                {
                    "code": f"sz{index:06d}",
                    "main_net_inflow": "0.20",
                    "main_net_inflow_yuan": 20_000_000,
                }
                for index in range(100)
            ], 300, None
        return [
            {
                "code": f"sz{index:06d}",
                "main_net_inflow": "0.05",
                "main_net_inflow_yuan": (
                    15_000_000 if index < 110 else 5_000_000
                ),
            }
            for index in range(100, 150)
        ], 300, None

    monkeypatch.setattr(source, "_fetch_stock_money_flow_page", fake_page)
    result = source.fetch_stock_money_flow_adaptive(
        target_codes={"sz999999"},
        min_main_inflow_yuan=10_000_000,
    )

    assert calls == [(1, 100), (3, 50)]
    assert result.status == "threshold_reached"
    assert result.stop_reason == "main_inflow_below_threshold"
    assert len(result.rows) == 110
    assert all(row["main_net_inflow_yuan"] >= 10_000_000 for row in result.rows)
    assert result.quality({"sz999999"})["min_main_inflow_yuan"] == 10_000_000


def test_adaptive_money_flow_handles_empty_page_with_threshold(monkeypatch):
    source = EastMoneyDataSource()
    monkeypatch.setattr(
        source,
        "_fetch_stock_money_flow_page",
        lambda **kwargs: ([], 100, None),
    )

    result = source.fetch_stock_money_flow_adaptive(
        target_codes={"sz000001"},
        min_main_inflow_yuan=10_000_000,
    )

    assert result.status == "unavailable"
    assert result.error == "empty_page_before_complete"
    assert result.min_main_inflow_yuan == 10_000_000


def test_compute_pool_passes_configured_threshold_to_money_flow(monkeypatch):
    captured = {}

    monkeypatch.setattr(compute_pool._sina, "fetch_quotes", lambda codes: [])

    def fake_adaptive(**kwargs):
        captured.update(kwargs)
        return StockMoneyFlowFetchResult(
            status="threshold_reached",
            rows=[],
            reported_total=5000,
            pages_fetched=2,
            stop_reason="main_inflow_below_threshold",
            min_main_inflow_yuan=10_000_000,
        )

    monkeypatch.setattr(
        compute_pool._eastmoney,
        "fetch_stock_money_flow_adaptive",
        fake_adaptive,
    )
    results, quality = compute_pool.fetch_indicators_for_codes(
        ["sz000001"],
        include_quality=True,
        min_main_inflow_yuan=10_000_000,
    )

    assert captured["min_main_inflow_yuan"] == 10_000_000
    assert quality["fetch_status"] == "threshold_reached"
    assert results["sz000001"]["money_flow_minimum_filter_applied"] is True


def test_money_flow_threshold_setting_defaults_and_can_be_overridden(tmp_path):
    missing = tmp_path / "missing.json"
    assert (
        load_stock_money_flow_min_inflow_yuan(missing)
        == DEFAULT_STOCK_MONEY_FLOW_MIN_INFLOW_YUAN
    )

    configured = tmp_path / "setting.json"
    configured.write_text(
        json.dumps(
            {"market_data": {"stock_money_flow_min_inflow_yuan": 20_000_000}}
        ),
        encoding="utf-8",
    )
    assert load_stock_money_flow_min_inflow_yuan(configured) == 20_000_000


def test_missing_partial_money_flow_is_not_treated_as_zero_outflow():
    fetched = {
        "enriched": {"money_flow": {"available": True, "main_net_inflow": "-1"}},
        "technicals": {},
    }
    missing = {
        "enriched": {"money_flow": {"available": False}},
        "technicals": {},
    }

    assert score.stock_money_flow_available(fetched) is True
    assert score.stock_money_flow_available(missing) is False
    assert score.passes_absolute_floor(fetched, check_inflow=True)[0] is False
    assert score.passes_absolute_floor(missing, check_inflow=False)[0] is True


def test_threshold_filtered_money_flow_fails_absolute_floor():
    filtered = {
        "enriched": {
            "money_flow": {
                "available": False,
                "minimum_filter_applied": True,
                "minimum_main_inflow_yuan": 10_000_000,
            }
        },
        "technicals": {},
    }

    assert score.stock_money_flow_below_minimum(filtered) is True
    passed, reason = score.passes_absolute_floor(
        filtered,
        check_inflow=False,
        require_minimum_inflow=True,
    )
    assert passed is False
    assert "最低额度" in reason


def test_report_explicitly_describes_partial_data():
    doc = {
        "schema_version": "intraday_overnight_strategy.v1",
        "date": "2026-07-27",
        "data_quality": {
            "money_flow": {
                "status": "partial",
                "requested_stock_count": 120,
                "matched_stock_count": 73,
                "coverage_pct": 60.8,
                "pages_fetched": 4,
                "failed_page": 6,
            }
        },
        "positions": [],
        "watchlist": [],
    }
    rendered = render_report.render(doc)
    assert "数据完整性 · 资金流数据部分完整" in rendered
    assert "覆盖 73/120 只（60.8%）" in rendered
    assert "第 6 页失败后未重新抓取" in rendered


def test_report_explicitly_describes_threshold_filter():
    doc = {
        "schema_version": "intraday_overnight_strategy.v1",
        "date": "2026-07-27",
        "data_quality": {
            "money_flow": {
                "status": "partial",
                "fetch_status": "threshold_reached",
                "min_main_inflow_yuan": 10_000_000,
                "requested_stock_count": 120,
                "matched_stock_count": 86,
                "coverage_pct": 71.7,
                "pages_fetched": 8,
            }
        },
        "positions": [],
        "watchlist": [],
    }
    rendered = render_report.render(doc)
    assert "数据完整性 · 资金流数据按最低额度过滤" in rendered
    assert "最低额度为 1000 万元" in rendered
    assert "达到阈值边界并主动停止" in rendered
