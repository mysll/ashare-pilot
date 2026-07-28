"""Recall-quality and shared trading-scope contract tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ashare_pilot.mapping import intraday_contract
from ashare_pilot.mapping._commands.intraday import scan_pool
from ashare_pilot.market_data.trading_scope import scope_decision
from tests.intraday_selection_fixtures import build_selection_case


def stock(code: str, *, source_change: str = "+3.0%") -> dict:
    return {
        "code": code,
        "name": "样本",
        "change_pct": source_change,
        "amount": "100",
        "turnover": "8%",
        "volume_ratio": "2",
    }


def scope() -> dict:
    return {
        "boards": {
            "sh": {"exclude": False},
            "sh688": {"exclude": True, "reason": "STAR excluded"},
            "sz": {"exclude": False},
            "sz30": {"exclude": True},
        },
        "overrides": [
            {"code": "sh688001", "allowed": True, "reason": "exact allow"},
            {"codes": ["sz300001"], "exclude": False},
        ],
    }


@pytest.mark.parametrize(
    ("code", "excluded", "matched_rule"),
    [
        ("sh600000", False, "boards.sh"),
        ("sh688002", True, "boards.sh688"),
        ("sh688001", False, "overrides.sh688001"),
        ("sz300002", True, "boards.sz30"),
        ("sz300001", False, "overrides.sz300001"),
        ("hk00700", True, "boards.<none>"),
    ],
)
def test_scan_and_execution_use_identical_scope_decision(
    code: str,
    excluded: bool,
    matched_rule: str,
):
    policy = scope()

    decision = scope_decision(code, policy)
    kept, removed = scan_pool.apply_board_filter([stock(code)], policy)
    execution = intraday_contract.execution_state(
        {
            "code": code,
            "name": "样本",
            "enriched": {
                "real_time": {"price": 10, "high": 10, "yestclose": 10}
            },
        },
        policy,
    )

    assert decision["excluded"] is excluded
    assert decision["matched_rule"] == matched_rule
    assert bool(removed) is excluded
    assert bool(kept) is not excluded
    assert execution["board_excluded"] is excluded
    assert execution["board_rule"] == matched_rule


def test_turnover_unavailable_can_continue_when_other_recall_is_sufficient(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    rows = [stock(f"sh60{index:04d}") for index in range(120)]
    fake = SimpleNamespace(
        fetch_all_astocks=lambda **_kwargs: [],
        fetch_limit_up_pool=lambda **_kwargs: [dict(row) for row in rows],
        fetch_turnover_ranking=lambda **_kwargs: [],
        fetch_scan_stocks=lambda **_kwargs: [],
        last_turnover_quality={
            "status": "unavailable",
            "count": 0,
            "error": "rate_limited",
        },
    )
    monkeypatch.setattr(scan_pool, "_ds", fake)
    monkeypatch.setattr(
        scan_pool,
        "load_trading_scope",
        lambda: {"boards": {"sh": {"exclude": False}}, "overrides": []},
    )
    output = tmp_path / "scan.json"

    result = scan_pool.main(
        [
            "--compute-pool-size",
            "120",
            "--cache-dir",
            str(tmp_path),
            "--json",
            "-o",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["compute_pool_size"] == 120
    assert payload["recall_quality"]["turnover"] == {
        "status": "unavailable",
        "count": 0,
        "error": "rate_limited",
    }


def test_scan_pool_below_compute_target_is_nonzero_and_keeps_quality_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    rows = [stock(f"sz00{index:04d}") for index in range(3)]
    fake = SimpleNamespace(
        fetch_all_astocks=lambda **_kwargs: [],
        fetch_limit_up_pool=lambda **_kwargs: [dict(row) for row in rows],
        fetch_turnover_ranking=lambda **_kwargs: [],
        fetch_scan_stocks=lambda **_kwargs: [],
        last_turnover_quality={
            "status": "unavailable",
            "count": 0,
            "error": "timeout",
        },
    )
    monkeypatch.setattr(scan_pool, "_ds", fake)
    monkeypatch.setattr(
        scan_pool,
        "load_trading_scope",
        lambda: {"boards": {"sz": {"exclude": False}}, "overrides": []},
    )
    output = tmp_path / "scan.json"

    result = scan_pool.main(
        [
            "--compute-pool-size",
            "4",
            "--cache-dir",
            str(tmp_path),
            "--json",
            "-o",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert payload["compute_pool_size"] == 3
    assert payload["recall_quality"]["turnover"]["status"] == "unavailable"


def test_v2_schema_constants_are_frozen():
    assert (
        intraday_contract.SELECTION_POOLS_SCHEMA_VERSION
        == "intraday_selection_pools.v1"
    )
    assert intraday_contract.MAPPER_BASE_SCHEMA_VERSION == "intraday_mapper_base.v2"
    assert (
        intraday_contract.MAPPER_ANNOTATIONS_SCHEMA_VERSION
        == "intraday_mapper_annotations.v2"
    )
    assert intraday_contract.MAPPER_SCHEMA_VERSION == "intraday_mapper.v2"
    assert (
        intraday_contract.OVERNIGHT_STRATEGY_SCHEMA_VERSION
        == "intraday_overnight_strategy.v2"
    )


def test_frozen_i14_boundary_variant_is_materialized_without_mutating_base():
    watch = build_selection_case("i14_watch")
    cautious = build_selection_case("i14_cautious_hold")

    assert watch["stock"]["enriched"]["real_time"]["vwap"] == 29.949
    assert cautious["stock"]["enriched"]["real_time"]["vwap"] == 31.2
    assert cautious["expected"]["i14_exemption"] == "cautious_hold"
