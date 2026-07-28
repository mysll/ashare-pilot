"""Convergence tests for score_overnight single-truth behavior."""

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ashare_pilot.mapping import intraday_contract
from ashare_pilot.mapping._commands.intraday import validate_annotations
from ashare_pilot.strategy._commands.overnight import build, score

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_score_mod():
    return score


def load_script_mod(name):
    return {
        "validate_intraday_mapper_annotations": validate_annotations,
        "build_overnight_strategy_json": build,
        "intraday_mapper_json_lib": intraday_contract,
    }[name]


def make_stock(
    code="sz000001",
    change_pct="4%",
    turnover="8%",
    volume_ratio="1.2",
    source_pool="turnover",
    price=10.0,
    high=11.0,
    low=9.0,
    vwap=9.5,
    main_net="2.0",
    super_large_net="1.0",
    large_net="0.5",
    medium_net="0.2",
    small_net="0.1",
    quick_score=None,
    drop_super_large=False,
):
    stock = {
        "code": code,
        "change_pct": change_pct,
        "turnover": turnover,
        "volume_ratio": volume_ratio,
        "source_pool": source_pool,
        "enriched": {
            "real_time": {
                "price": price,
                "high": high,
                "low": low,
                "vwap": vwap,
            },
            "money_flow": {
                "main_net_inflow": main_net,
                "super_large_net": super_large_net,
                "large_net": large_net,
                "medium_net": medium_net,
                "small_net": small_net,
            },
        },
        "technicals": {
            "boll_zone": "upper_half",
            "ma_alignment": "bullish",
            "above_ma5": True,
        },
    }
    if quick_score is not None:
        stock["quick_score"] = quick_score
    if drop_super_large:
        stock["enriched"]["money_flow"].pop("super_large_net", None)
    return stock


def healthy_pool(n=20):
    return [
        make_stock(code=f"sz{i:06d}", main_net=str(1.0 + i * 0.1))
        for i in range(n)
    ]


def clone(obj):
    return copy.deepcopy(obj)


def by_code(scored):
    return {s["code"]: s for s in scored}


def test_classify_rank_tier_percentiles():
    mod = load_score_mod()
    assert mod.classify_rank_tier(rank=1, pool_size=100) == "A"
    assert mod.classify_rank_tier(rank=10, pool_size=100) == "A"
    assert mod.classify_rank_tier(rank=11, pool_size=100) == "B"
    assert mod.classify_rank_tier(rank=40, pool_size=100) == "B"
    assert mod.classify_rank_tier(rank=41, pool_size=100) == "C"
    assert mod.classify_rank_tier(rank=70, pool_size=100) == "C"
    assert mod.classify_rank_tier(rank=71, pool_size=100) == "D"


def test_compute_scores_sets_only_rank_tier_by_percentile():
    mod = load_score_mod()
    scored = mod.compute_scores(healthy_pool(20))
    for s in scored:
        expected = mod.classify_rank_tier(s["rank"], len(scored))
        assert s.get("rank_tier") == expected
        assert s.get("tier") == expected
        assert s.get("absolute_score") == s.get("overnight_score")
        assert "tradeability" not in s
        assert s["rank_tier_rule"] == "rank_percentile_v1"


def test_compute_scores_empty_pool_is_safe():
    mod = load_score_mod()
    assert mod.compute_scores([]) == []


def test_risk_penalty_increases_with_risk_raw():
    mod = load_score_mod()
    pool = [
        make_stock(code="sz000001", change_pct="4%", turnover="8%"),
        make_stock(code="sz000002", change_pct="7%", turnover="16%"),
        make_stock(
            code="sz000003",
            change_pct="9.5%",
            turnover="26%",
            source_pool="limit_up",
        ),
    ]

    scored = by_code(mod.compute_scores(pool))
    low = scored["sz000001"]["score_trace"]["risk_penalty"]
    medium = scored["sz000002"]["score_trace"]["risk_penalty"]
    high = scored["sz000003"]["score_trace"]["risk_penalty"]

    assert low["raw"] < medium["raw"] < high["raw"]
    assert low["pct"] < medium["pct"] < high["pct"]
    assert low["contrib"] < medium["contrib"] < high["contrib"]


