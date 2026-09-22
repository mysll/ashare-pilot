"""Unit tests for the side-car limit-up cluster screen."""

from __future__ import annotations

from ashare_pilot.mapping.intraday_contract import execution_state, limit_ratio
from ashare_pilot.screen._commands.limit_up_cluster import (
    DEFAULT_CONFIG,
    SCREEN_SCHEMA_VERSION,
    board_of,
    build_from_files,
    is_limit_up,
    limit_bounds,
    prefix_code,
    run_screen,
)
from ashare_pilot.strategy._commands.overnight.render_report import (
    limit_up_cluster_section,
)


def stock(code, name, chg, turnover, market=0):
    return {
        "code": code,
        "market": market,
        "name": name,
        "chg_pct": chg,
        "turnover": turnover,
    }


def history(*closes):
    rows = [{"change_pct": 0.0} for _ in range(10)]
    if closes:
        rows[-1] = {"change_pct": closes[-1]}
    return rows


def flat_history_provider(limit_pct=10.0):
    def provider(_code):
        return history(limit_pct)

    return provider


def base_config(**overrides):
    config = {
        "chg_min": 3.0,
        "chg_max": 6.0,
        "turnover_min": 5.0,
        "turnover_max": 15.0,
        "min_limit_ups": 3,
        "history_window": 10,
        "st_only": False,
        "pseudo_concepts": [
            "昨日涨停",
            "最近多板",
            "东方财富热股",
            "题材股",
            "央国企改革",
        ],
    }
    config.update(overrides)
    return config


def sample_inputs():
    stocks = [
        stock("600001", "甲", 10.0, 3.0, market=1),
        stock("600002", "乙", 10.0, 3.0, market=1),
        stock("600003", "丙", 10.0, 3.0, market=1),
        stock("300001", "创业板涨停", 20.0, 3.0, market=0),
        stock("000001", "*ST测试", 3.5, 6.8, market=0),
        stock("600010", "伪甲", 10.0, 3.0, market=1),
        stock("600011", "伪乙", 10.0, 3.0, market=1),
        stock("600012", "伪丙", 10.0, 3.0, market=1),
        stock("000002", "*ST伪", 3.5, 6.8, market=0),
    ]
    concepts = {
        "测试概念": ["sh600001", "sh600002", "sh600003", "sz300001", "sz000001"],
        "昨日涨停": ["sh600010", "sh600011", "sh600012", "sz000002"],
    }
    return stocks, concepts


def test_prefix_code_and_board_classification():
    assert prefix_code("600519", 1) == "sh600519"
    assert prefix_code("000001", 0) == "sz000001"
    assert prefix_code("300750", 0) == "sz300750"
    assert prefix_code("835185", 2) == "bj835185"
    assert prefix_code("920000", 2) == "bj920000"
    assert prefix_code("sh600519") == "sh600519"
    assert board_of("sh600519") == "Main"
    assert board_of("sz300750") == "ChiNext"
    assert board_of("sh688981") == "STAR"
    assert board_of("bj835185") == "BSE"


def test_limit_bounds_and_st_threshold():
    assert limit_bounds(0.10) == (9.5, 11.0)
    assert is_limit_up(9.5, 0.10) is True
    assert is_limit_up(11.0, 0.10) is True
    assert is_limit_up(11.1, 0.10) is False
    assert is_limit_up(9.4, 0.10) is False
    assert is_limit_up(4.5, 0.05) is True
    assert is_limit_up(5.0, 0.05) is True
    assert is_limit_up(4.4, 0.05) is False


def test_limit_ratio_reflects_2026_st_rule_change():
    # 2026-07-06: main-board ST limit is 10%, no longer 5%.
    assert float(limit_ratio("sh600302", "ST标准")) == 0.10
    assert float(limit_ratio("sz002667", "*ST威领")) == 0.10
    assert float(limit_ratio("sz300001", "*ST创业")) == 0.20
    assert float(limit_ratio("sh688001", "*ST科创")) == 0.20
    assert float(limit_ratio("bj835185", "*ST北交")) == 0.30


def test_main_st_five_percent_is_not_sealed_limit_up():
    stock = {
        "code": "sh600302",
        "name": "ST标准",
        "enriched": {
            "real_time": {
                "yestclose": "10.00",
                "price": "10.50",
                "high": "10.50",
            }
        },
    }
    state = execution_state(stock)
    assert state["is_limit_up"] is False
    assert state["is_sealed"] is False
    assert state["limit_up_price"] == 11.0


def test_screen_finds_st_candidate_and_excludes_pseudo_and_growth_boards():
    stocks, concepts = sample_inputs()
    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=flat_history_provider(),
        date="2026-09-15",
    )
    assert result["schema_version"] == SCREEN_SCHEMA_VERSION
    assert result["status"] == "complete"
    assert [c["code"] for c in result["candidates"]] == ["sz000001"]
    assert result["candidates"][0]["limit_up_freq"] == 1
    # ChiNext limit-up does not count toward the main-board concept total and
    # the pseudo trading-state concept is removed.
    assert result["summary"]["qualifying_concept_count"] == 1
    assert result["summary"]["main_non_st_limit_up_count"] == 6
    assert {c["name"] for c in result["concepts"]} == {"测试概念"}
    assert result["concepts"][0]["main_limit_up_count"] == 3
    # Pseudo-concept-only ST name never becomes a candidate.
    assert "sz000002" not in [c["code"] for c in result["candidates"]]


