from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ashare_pilot.strategy._commands.daily import (
    finalize,
    llm_input,
    render_report as daily_report,
    trade_profile,
)
from ashare_pilot.strategy._commands.overnight import (
    build as overnight_build,
    render_report as overnight_report,
    score as overnight_score,
)

ROOT = Path(__file__).resolve().parents[2]
DAILY_SCRIPTS = ROOT / ".opencode" / "skills" / "daily-strategy" / "scripts"
OVERNIGHT_SCRIPTS = ROOT / ".opencode" / "skills" / "intraday-strategy" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "strategy" / "step3_real"


def load_old(name: str, script: Path, search_dir: Path):
    if not script.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    sys.path.insert(0, str(search_dir))
    try:
        spec = importlib.util.spec_from_file_location(name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(search_dir))


def test_daily_compact_draft_and_html_match_legacy(tmp_path: Path) -> None:
    old_llm = load_old(
        "legacy_daily_llm_input_batch5",
        DAILY_SCRIPTS / "build_strategy_llm_input.py",
        DAILY_SCRIPTS,
    )
    old_finalize = load_old(
        "legacy_daily_finalize_batch5",
        DAILY_SCRIPTS / "finalize_daily_strategy.py",
        DAILY_SCRIPTS,
    )
    old_report = load_old(
        "legacy_daily_report_batch5",
        DAILY_SCRIPTS / "render_daily_report_html.py",
        DAILY_SCRIPTS,
    )
    fixture = json.loads((FIXTURES / "2026-07-13.json").read_text(encoding="utf-8"))

    old_compact = old_llm.build_input(
        fixture["view"], fixture["theme_stocks"], fixture["pool"], fixture["news"], fixture["indices"]
    )
    new_compact = llm_input.build_input(
        fixture["view"], fixture["theme_stocks"], fixture["pool"], fixture["news"], fixture["indices"]
    )
    assert new_compact == old_compact

    old_strategy = old_finalize.materialize(copy.deepcopy(fixture["draft"]), old_compact)
    new_strategy = finalize.materialize(copy.deepcopy(fixture["draft"]), new_compact)
    assert new_strategy == old_strategy

    news_path = tmp_path / "news.json"
    news_path.write_text(json.dumps(fixture["news"], ensure_ascii=False), encoding="utf-8")
    mapper = {"observation_pool": [], "excluded_stocks": []}
    assert daily_report.render_report(
        "2026-07-13", new_strategy, fixture["view"], mapper, None, news_path
    ) == old_report.render_report(
        "2026-07-13", old_strategy, fixture["view"], mapper, None, news_path
    )


def test_trade_profile_decision_tree_matches_legacy() -> None:
    old = load_old(
        "legacy_trade_profile_batch5",
        DAILY_SCRIPTS / "compute_trade_profile.py",
        DAILY_SCRIPTS,
    )
    raw = {
        "price": {"value": 10.2}, "ma20": {"value": 9.8}, "ma5": {"value": 10.0},
        "atr": {"value": 0.4}, "high20": {"value": 10.8},
        "board_streak": {"value": 0}, "yesterday_limit_up": {"value": False},
    }
    kwargs = dict(
        code="sz000001", raw_obs=raw, cp={}, regime="strong-sector",
        mainline=True, sector_heat=80, kcb_pct=2.5, sector_pct=3.0,
    )

    assert trade_profile.compute_trade_profile(**kwargs) == old.compute_trade_profile(**kwargs)


def test_overnight_scoring_matches_legacy() -> None:
    old = load_old(
        "legacy_overnight_score_batch5",
        OVERNIGHT_SCRIPTS / "score_overnight.py",
        OVERNIGHT_SCRIPTS,
    )
    pool = [
        {
            "code": f"sz{index:06d}", "change_pct": "4%", "turnover": "8%",
            "volume_ratio": "1.2", "source_pool": "turnover", "quick_score": 70 + index,
            "enriched": {
                "real_time": {"price": 10, "high": 11, "low": 9, "vwap": 9.5},
                "money_flow": {
                    "main_net_inflow": str(1 + index / 10), "super_large_net": "1",
                    "large_net": "0.5", "medium_net": "0.2", "small_net": "0.1",
                },
            },
            "technicals": {"boll_zone": "upper_half", "ma_alignment": "bullish", "above_ma5": True},
        }
        for index in range(8)
    ]
    regime = {"up_ratio_pct": 45, "sz_change_pct": 0.5, "i10_capital_scale": 1.0}

    assert overnight_score.compute_scores(copy.deepcopy(pool), regime=regime) == old.compute_scores(
        copy.deepcopy(pool), regime=regime
    )


def test_overnight_contract_and_html_match_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_build = load_old(
        "legacy_overnight_build_batch5",
        OVERNIGHT_SCRIPTS / "build_overnight_strategy_json.py",
        OVERNIGHT_SCRIPTS,
    )
    old_report = load_old(
        "legacy_overnight_report_batch5",
        OVERNIGHT_SCRIPTS / "render_overnight_strategy_html.py",
        OVERNIGHT_SCRIPTS,
    )
    mapper = {
        "schema_version": "intraday_mapper.v1",
        "date": "2026-07-13",
        "generated_at": "2026-07-13T06:30:00+00:00",
        "pool_summary": {"scoring_policy_version": "convergence_v1"},
        "market_assessment": {"regime": "neutral", "reasoning_trace": "frozen"},
        "strategy": {"position_cap": "0%"},
        "stocks": [],
    }
    timestamp = "2026-07-13T07:00:00+00:00"
    monkeypatch.setattr(old_build, "utc_now_iso", lambda: timestamp)
    monkeypatch.setattr(overnight_build, "utc_now_iso", lambda: timestamp)
    old_doc = old_build.build(copy.deepcopy(mapper))
    new_doc = overnight_build.build(copy.deepcopy(mapper))

    assert new_doc == old_doc
    assert overnight_report.render(new_doc, mapper) == old_report.render(old_doc, mapper)