def test_classify_tier_alias_ignores_absolute_score():
    mod = load_score_mod()
    assert mod.classify_tier(score=10.0, rank=1, pool_size=100) == "A"
    assert mod.classify_tier(score=99.0, rank=80, pool_size=100) == "D"


def test_selection_scoring_does_not_apply_i11_peer_replacement():
    mod = load_score_mod()
    victim = make_stock(code="sz000000", drop_super_large=True)
    pool = [victim] + [
        make_stock(code=f"sz{i:06d}", super_large_net="3.0") for i in range(1, 6)
    ]
    scored = mod.compute_scores(pool)
    victim = next(s for s in scored if s["code"] == "sz000000")
    assert victim.get("anomaly_flags") is None
    assert victim.get("i11_applied") is None


def test_i11_legitimate_zero_conviction_is_not_replaced():
    mod = load_score_mod()
    stock = make_stock(code="sz000099", main_net="5.0", super_large_net="0", large_net="5.0")
    scored = mod.compute_scores([stock] + healthy_pool(5))
    victim = next(s for s in scored if s["code"] == "sz000099")
    assert not any(f["dim"] == "conviction" for f in victim.get("anomaly_flags", []))


def test_selection_scoring_does_not_apply_i11_tail_replacement():
    mod = load_score_mod()
    stock = make_stock(
        code="sz000001",
        change_pct="5%",
        turnover="27%",
        volume_ratio="2.0",
        price=10,
        high=10,
        low=10,
        vwap=9.9,
    )
    scored = mod.compute_scores([stock] + healthy_pool(6))
    victim = next(s for s in scored if s["code"] == "sz000001")
    assert victim.get("anomaly_flags") is None
    assert victim.get("i11_applied") is None


def test_i10_scale_table():
    mod = load_score_mod()
    assert mod.i10_capital_scale(up_ratio_pct=50, sz_change_pct=-1) == 1.0
    assert mod.i10_capital_scale(up_ratio_pct=30, sz_change_pct=-1) == 0.5
    assert mod.i10_capital_scale(up_ratio_pct=15, sz_change_pct=-1) == 0.25
    assert mod.i10_capital_scale(up_ratio_pct=5, sz_change_pct=-1) == 0.0
    assert mod.i10_capital_scale(up_ratio_pct=15, sz_change_pct=0.5) == 1.0


def test_i10_reduces_capital_contribution_when_active():
    mod = load_score_mod()
    pool = healthy_pool(10)
    normal = by_code(
        mod.compute_scores(
            clone(pool),
            regime={"up_ratio_pct": 50, "sz_change_pct": 1, "i10_capital_scale": 1.0},
        )
    )
    weak = by_code(
        mod.compute_scores(
            clone(pool),
            regime={"up_ratio_pct": 12, "sz_change_pct": -1, "i10_capital_scale": 0.25},
        )
    )
    for code in normal:
        assert (
            weak[code]["score_trace"]["capital_continuity"]["pct"]
            == normal[code]["score_trace"]["capital_continuity"]["pct"]
        )
        assert (
            weak[code]["score_trace"]["capital_continuity"]["contrib"]
            <= normal[code]["score_trace"]["capital_continuity"]["contrib"]
        )
        assert weak[code]["overnight_score"] <= normal[code]["overnight_score"]


def test_i10_zero_scale_zeros_capital_family_contributions():
    mod = load_score_mod()
    scored = mod.compute_scores(
        healthy_pool(10),
        regime={"up_ratio_pct": 5, "sz_change_pct": -1, "i10_capital_scale": 0.0},
    )
    for stock in scored:
        for dim in ("capital_continuity", "intensity", "conviction", "consistency"):
            assert stock["score_trace"][dim]["contrib"] == 0.0


def test_vwap_hard_exclude_without_i14():
    mod = load_score_mod()
    stock = {
        "code": "sz1",
        "quick_score": 90,
        "enriched": {"real_time": {"price": 9.7, "vwap": 10.0}},
    }
    passed, filtered, _ = mod.apply_quality_filter([stock], regime={"up_ratio_pct": 50})
    assert len(passed) == 0 and len(filtered) == 1


