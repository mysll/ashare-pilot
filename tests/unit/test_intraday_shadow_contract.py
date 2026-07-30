from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.review.intraday_shadow_contract import (
    SCHEMA_VERSION,
    build_contract,
    validate_contract,
)
from ashare_pilot.workspace import Workspace


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_workspace(tmp_path: Path) -> tuple[Workspace, Path]:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname='shadow-fixture'\n", encoding="utf-8"
    )
    write_json(
        root / "config" / "trading-scope.json",
        {
            "boards": {
                "sh688": {"exclude": True},
                "sh": {"exclude": False},
                "sz": {"exclude": False},
            },
            "overrides": [],
        },
    )
    write_json(
        root / "config" / "trading-calendar.json",
        {
            "timezone": "Asia/Shanghai",
            "daily_bar_publish_cutoff": "15:30",
            "years": {"2026": {"closures": []}},
        },
    )
    config = root / "config" / "intraday-shadow-rules.json"
    write_json(
        config,
        {
            "rule": {
                "rule_id": "ISR-TEST",
                "version": 1,
                "name": "test",
                "frozen_on": "2026-07-29",
                "hypothesis": "test only",
                "conditions": [
                    {"field": "change_pct", "min": 0, "max": 5},
                    {"field": "vwap_gap_pct", "min": 2, "max": 6},
                    {"field": "close_location", "min": 0.5},
                    {"field": "turnover_pct", "max": 5},
                ],
            },
            "label": {
                "primary_threshold_pct": 1,
                "assumed_round_trip_cost_bps": 20,
            },
            "data_quality": {
                "minimum_compute_pool_rows": 1,
                "minimum_t_plus_1_market_rows": 1,
                "minimum_t_plus_1_match_ratio": 1,
            },
            "prospective_gates": {
                "minimum_prospective_market_days": 1,
                "minimum_primary_success_rate": 0.75,
                "minimum_success_rate_lift": 0,
                "minimum_mean_mark_net_return_pct": 0,
            },
        },
    )
    return Workspace(root), config


def source_stock(code: str = "sh600001") -> dict:
    return {
        "code": code,
        "name": "测试股份",
        "price": "10.40",
        "change_pct": "+4.00%",
        "turnover": "+4.00%",
        "source_pool": "turnover",
        "enriched": {
            "real_time": {
                "price": "10.40",
                "high": "10.50",
                "low": "10.00",
                "yestclose": "10.00",
                "vwap": 10.0,
            }
        },
    }


def seed_source(root: Path, source_date: str = "2026-07-30") -> None:
    write_json(
        root / ".cache" / "intraday" / source_date / "compute_pool_enriched.json",
        {"compute_pool": [source_stock()]},
    )
    write_json(
        root / ".cache" / "intraday" / source_date / "market_breadth.json",
        {"up_ratio": 40.0},
    )


def seed_outcome(root: Path, outcome_date: str = "2026-07-31") -> None:
    write_json(
        root / ".cache" / "intraday" / outcome_date / "all_stocks_cache.json",
        {
            "fetched_at": f"{outcome_date} 14:31:00",
            "stocks": [
                {
                    "market": 1,
                    "code": "600001",
                    "open": 10.45,
                    "high": 10.70,
                    "price": 10.60,
                }
            ],
        },
    )


def test_build_contract_keeps_shadow_boundary_and_uses_prospective_rows(
    tmp_path: Path,
) -> None:
    workspace, config = make_workspace(tmp_path)
    seed_source(workspace.root)
    seed_outcome(workspace.root)

    with use_workspace(workspace):
        contract = build_contract(
            as_of_date="2026-07-31",
            config_path=config,
            now=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )

    assert contract["schema_version"] == SCHEMA_VERSION
    assert contract["mode"] == "VALIDATION_ONLY"
    assert set(contract["integration_boundary"].values()) >= {False}
    assert contract["dataset"]["matched_verified_rows"] == 1
    prospective = contract["evidence"]["phases"]["prospective"]["rule"]
    assert prospective["market_day_count"] == 1
    assert prospective["primary_success_rate"] == 1
    assert contract["prospective_review"]["automatic_promotion_allowed"] is False
    assert validate_contract(contract) == []


def test_contract_never_skips_a_missing_exact_t_plus_1_cache(
    tmp_path: Path,
) -> None:
    workspace, config = make_workspace(tmp_path)
    seed_source(workspace.root)
    seed_outcome(workspace.root, "2026-08-03")

    with use_workspace(workspace):
        contract = build_contract(
            as_of_date="2026-08-03",
            config_path=config,
        )

    assert contract["dataset"]["matched_verified_rows"] == 0
    assert contract["dataset"]["excluded_pairs"] == [
        {
            "source_date": "2026-07-30",
            "t_plus_1_date": "2026-07-31",
            "reason": "exact_t_plus_1_cache_missing",
        }
    ]


def test_current_day_match_is_pending_without_an_outcome(tmp_path: Path) -> None:
    workspace, config = make_workspace(tmp_path)
    seed_source(workspace.root)

    with use_workspace(workspace):
        contract = build_contract(
            as_of_date="2026-07-30",
            config_path=config,
        )

    assert contract["dataset"]["pending_matched_rows"] == 1
    assert "outcome" not in contract["evidence"]["pending_matches"][0]
    assert contract["prospective_review"]["evidence_status"] == (
        "awaiting_prospective_evidence"
    )


def test_validator_rejects_any_decision_semantics(tmp_path: Path) -> None:
    workspace, config = make_workspace(tmp_path)
    seed_source(workspace.root)

    with use_workspace(workspace):
        contract = build_contract(
            as_of_date="2026-07-30",
            config_path=config,
        )
    contract["recommendations"] = []
    contract["evidence"]["pending_matches"][0]["direction"] = "买入"

    errors = validate_contract(contract)

    assert "recommendations: decision field forbidden" in errors
    assert any("direction: decision field forbidden" in error for error in errors)
