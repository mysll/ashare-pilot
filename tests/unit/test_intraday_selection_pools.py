"""ADR-0004 Scoreability, Executability, and dual-pool invariants."""

from __future__ import annotations

import copy

import pytest

from ashare_pilot.strategy import intraday_selection
from ashare_pilot.strategy.intraday_selection import (
    assess_execution_eligibility,
    assess_scoreability,
    build_selection_pools,
    selection_invariant_errors,
)
from tests.intraday_selection_fixtures import build_selection_case


def frozen_stock(case_id: str) -> dict:
    return copy.deepcopy(build_selection_case(case_id)["stock"])


def test_scoreability_rejects_partial_money_and_technical_no_data():
    money = assess_scoreability(frozen_stock("partial_money_flow_uncovered"))
    technical = assess_scoreability(frozen_stock("technicals_no_data"))

    assert money["scoreable"] is False
    assert money["reasons"][0] == "money_flow_unavailable"
    assert technical["scoreable"] is False
    assert "technicals_no_data" in technical["reasons"]


def test_vwap_missing_is_scoreable_but_not_executable():
    document = build_selection_pools(
        [frozen_stock("vwap_missing")],
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": False},
    )

    assert document["scored_pool_summary"]["scoreable_count"] == 1
    assert document["executable_pool"] == []
    stock = document["observation_pool"][0]
    assert stock["score_status"] == "scored"
    assert stock["primary_observation_reason"] == "vwap_missing"


def test_frozen_cases_route_to_mutually_exclusive_pools_without_proxy_scores():
    stocks = [
        frozen_stock(case)
        for case in (
            "sealed_limit_up",
            "partial_money_flow_uncovered",
            "technicals_no_data",
            "vwap_missing",
            "i14_watch",
            "i14_cautious_hold",
        )
    ]
    stocks[-1]["code"] = "sz002397"
    document = build_selection_pools(
        stocks,
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": True},
    )

    assert selection_invariant_errors(document) == []
    executable_codes = {stock["code"] for stock in document["executable_pool"]}
    observation_codes = {stock["code"] for stock in document["observation_pool"]}
    assert executable_codes.isdisjoint(observation_codes)
    assert executable_codes == {"sz002397"}
    assert any(
        stock.get("i14_exemption") == "cautious_hold"
        for stock in document["executable_pool"]
    )
    assert any(
        stock.get("i14_exemption") == "watch"
        for stock in document["observation_pool"]
    )
    for stock in document["observation_pool"]:
        if stock["score_status"] == "unscored":
            assert "overnight_score" not in stock
            assert "rank" not in stock


def test_empty_executable_pool_is_successful_contract():
    document = build_selection_pools(
        [
            frozen_stock("sealed_limit_up"),
            frozen_stock("partial_money_flow_uncovered"),
            frozen_stock("technicals_no_data"),
            frozen_stock("vwap_missing"),
            frozen_stock("i14_watch"),
        ],
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": True},
    )

    assert selection_invariant_errors(document) == []
    assert document["executable_pool"] == []
    assert document["pool_summary"]["no_executable_candidates"] is True
    assert document["scored_pool_summary"]["scoreable_count"] > 0


def test_tier_never_filters_execution_and_d_tier_can_fill():
    eligible = frozen_stock("i14_cautious_hold")
    eligible["enriched"]["real_time"]["price"] = 31.3
    eligible["enriched"]["real_time"]["vwap"] = 30.0
    sealed = copy.deepcopy(eligible)
    sealed["enriched"]["real_time"]["price"] = 31.36
    sealed["enriched"]["real_time"]["high"] = 31.36
    stocks = []
    for index in range(35):
        row = copy.deepcopy(sealed)
        row["code"] = f"sh60{index:04d}"
        row["name"] = f"封板{index}"
        row["quick_score"] = 100 - index / 10
        stocks.append(row)
    for index in range(5):
        row = copy.deepcopy(eligible)
        row["code"] = f"sz00{index:04d}"
        row["name"] = f"可执行{index}"
        row["quick_score"] = 50 - index
        stocks.append(row)

    document = build_selection_pools(
        stocks,
        executable_limit=30,
        observation_limit=30,
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": False},
    )

    assert len(document["executable_pool"]) == 5
    assert any(stock["rank_tier"] == "D" for stock in document["executable_pool"])
    assert all(
        stock["execution_eligibility"]["eligible"]
        for stock in document["executable_pool"]
    )


def test_observation_reason_counts_are_before_top_n_truncation():
    rows = []
    for index in range(35):
        row = frozen_stock("partial_money_flow_uncovered")
        row["code"] = f"sz00{index:04d}"
        row["quick_score"] = 100 - index
        rows.append(row)
    document = build_selection_pools(
        rows,
        observation_limit=30,
        configured_min_inflow_yuan=5_000_000,
        regime={},
    )

    assert document["pool_summary"]["observation_total_before_limit"] == 35
    assert document["pool_summary"]["observation_count"] == 30
    assert document["pool_summary"]["observation_truncated_count"] == 5
    assert (
        document["pool_summary"]["observation_reason_counts"][
            "money_flow_unavailable"
        ]
        == 35
    )


def test_v13_trace_has_source_capital_proxy_and_no_theme_continuity():
    document = build_selection_pools(
        [frozen_stock("i14_cautious_hold")],
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": True},
    )
    scored = document["executable_pool"][0]

    assert "source_capital_proxy" in scored["score_trace"]
    assert "theme_continuity" not in scored["score_trace"]
    assert "i11_applied" not in scored


def test_money_threshold_is_inclusive_and_trend_floor_is_inclusive(
    monkeypatch: pytest.MonkeyPatch,
):
    stock = frozen_stock("i14_cautious_hold")
    stock["score_status"] = "scored"
    stock["execution_state"] = {"eligible": True}
    stock["enriched"]["money_flow"]["main_net_inflow_yuan"] = 5_000_000
    stock["enriched"]["real_time"]["price"] = 31.3
    stock["enriched"]["real_time"]["vwap"] = 30.0
    stock.pop("i14_exemption", None)
    monkeypatch.setattr(intraday_selection, "trend_raw", lambda _stock: 0.3)

    result = assess_execution_eligibility(stock, 5_000_000)

    assert result == {"eligible": True, "reasons": []}
