"""Mapper v2 separation, Theme Shadow, and LLM ownership tests."""

from __future__ import annotations

import copy

from ashare_pilot.mapping._commands.intraday.validate_annotations import (
    validate as validate_annotations,
)
from ashare_pilot.mapping._commands.intraday.validate_mapper import (
    validate as validate_mapper,
)
from ashare_pilot.mapping.intraday_contract import (
    attach_theme_evidence,
    build_theme_support_shadow,
    merge_annotations,
)
from ashare_pilot.strategy.intraday_selection import build_selection_pools
from tests.intraday_selection_fixtures import build_selection_case


DATE = "2026-07-27"


def stock(case_id: str) -> dict:
    return copy.deepcopy(build_selection_case(case_id)["stock"])


def base_and_annotations():
    executable = stock("i14_cautious_hold")
    executable["enriched"]["real_time"]["price"] = 31.3
    executable["enriched"]["real_time"]["vwap"] = 30.0
    observation = stock("vwap_missing")
    pools = build_selection_pools(
        [executable, observation],
        configured_min_inflow_yuan=5_000_000,
        regime={"i14_active": False},
    )
    base = {
        "schema_version": "intraday_mapper_base.v2",
        "date": DATE,
        "market": {},
        "themes": {},
        "pool_summary": pools["pool_summary"],
        "executable_stocks": attach_theme_evidence(
            pools["executable_pool"], {}, {}
        ),
        "observation_stocks": attach_theme_evidence(
            pools["observation_pool"], {}, {}
        ),
    }
    executable_code = base["executable_stocks"][0]["code"]
    observation_code = base["observation_stocks"][0]["code"]
    annotations = {
        "schema_version": "intraday_mapper_annotations.v2",
        "date": DATE,
        "market_assessment": {"reasoning_trace": "市场结构中性"},
        "executable_annotations": [
            {
                "code": executable_code,
                "tradeability": "Suitable",
                "direction": "谨慎持有",
                "trading_strategy": "趋势跟随",
                "risk_severity": "medium",
                "expected_premium": "次日温和溢价",
                "key_reason": "资金与趋势合格",
                "position_plan": "小仓位",
                "t_plus_1_plan": {
                    "auction_condition": "竞价不弱",
                    "open_strategy": "确认后持有",
                    "stop_loss_basis": "ma5",
                    "take_profit": "冲高分批止盈",
                },
                "rules_applied": [],
                "reasoning_trace": "仅消费确定性事实",
            }
        ],
        "observation_annotations": [
            {
                "code": observation_code,
                "observation_summary": "VWAP 缺失，仅观察",
                "watch_condition": "数据恢复后重评",
                "risk_note": "禁止生成仓位",
            }
        ],
        "strategy": {"position_cap": "20%"},
    }
    return base, annotations


def test_theme_shadow_complete_and_missing_states_never_invent_neutral_values():
    relations = [
        {"name": "AI算力", "member_role": "core", "weight": 1.0}
    ]
    ranking = {
        "theme_ranking": [
            {"theme": "AI算力", "core_heat": 82.4, "diffusion_heat": 46.1}
        ]
    }

    complete = build_theme_support_shadow(relations, "AI算力", ranking)
    missing = build_theme_support_shadow(relations, "AI算力", {"theme_ranking": []})

    assert complete == {
        "available": True,
        "primary_theme": "AI算力",
        "member_role": "core",
        "membership_weight": 1.0,
        "core_heat": 82.4,
        "diffusion_heat": 46.1,
        "theme_rank": 1,
        "missing_reason": None,
    }
    assert missing["available"] is False
    assert missing["missing_reason"] == "primary_theme_not_in_top15"
    assert missing["core_heat"] is None
    assert missing["diffusion_heat"] is None


def test_v2_annotations_require_exact_separate_coverage():
    base, annotations = base_and_annotations()
    executable_codes = {base["executable_stocks"][0]["code"]}
    observation_codes = {base["observation_stocks"][0]["code"]}

    assert (
        validate_annotations(
            annotations,
            DATE,
            executable_codes,
            observation_codes,
            base,
        )
        == []
    )
    annotations["observation_annotations"] = []
    errors = validate_annotations(
        annotations,
        DATE,
        executable_codes,
        observation_codes,
        base,
    )
    assert any("exact coverage mismatch" in error for error in errors)


def test_observation_annotation_rejects_every_execution_field():
    base, annotations = base_and_annotations()
    annotations["observation_annotations"][0]["direction"] = "持有"

    errors = validate_annotations(
        annotations,
        DATE,
        {base["executable_stocks"][0]["code"]},
        {base["observation_stocks"][0]["code"]},
        base,
    )

    assert any(
        "observation_annotations[0].direction: execution field not allowed"
        in error
        for error in errors
    )


def test_mapper_merge_keeps_reasoning_in_its_owned_pool_and_validates():
    base, annotations = base_and_annotations()

    mapper = merge_annotations(base, annotations)

    assert mapper["schema_version"] == "intraday_mapper.v2"
    assert "stocks" not in mapper
    assert "reasoning" in mapper["executable_stocks"][0]
    assert "observation_reasoning" not in mapper["executable_stocks"][0]
    assert "observation_reasoning" in mapper["observation_stocks"][0]
    assert "reasoning" not in mapper["observation_stocks"][0]
    assert validate_mapper(mapper, DATE) == []


def test_execution_state_tampering_is_recomputed_and_rejected():
    base, annotations = base_and_annotations()
    base["executable_stocks"][0]["execution_state"]["eligible"] = False

    errors = validate_annotations(
        annotations,
        DATE,
        {base["executable_stocks"][0]["code"]},
        {base["observation_stocks"][0]["code"]},
        base,
    )

    assert any("execution_state differs" in error for error in errors)