def test_i14_micro_deviation_passes():
    mod = load_score_mod()
    stock = {
        "code": "sz1",
        "quick_score": 75,
        "enriched": {"real_time": {"price": 9.8, "vwap": 10.0}},
    }
    passed, filtered, stats = mod.apply_quality_filter(
        [stock], regime={"up_ratio_pct": 33, "i14_active": True}
    )
    assert len(passed) == 1
    assert passed[0].get("i14_exemption") == "watch"
    assert stats["i14_applied_count"] == 1


def test_i14_missing_quick_score_does_not_pass():
    mod = load_score_mod()
    stock = {"code": "sz000001", "enriched": {"real_time": {"price": 9.8, "vwap": 10.0}}}
    passed, filtered, stats = mod.apply_quality_filter(
        [stock], regime={"up_ratio_pct": 33, "i14_active": True}
    )
    assert not passed and len(filtered) == 1
    assert stats["i14_skipped_no_quick_score"] == 1


def test_parse_regime_from_files_direct_up_ratio():
    mod = load_score_mod()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        breadth = {
            "up_count": 595,
            "down_count": 4647,
            "flat_count": 30,
            "total": 5272,
            "up_ratio": 11.29,
            "partial": False,
        }
        indices = [
            {"code": "sh000001", "percent": "-1.36%"},
            {"code": "sz399001", "percent": "-1.43%"},
        ]
        bp = root / "market_breadth.json"
        ip = root / "indices.json"
        bp.write_text(json.dumps(breadth), encoding="utf-8")
        ip.write_text(json.dumps(indices), encoding="utf-8")
        snap = mod.parse_regime_from_files(str(bp), str(ip))
        assert snap["available"] is True
        assert snap["up_ratio_pct"] == 11.29
        assert snap["sz_change_pct"] == -1.43
        assert snap["i10_active"] is True
        assert snap["i14_active"] is True
        assert snap["i10_capital_scale"] == 0.25


def test_parse_regime_partial_unavailable():
    mod = load_score_mod()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bp = root / "b.json"
        ip = root / "i.json"
        bp.write_text(json.dumps({"up_ratio": 10, "partial": True}), encoding="utf-8")
        ip.write_text(json.dumps([{"code": "sz399001", "percent": "-1%"}]), encoding="utf-8")
        snap = mod.parse_regime_from_files(str(bp), str(ip))
        assert snap["available"] is False
        assert snap["i10_active"] is False
        assert snap["i10_capital_scale"] == 1.0


def test_parse_regime_rejects_invalid_breadth_ranges():
    mod = load_score_mod()
    cases = [
        {"up_ratio": -5, "partial": False},
        {"up_ratio": 105, "partial": False},
        {"up_count": -5, "down_count": 10, "flat_count": 0, "partial": False},
    ]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ip = root / "indices.json"
        ip.write_text(json.dumps([{"code": "sz399001", "percent": "-1%"}]), encoding="utf-8")
        for index, breadth in enumerate(cases):
            bp = root / f"breadth-{index}.json"
            bp.write_text(json.dumps(breadth), encoding="utf-8")
            snap = mod.parse_regime_from_files(str(bp), str(ip))
            assert snap["available"] is False
            assert snap["i10_active"] is False
            assert snap["i14_active"] is False
            assert snap["i10_capital_scale"] == 1.0


def convergence_annotation(tradeability="Watch", direction="观望", position_cap="0%"):
    return {
        "schema_version": "intraday_mapper_annotations.v1",
        "date": "2026-07-13",
        "market_assessment": {"reasoning_trace": "test"},
        "stocks": [{
            "code": "sz000001",
            "tradeability": tradeability,
            "direction": direction,
            "trading_strategy": "趋势跟随",
            "risk_severity": "low",
            "expected_premium": "test",
            "key_reason": "test",
            "reasoning_trace": "test",
            "t_plus_1_plan": {
                "auction_condition": "test",
                "open_strategy": "test",
                "stop_loss_basis": "not_applicable",
                "take_profit": "test",
            },
        }],
        "strategy": {"position_cap": position_cap},
    }


