"""Mapper v3 role convergence, Theme Shadow, and LLM ownership tests."""

from __future__ import annotations

import copy
import pytest

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
        "schema_version": "intraday_mapper_annotations.v3",
        "date": DATE,
        "market_assessment": {
            "regime_hint": "neutral",
            "tomorrow_expectation": "预计震荡",
            "risk_severity": "medium",
            "reasoning_trace": "市场结构中性",
        },
        "executable_annotations": [
            {
                "code": executable_code,
                "tradeability": "Suitable",
                "direction": "谨慎持有",
                "execution_role": "primary",
                "trading_strategy": "趋势跟随",
                "risk_severity": "medium",
                "expected_premium": "次日温和溢价",
                "key_reason": "资金与趋势合格",
                "execution_condition": "竞价和开盘条件均确认后执行",
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
        "strategy": {
            "risk_posture": "light",
            "execution_principle": "只执行完成组合比较后的主选",
            "risk_control": ["条件不满足时不执行"],
            "execution_window": "14:50-14:57",
        },
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


def test_v3_annotations_require_exact_separate_coverage():
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

    assert mapper["schema_version"] == "intraday_mapper.v3"
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


def annotation_errors(base, annotations):
    return validate_annotations(
        annotations,
        DATE,
        {item["code"] for item in base["executable_stocks"]},
        {item["code"] for item in base["observation_stocks"]},
        base,
    )


@pytest.mark.parametrize(
    ("tradeability", "role", "direction", "basis"),
    [
        ("Suitable", "primary", "持有", "ma5"),
        ("Watch", "primary", "谨慎持有", "ma5"),
        ("Watch", "alternative", "观望", "not_applicable"),
        ("Watch", "watch", "观望", "not_applicable"),
    ],
)
def test_valid_role_direction_stop_combinations(
    tradeability, role, direction, basis
):
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note.update(
        tradeability=tradeability,
        execution_role=role,
        direction=direction,
    )
    note["t_plus_1_plan"]["stop_loss_basis"] = basis
    annotations["strategy"]["risk_posture"] = (
        "light" if role == "primary" else "zero"
    )

    assert annotation_errors(base, annotations) == []


@pytest.mark.parametrize(
    ("tradeability", "role", "direction", "basis", "message"),
    [
        ("Watch", "primary", "持有", "ma5", "Watch primary"),
        ("Watch", "alternative", "持有", "ma5", "alternative/watch"),
        ("Watch", "watch", "谨慎持有", "ma5", "alternative/watch"),
        ("Avoid", "primary", "谨慎持有", "ma5", "Extended/Avoid"),
        ("Extended", "alternative", "观望", "not_applicable", "Extended/Avoid"),
        ("Suitable", "primary", "持有", "not_applicable", "structured stop"),
        ("Suitable", "alternative", "观望", "ma5", "not_applicable"),
    ],
)
def test_invalid_role_direction_stop_combinations(
    tradeability, role, direction, basis, message
):
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note.update(
        tradeability=tradeability,
        execution_role=role,
        direction=direction,
    )
    note["t_plus_1_plan"]["stop_loss_basis"] = basis
    annotations["strategy"]["risk_posture"] = (
        "light" if role == "primary" else "zero"
    )

    assert any(message in error for error in annotation_errors(base, annotations))


@pytest.mark.parametrize("value", [None, "invalid"])
def test_execution_role_must_be_explicit_supported_value(value):
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    if value is None:
        note.pop("execution_role")
    else:
        note["execution_role"] = value

    errors = annotation_errors(base, annotations)

    assert any("execution_role" in error for error in errors)


@pytest.mark.parametrize("field", ["position_pct", "position_amount", "lot_count"])
def test_account_sizing_fields_are_forbidden(field):
    base, annotations = base_and_annotations()
    annotations["executable_annotations"][0][field] = 10

    assert any(
        f".{field}: account sizing field not allowed" in error
        for error in annotation_errors(base, annotations)
    )


def test_observation_cannot_contain_execution_role_or_condition():
    base, annotations = base_and_annotations()
    note = annotations["observation_annotations"][0]
    note["execution_role"] = "watch"
    note["execution_condition"] = "等待"

    errors = annotation_errors(base, annotations)

    assert any(".execution_role: execution field not allowed" in e for e in errors)
    assert any(".execution_condition: execution field not allowed" in e for e in errors)


def test_risk_posture_tracks_primary_presence():
    base, annotations = base_and_annotations()
    annotations["strategy"]["risk_posture"] = "zero"
    assert any(
        "must not be zero when primary exists" in error
        for error in annotation_errors(base, annotations)
    )

    note = annotations["executable_annotations"][0]
    note.update(execution_role="watch", direction="观望", tradeability="Watch")
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
    annotations["strategy"]["risk_posture"] = "light"
    assert any(
        "must be zero when no primary exists" in error
        for error in annotation_errors(base, annotations)
    )


def test_empty_executable_requires_zero_risk_posture():
    base, annotations = base_and_annotations()
    base["executable_stocks"] = []
    annotations["executable_annotations"] = []
    annotations["strategy"]["risk_posture"] = "zero"
    assert annotation_errors(base, annotations) == []

    annotations["strategy"]["risk_posture"] = "light"
    assert any(
        "must be zero when no primary exists" in error
        for error in annotation_errors(base, annotations)
    )


def test_mapper_validation_detects_annotation_or_compute_drift():
    base, annotations = base_and_annotations()
    mapper = merge_annotations(base, annotations)
    assert validate_mapper(mapper, DATE, annotations, base) == []

    mapper["executable_stocks"][0]["reasoning"]["execution_condition"] = "篡改"
    assert any(
        "reasoning differs from annotations" in error
        for error in validate_mapper(mapper, DATE, annotations, base)
    )
