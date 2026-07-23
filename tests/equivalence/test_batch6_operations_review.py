from __future__ import annotations

import copy
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from ashare_pilot.operations import market_confirmation as new_market
from ashare_pilot.operations import mechanical_classification as new_classification
from ashare_pilot.operations import operation_time as new_time
from ashare_pilot.operations._commands import render_guide as new_render
from ashare_pilot.operations._commands import run_guide as new_runner
from ashare_pilot.operations._commands import snapshot as new_snapshot
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace
from ashare_pilot.review._commands import backtest_entry_band as new_band
from ashare_pilot.review._commands import backtest_entry_quality as new_quality
from ashare_pilot.review._commands import verify as new_verify
from tests.equivalence.nondeterminism import normalize_nondeterminism

ROOT = Path(__file__).resolve().parents[2]
OPERATION_SCRIPTS = ROOT / ".opencode" / "skills" / "intraday-operation-guide" / "scripts"
REVIEW_SCRIPTS = ROOT / ".opencode" / "skills" / "daily-trading-review" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "review"


def load_old(name: str, path: Path, search_dir: Path):
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    sys.path.insert(0, str(search_dir))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(search_dir))


def test_completed_kline_and_mechanical_classification_match_legacy() -> None:
    old_time = load_old("legacy_operation_time_batch6", OPERATION_SCRIPTS / "operation_time.py", OPERATION_SCRIPTS)
    old_market = load_old("legacy_market_confirmation_batch6", OPERATION_SCRIPTS / "market_confirmation.py", OPERATION_SCRIPTS)
    old_classification = load_old("legacy_mechanical_classification_batch6", OPERATION_SCRIPTS / "mechanical_classification.py", OPERATION_SCRIPTS)
    at = datetime(2026, 7, 10, 9, 40, 5, tzinfo=new_time.MARKET_TZ)
    bars = [
        {"time": "2026-07-10 09:35:00", "close": 10.1},
        {"time": "2026-07-10 09:40:00", "close": 10.2},
        {"time": "2026-07-10 09:45:00", "close": 10.3},
    ]
    assert new_time.select_completed_bars(bars, at, at.date()) == old_time.select_completed_bars(bars, at, at.date())

    quotes = [
        {"code": "sh000001", "percent": -0.3, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
        {"code": "sz399001", "percent": -0.8, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
        {"code": "sh000688", "percent": -1.2, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
    ]
    market = new_market.build_market_confirmation(copy.deepcopy(quotes), "strong-sector")
    assert market == old_market.build_market_confirmation(copy.deepcopy(quotes), "strong-sector")
    strategy = {"direction": "看多", "profile": "趋势跟随", "position": 0.02, "no_buy": "破位取消"}
    signals = {
        "data_warning": [], "below_vwap": False, "high_open_fade": False,
        "extended_from_anchor": False, "near_ma5": True, "near_ma20": False,
        "first_bar": {"red_flag": False, "price_strength_confirmed": True},
        "latest_completed_bar": {"price_strength_confirmed": True, "volume_confirmed": True},
    }
    assert new_classification.compute_mechanical_decision(strategy, signals, market, at) == old_classification.compute_mechanical_decision(strategy, signals, market, at)


def test_stock_snapshot_and_html_match_legacy() -> None:
    old_snapshot = load_old("legacy_snapshot_batch6", OPERATION_SCRIPTS / "build_operation_snapshot.py", OPERATION_SCRIPTS)
    old_render = load_old("legacy_operation_render_batch6", OPERATION_SCRIPTS / "render_operation_guide_html.py", OPERATION_SCRIPTS)
    at = datetime(2026, 7, 10, 9, 40, 10, tzinfo=new_time.MARKET_TZ)
    strategy = {"code": "sz000001", "name": "测试", "sector": "银行", "direction": "看多", "profile": "趋势跟随", "anchor": "MA5", "position": 0.02, "no_buy": "跌破MA5取消"}
    mapper = {"ma5": 10, "ma20": 9.5, "atr": 0.5, "high20": 11, "low20": 8}
    quote = {"code": "sz000001", "name": "测试", "price": 10.2, "open": 10, "high": 10.3, "low": 9.9, "percent": 2, "yestclose": 10, "amount": 1020000, "volume": 100000, "time": "2026-07-10 09:40:01"}
    market = {"global_action": "SELECTIVE"}
    bars = [
        {"time": "2026-07-10 09:35:00", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 100},
        {"time": "2026-07-10 09:40:00", "open": 10.1, "high": 10.3, "low": 10, "close": 10.2, "volume": 160},
    ]
    old_stock = old_snapshot.build_stock_snapshot("sz000001", strategy, mapper, quote, at, market, bars)
    new_stock = new_snapshot.build_stock_snapshot("sz000001", strategy, mapper, quote, at, market, bars)
    assert new_stock == old_stock
    decision = {"schema_version": "intraday_operation_decision.v1", "date": "2026-07-10", "generated_at": at.isoformat(), "global_action": "SELECTIVE", "portfolio": {}, "stocks": []}
    assert new_render.render(decision, None) == old_render.render(decision, None)


def test_state_transition_and_immutable_publish_match_legacy(tmp_path: Path) -> None:
    old_transition = load_old("legacy_transition_batch6", OPERATION_SCRIPTS / "operation_transition.py", OPERATION_SCRIPTS)
    old_runner = load_old("legacy_runner_batch6", OPERATION_SCRIPTS / "run_operation_guide.py", OPERATION_SCRIPTS)
    stock = {
        "code": "sz000001",
        "decision_guardrails": {
            "mechanical_class": "A", "max_allowed_class": "A", "class_reasons": [],
            "position": {"morning_budget": 0.02, "market_adjusted_max": 0.01, "signal_adjusted_max": 0.01, "final_max": 0.01},
        },
    }
    old_current = [copy.deepcopy(stock)]
    new_current = [copy.deepcopy(stock)]
    old_delivery = old_transition.apply_delivery_gate(old_current, "09:40", False)
    new_delivery = __import__("ashare_pilot.operations.operation_transition", fromlist=["apply_delivery_gate"]).apply_delivery_gate(new_current, "09:40", False)
    assert (new_delivery, new_current) == (old_delivery, old_current)

    for runner, prefix in ((old_runner, "old"), (new_runner, "new")):
        pending = tmp_path / f".{prefix}.pending"
        destination = tmp_path / f"{prefix}.json"
        pending.write_text("first", encoding="utf-8")
        runner.publish_immutable(pending, destination)
        retry = tmp_path / f".{prefix}.retry"
        retry.write_text("second", encoding="utf-8")
        try:
            runner.publish_immutable(retry, destination)
        except RuntimeError as exc:
            assert "refusing to overwrite immutable artifact" in str(exc)
        else:
            raise AssertionError("immutable publish overwrote an existing artifact")
        assert destination.read_text(encoding="utf-8") == "first"


def test_operation_runner_offline_commit_is_complete_and_idempotent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    predict = tmp_path / "predict" / "2026-07-10"
    intraday = tmp_path / "fixtures" / "intraday"
    predict.mkdir(parents=True)
    intraday.mkdir(parents=True)
    strategy = {
        "schema_version": "daily_strategy.v1", "date": "2026-07-10",
        "market": {"regime_hint": "strong-sector"},
        "stocks": [{"code": "sz000001", "name": "测试", "sector": "银行", "direction": "看多", "entry_profile": "趋势跟随", "anchor": "MA5", "entry_trigger": "确认后参与", "no_buy_condition": "转弱取消", "position_budget": 0.02}],
    }
    mapper = {
        "schema_version": "daily_mapper.v1", "date": "2026-07-10",
        "candidate_pool": [{"code": "sz000001", "strategy_inputs": {"price": 10, "price_source": "PrevClose", "ma20": 9.5, "ma5": 10, "atr": 0.5, "atr_pct": 5, "high20": 11, "low20": 8}}],
        "observation_pool": [],
    }
    quotes = {
        "stocks": [{"code": "sz000001", "name": "测试", "price": 10.2, "open": 10, "high": 10.3, "low": 9.9, "percent": 2, "yestclose": 10, "amount": 1020000, "volume": 100000, "time": "2026-07-10 09:40:01"}],
        "indices": [
            {"code": "sh000001", "percent": 0.2, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
            {"code": "sz399001", "percent": 0.5, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
            {"code": "sh000688", "percent": 0.8, "open": 100, "yestclose": 100, "time": "2026-07-10 09:40:01"},
        ],
    }
    bars = [
        {"time": "2026-07-10 09:35:00", "open": 10, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 100},
        {"time": "2026-07-10 09:40:00", "open": 10.1, "high": 10.3, "low": 10, "close": 10.2, "volume": 160},
    ]
    (predict / "strategy.json").write_text(json.dumps(strategy), encoding="utf-8")
    (predict / "mapper.json").write_text(json.dumps(mapper), encoding="utf-8")
    quote_path = tmp_path / "fixtures" / "quotes.json"
    quote_path.write_text(json.dumps(quotes), encoding="utf-8")
    (intraday / "sz000001.json").write_text(json.dumps(bars), encoding="utf-8")
    argv = ["--date", "2026-07-10", "--as-of", "2026-07-10T09:40:10+08:00", "--quotes-fixture", str(quote_path), "--intraday-fixture-dir", str(intraday), "--no-network"]
    with use_workspace(Workspace(tmp_path)):
        assert new_runner.main(argv) == 0
        assert new_runner.main(argv) == 0
    operation_dir = tmp_path / "operation" / "2026-07-10"
    manifests = sorted(path for path in operation_dir.glob("operation_run_*.json") if path.name != "operation_run_state.json")
    assert len(manifests) == 2
    assert all(new_runner.committed_snapshot_names(operation_dir))
    latest = json.loads((operation_dir / "operation_run.latest.json").read_text(encoding="utf-8"))
    assert new_render.valid_run_manifest(operation_dir, latest)


def test_entry_band_and_quality_statistics_match_legacy() -> None:
    old_band = load_old("legacy_entry_band_batch6", REVIEW_SCRIPTS / "entry_band_shadow_backtest.py", REVIEW_SCRIPTS)
    old_quality = load_old("legacy_entry_quality_batch6", REVIEW_SCRIPTS / "entry_quality_backtest.py", REVIEW_SCRIPTS)
    files = [str(FIXTURES / "verification_2026-07-10.json"), str(FIXTURES / "verification_2026-07-11.json")]
    old_rows, old_warnings = old_band.load_rows(files)
    new_rows, new_warnings = new_band.load_rows(files)
    assert (new_rows, new_warnings) == (old_rows, old_warnings)
    assert new_band.summarize(new_rows) == old_band.summarize(old_rows)
    markdown = str(FIXTURES / "verification_2026-07-10.md")
    old_records, old_violations = old_quality.parse_file(markdown)
    new_records, new_violations = new_quality.parse_file(markdown)
    assert (new_records, new_violations) == (old_records, old_violations)
    assert new_quality.metrics(new_records[0]) == old_quality.metrics(old_records[0])


def test_verification_contract_matches_legacy_with_frozen_market_data(monkeypatch) -> None:
    old = load_old("legacy_verification_batch6", REVIEW_SCRIPTS / "generate_verification_json.py", REVIEW_SCRIPTS)
    day = {"date": "2026-07-10", "open": 10.0, "low": 9.8, "high": 10.5, "close": 10.3, "volume": 1000, "change_pct": 3.0}
    history = [{"date": f"2026-06-{index:02d}", "open": 9.0, "high": 10.0, "low": 8.5, "close": 9.5 + index / 100, "volume": 900} for index in range(1, 26)]
    for module in (old, new_verify):
        monkeypatch.setattr(module, "fetch_daily_records", lambda code, date: (day, history, None))
        monkeypatch.setattr(module, "first_candle_state", lambda code, date, anchor=None: ("企稳", {"close": 10.1}, None))
    kwargs = {"date": "2026-07-10", "strategy_path": None, "codes": ["sz000001"], "regime_hint": "neutral", "pool_indicators_path": None}
    old_doc = old.build_verification(**kwargs)
    new_doc = new_verify.build_verification(**kwargs)
    assert normalize_nondeterminism(
        new_doc, "daily_verification"
    ) == normalize_nondeterminism(old_doc, "daily_verification")