def convergence_base():
    return {
        "pool_summary": {
            "scoring_policy_version": "convergence_v1",
            "regime_snapshot": {"available": True, "up_ratio_pct": 10},
        },
        "stocks": [{"code": "sz000001", "i14_exemption": "watch"}],
    }


def execution_base_stock(
    *, code="sz000767", name="晋控电力", source_pool="limit_up", price=3.76,
    high=3.76, low=3.34, yestclose=3.42
):
    return {
        "code": code,
        "name": name,
        "source_pool": source_pool,
        "price": str(price),
        "enriched": {"real_time": {
            "price": str(price),
            "high": None if high is None else str(high),
            "low": str(low),
            "yestclose": str(yestclose),
        }},
        "technicals": {"ma5": 3.36, "ma10": 3.4, "ma20": 3.7},
    }


def execution_annotation(*, tradeability="Extended", direction="观望", basis="not_applicable"):
    item = convergence_annotation(tradeability=tradeability, direction=direction)
    item["stocks"][0]["code"] = "sz000767"
    item["stocks"][0]["t_plus_1_plan"]["stop_loss_basis"] = basis
    return item


def test_994_percent_limit_up_is_deterministically_sealed():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock()
    state = mod.execution_state(stock)
    assert state["is_limit_up"] is True
    assert state["is_sealed"] is True
    assert state["limit_up_price"] == 3.76
    assert state["quote_complete"] is True
    assert state["board_rule"] == "boards.sz"
    assert state["eligible"] is False
    assert state["exclusion_reason"] == "sealed_limit_up"


def test_sealed_detection_uses_quote_not_source_pool_tag():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock(source_pool="turnover")
    state = mod.execution_state(stock)
    assert state["source_pool_limit_up"] is False
    assert state["is_limit_up"] is True
    assert state["is_sealed"] is True
    assert state["eligible"] is False


def test_missing_high_fails_closed():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock(source_pool="turnover", high=None)
    state = mod.execution_state(stock)
    assert state["quote_complete"] is False
    assert state["eligible"] is False
    assert state["exclusion_reason"] == "quote_data_missing"


def test_board_exclusion_uses_scope_override_and_longest_prefix():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock(code="sh688001", source_pool="turnover", price=10, high=10.2)
    scope = {
        "boards": {"sh": {"exclude": False}, "sh688": {"exclude": True, "reason": "scope-star"}},
        "overrides": [{"code": "sh688001", "allowed": True, "reason": "test override"}],
    }
    state = mod.execution_state(stock, scope=scope)
    assert state["board_excluded"] is False
    assert state["board_rule"] == "overrides.sh688001"
    scope["overrides"] = []
    state = mod.execution_state(stock, scope=scope)
    assert state["board_excluded"] is True
    assert state["board_rule"] == "boards.sh688"
    assert state["board_reason"] == "scope-star"


def test_execution_state_cannot_be_tampered_to_bypass_filter():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock()
    stock["execution_state"] = {
        "is_limit_up": False,
        "is_sealed": False,
        "board_excluded": False,
        "eligible": True,
        "exclusion_reason": None,
    }
    reasoning = {
        "tradeability": "Suitable",
        "direction": "谨慎持有",
        "t_plus_1_plan": {"stop_loss_basis": "day_low"},
    }
    errors = mod.reasoning_invariant_errors(stock, reasoning)
    assert any("differs from deterministic compute fields" in error for error in errors)
    assert any("sealed limit-up requires direction=观望" in error for error in errors)


def test_stop_loss_is_resolved_from_same_stock_and_must_be_below_price():
    mod = load_script_mod("intraday_mapper_json_lib")
    stock = execution_base_stock(source_pool="turnover", price=3.76, high=3.8, low=3.34)
    assert mod.resolved_stop_loss(stock, "day_low")["stop_loss_price"] == 3.34
    bad = copy.deepcopy(stock)
    bad["enriched"]["real_time"]["low"] = "5.67"
    reasoning = {
        "tradeability": "Suitable",
        "direction": "谨慎持有",
        "t_plus_1_plan": {"stop_loss_basis": "day_low"},
    }
    assert any("below current price" in error for error in mod.reasoning_invariant_errors(bad, reasoning))