def test_inclusive_endpoints_and_upper_lower_rejection():
    stocks, concepts = sample_inputs()
    stocks.extend(
        [
            stock("000003", "*ST低", 2.9, 6.0),
            stock("000004", "*ST高", 6.1, 6.0),
            stock("000005", "*ST低换", 3.5, 4.9),
            stock("000006", "*ST高换", 3.5, 15.1),
            stock("000007", "*ST端点低", 3.0, 5.0),
            stock("000008", "*ST端点高", 6.0, 15.0),
        ]
    )
    concepts["测试概念"] = concepts["测试概念"] + [
        "sz000003",
        "sz000004",
        "sz000005",
        "sz000006",
        "sz000007",
        "sz000008",
    ]
    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=flat_history_provider(),
        date="2026-09-15",
    )
    codes = {c["code"] for c in result["candidates"]}
    assert codes == {"sz000001", "sz000007", "sz000008"}


def test_history_failure_drops_candidate():
    stocks, concepts = sample_inputs()
    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=lambda _code: None,
        date="2026-09-15",
    )
    assert result["status"] == "empty"
    assert result["candidates"] == []
    assert result["dropped"]["history_failed"] == ["sz000001"]


def test_no_recent_limit_up_is_kept_out():
    stocks, concepts = sample_inputs()

    def provider(_code):
        return history(1.0)

    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=provider,
        date="2026-09-15",
    )
    assert result["candidates"] == []
    assert result["dropped"]["no_recent_limit_up"] == ["sz000001"]


def test_default_includes_normal_and_st():
    stocks, concepts = sample_inputs()
    stocks.append(stock("000009", "普通股", 3.5, 6.8, market=0))
    concepts["测试概念"] = concepts["测试概念"] + ["sz000009"]
    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=flat_history_provider(limit_pct=10.0),
        date="2026-09-15",
    )
    codes = {c["code"] for c in result["candidates"]}
    assert codes == {"sz000001", "sz000009"}


def test_st_only_flag_restricts_candidates_to_st():
    stocks, concepts = sample_inputs()
    stocks.append(stock("000009", "普通股", 3.5, 6.8, market=0))
    concepts["测试概念"] = concepts["测试概念"] + ["sz000009"]
    result = run_screen(
        stocks,
        concepts,
        base_config(st_only=True),
        history_provider=flat_history_provider(limit_pct=10.0),
        date="2026-09-15",
    )
    codes = {c["code"] for c in result["candidates"]}
    assert codes == {"sz000001"}


def test_default_config_excludes_style_and_generic_concepts():
    excluded = set(DEFAULT_CONFIG["pseudo_concepts"])
    assert excluded >= {
        "东方财富热股",
        "题材股",
        "央国企改革",
        "ST股",
        "次新股",
        "融资融券",
        "大盘股",
        "深圳特区",
    }
    # Policy theme explicitly kept by product decision.
    assert "海南自贸" not in excluded


def test_loaded_config_excludes_style_and_generic_concepts():
    from ashare_pilot.screen._commands.limit_up_cluster import load_config

    excluded = set(load_config()["pseudo_concepts"])
    assert len(excluded) >= 100
    assert {"东方财富热股", "题材股", "央国企改革", "深圳特区"} <= excluded
    assert "海南自贸" not in excluded


def test_style_concepts_do_not_form_qualifying_clusters():
    stocks = [
        stock("600001", "甲", 10.0, 3.0, market=1),
        stock("600002", "乙", 10.0, 3.0, market=1),
        stock("600003", "丙", 10.0, 3.0, market=1),
        stock("000001", "普通股", 3.5, 6.8, market=0),
    ]
    concepts = {"央国企改革": ["sh600001", "sh600002", "sh600003", "sz000001"]}
    result = run_screen(
        stocks,
        concepts,
        base_config(),
        history_provider=flat_history_provider(),
        date="2026-09-15",
    )
    assert result["status"] == "empty"
    assert result["summary"]["qualifying_concept_count"] == 0
    assert result["candidates"] == []


def test_build_from_files_unavailable_when_snapshot_missing(tmp_path):
    result = build_from_files("2026-09-15", all_stocks_path=tmp_path / "nope.json")
    assert result["status"] == "unavailable"
    assert "missing snapshot" in result["error"]


def test_render_section_with_candidates_and_none():
    section_none = limit_up_cluster_section(None)
    assert "旁路筛选未运行" in section_none

    section = limit_up_cluster_section(
        {
            "status": "complete",
            "summary": {"qualifying_concept_count": 1, "final_count": 1},
            "snapshot": {"fetched_at": "2026-09-15 14:31:53"},
            "candidates": [
                {
                    "code": "sz002667",
                    "name": "*ST威领",
                    "concepts": ["储能概念"],
                    "turnover": 6.84,
                    "chg_pct": 3.5,
                    "limit_up_freq": 1,
                }
            ],
        }
    )
    assert "自定义筛选 · 涨停簇" in section
    assert "*ST威领" in section
    assert "储能概念" in section
