"""Convergence tests for score_overnight single-truth behavior."""

import copy
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "score_overnight.py"


def load_score_mod():
    spec = importlib.util.spec_from_file_location("score_overnight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


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


def test_classify_tier_alias_ignores_absolute_score():
    mod = load_score_mod()
    assert mod.classify_tier(score=10.0, rank=1, pool_size=100) == "A"
    assert mod.classify_tier(score=99.0, rank=80, pool_size=100) == "D"


def test_i11_missing_conviction_source_replaced_by_valid_peer_median():
    mod = load_score_mod()
    victim = make_stock(code="sz000000", drop_super_large=True)
    pool = [victim] + [
        make_stock(code=f"sz{i:06d}", super_large_net="3.0") for i in range(1, 6)
    ]
    scored = mod.compute_scores(pool)
    victim = next(s for s in scored if s["code"] == "sz000000")
    assert victim.get("anomaly_flags")
    dims = {f["dim"] for f in victim["anomaly_flags"]}
    assert "conviction" in dims
    flag = next(f for f in victim["anomaly_flags"] if f["dim"] == "conviction")
    assert flag["reason"] == "missing_super_large_net"
    assert flag["valid_peer_count"] == 5
    assert flag["replacement"] is not None
    assert victim.get("i11_applied") is True


def test_i11_legitimate_zero_conviction_is_not_replaced():
    mod = load_score_mod()
    stock = make_stock(code="sz000099", main_net="5.0", super_large_net="0", large_net="5.0")
    scored = mod.compute_scores([stock] + healthy_pool(5))
    victim = next(s for s in scored if s["code"] == "sz000099")
    assert not any(f["dim"] == "conviction" for f in victim.get("anomaly_flags", []))


def test_i11_tail_range_contradiction_flagged():
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
    assert any(f["dim"] == "tail" for f in victim.get("anomaly_flags", []))


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
