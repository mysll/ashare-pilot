"""Required-data hard stops and optional-data degradation contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_pilot.automation._commands import intraday
from ashare_pilot.indicators._commands import pool_enrich
from ashare_pilot.mapping._commands.intraday import compute_pool
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.strategy._commands.overnight import score
from ashare_pilot.themes._commands import dashboard
from ashare_pilot.workspace import Workspace


def valid_indices() -> list[dict]:
    return [
        {"code": "sh000001", "price": "3200.5", "percent": "+0.25%"},
        {"code": "sz399001", "price": "10400.2", "percent": "-0.10%"},
    ]


@pytest.mark.parametrize(
    ("document", "error"),
    [
        (valid_indices(), None),
        ([valid_indices()[1]], "required index missing: sh000001"),
        ([valid_indices()[0]], "required index missing: sz399001"),
        (
            [
                {"code": "sh000001", "price": "-", "percent": "0%"},
                valid_indices()[1],
            ],
            "required index price invalid: sh000001",
        ),
        (
            [
                valid_indices()[0],
                {"code": "sz399001", "price": "100", "percent": "nan"},
            ],
            "required index percent invalid: sz399001",
        ),
    ],
)
def test_required_indices_validate_presence_and_finite_values(document, error):
    errors = intraday.validate_required_indices(document)
    if error is None:
        assert errors == []
    else:
        assert error in errors


def test_auxiliary_index_gaps_are_explicit_but_do_not_degrade_required_status():
    quality = intraday.build_indices_quality(valid_indices())

    assert quality["status"] == "complete"
    assert quality["required_complete_count"] == 2
    assert quality["auxiliary_complete_count"] == 0
    assert quality["indices"]["sz399006"] == {
        "status": "unavailable",
        "required": False,
        "error": "missing_or_invalid_quote",
    }


def test_partial_all_stock_snapshot_stops_before_any_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        intraday._cache_ds,
        "fetch_all_astocks",
        lambda **_kwargs: [{"code": "600000"}],
    )
    intraday._cache_ds.last_all_stocks_quality = {
        "status": "partial",
        "pages_fetched": 1,
        "failed_page": 2,
        "next_page": 2,
        "error": "limited",
    }
    monkeypatch.setattr(
        intraday,
        "run_cmd",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not run downstream commands")
        ),
    )

    with use_workspace(Workspace(tmp_path)):
        assert intraday.main(["--date", "2026-07-27"]) == 1


def test_optional_concept_failure_overwrites_old_file_then_pipeline_can_continue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        intraday._cache_ds,
        "fetch_all_astocks",
        lambda **_kwargs: [{"code": "600000"}],
    )
    intraday._cache_ds.last_all_stocks_quality = {"status": "complete"}
    out_dir = tmp_path / ".cache" / "intraday" / "2026-07-27"
    out_dir.mkdir(parents=True)
    concept_path = out_dir / "concept_dashboard.json"
    concept_path.write_text(
        json.dumps({"status": "complete", "themes": {"OLD": {}}}),
        encoding="utf-8",
    )
    labels: list[str] = []

    def fake_run(_command: list[str], label: str = "") -> dict:
        labels.append(label)
        if label == "indices":
            (out_dir / "indices.json").write_text(
                json.dumps(valid_indices()),
                encoding="utf-8",
            )
        success = label not in {"concept", "scan"}
        return {"success": success, "stdout": "", "stderr": "", "elapsed": 0.0}

    monkeypatch.setattr(intraday, "run_cmd", fake_run)
    with use_workspace(Workspace(tmp_path)):
        assert intraday.main(["--date", "2026-07-27"]) == 1

    payload = json.loads(concept_path.read_text(encoding="utf-8"))
    assert labels == ["breadth", "indices", "concept", "scan"]
    assert payload["status"] == "unavailable"
    assert payload["themes"] == {}
    assert payload["error"] == "concept_dashboard_command_failed"


def test_partial_money_flow_uncovered_stock_gets_minimum_filter_flag(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(compute_pool._sina, "fetch_quotes", lambda _codes: [])

    class PartialResult:
        rows = []

        @staticmethod
        def quality(_codes):
            return {
                "status": "partial",
                "fetch_status": "partial",
                "matched_stock_count": 0,
            }

    monkeypatch.setattr(
        compute_pool._eastmoney,
        "fetch_stock_money_flow_adaptive",
        lambda **_kwargs: PartialResult(),
    )
    results, _quality = compute_pool.fetch_indicators_for_codes(
        ["sz000001"],
        include_quality=True,
        min_main_inflow_yuan=5_000_000,
    )

    assert results["sz000001"]["money_flow_available"] is False
    assert results["sz000001"]["money_flow_minimum_filter_applied"] is True


def test_partial_money_flow_uncovered_stock_is_never_median_imputed():
    pool = []
    for index in range(4):
        case = {
            "code": f"sz00000{index}",
            "source_pool": "turnover",
            "change_pct": "3%",
            "turnover": "5%",
            "volume_ratio": "1.2",
            "enriched": {
                "real_time": {"price": 10, "high": 11, "low": 9, "vwap": 9.8},
                "money_flow": {
                    "available": True,
                    "main_net_inflow": "1.0",
                    "super_large_net": "0.4",
                    "large_net": "0.3",
                    "medium_net": "0.2",
                    "small_net": "0.1",
                },
            },
            "technicals": {
                "boll_zone": "upper_half",
                "ma_alignment": "bullish",
                "above_ma5": True,
            },
        }
        pool.append(case)
    pool[0]["enriched"]["money_flow"] = {
        "available": False,
        "minimum_filter_applied": True,
    }

    score.compute_scores(pool, replace_missing=True)
    money_flags = [
        flag
        for flag in pool[0]["anomaly_flags"]
        if flag["dim"] in {"capital", "intensity", "conviction", "consistency"}
    ]

    assert money_flags
    assert all(flag["replacement"] is None for flag in money_flags)
    assert all(
        flag["reason"] == "money_flow_unavailable_not_imputed"
        for flag in money_flags
    )


def test_money_flow_unavailable_writes_quality_then_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    source = tmp_path / "scan.json"
    output = tmp_path / "enriched.json"
    source.write_text(
        json.dumps({"compute_pool": [{"code": "sz000001"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        compute_pool,
        "fetch_indicators_for_codes",
        lambda *_args, **_kwargs: (
            {
                "sz000001": {
                    "money_flow_available": False,
                    "money_flow_minimum_filter_applied": False,
                    "min_main_inflow_yuan": 5_000_000,
                }
            },
            {"status": "unavailable", "fetch_status": "unavailable"},
        ),
    )

    result = compute_pool.main(
        [str(source), "--json", "-o", str(output), "--no-board-filter"]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result == 1
    assert payload["data_quality"]["money_flow"]["status"] == "unavailable"
    assert payload["compute_pool"][0]["enriched"]["money_flow"]["available"] is False


def test_technical_pool_all_no_data_writes_summary_then_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    source = tmp_path / "enriched.json"
    output = tmp_path / "technicals.json"
    source.write_text(
        json.dumps(
            {
                "compute_pool": [
                    {
                        "code": "sz000001",
                        "enriched": {"real_time": {"price": 10}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pool_enrich, "_fetch_and_compute", lambda *_args: None)

    result = pool_enrich.main(
        [str(source), "--json", "-o", str(output), "--max-workers", "1"]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result == 1
    assert payload["data_quality"]["technicals"] == {
        "status": "unavailable",
        "requested_stock_count": 1,
        "valid_stock_count": 0,
        "no_data_stock_count": 1,
    }
    assert payload["compute_pool"][0]["technicals"]["status"] == "no_data"


def test_score_stops_when_every_vwap_is_invalid(tmp_path: Path):
    source = tmp_path / "enriched.json"
    source.write_text(
        json.dumps(
            {
                "compute_pool": [
                    {"code": "sz000001", "enriched": {"real_time": {"vwap": 0}}},
                    {"code": "sh600000", "enriched": {"real_time": {"vwap": None}}},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert score.main([str(source), "--json"]) == 1


def test_concept_dashboard_failure_is_explicit_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        dashboard._ds,
        "fetch_concept_ranking",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("limited")),
    )

    payload = dashboard.build_dashboard()

    assert payload["schema_version"] == "intraday_concept_dashboard.v1"
    assert payload["status"] == "unavailable"
    assert payload["themes"] == {}
    assert payload["rankings"] == {}
