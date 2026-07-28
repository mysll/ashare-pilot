"""Overnight strategy v3 exact role-driven projection tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ashare_pilot.mapping.intraday_contract import merge_annotations
from ashare_pilot.strategy._commands.overnight.build import build
from ashare_pilot.strategy._commands.overnight.render_report import render
from ashare_pilot.strategy._commands.overnight.validate import validate
from tests.unit.test_intraday_mapper_v3 import DATE, base_and_annotations


def actionable_mapper():
    base, annotations = base_and_annotations()
    return merge_annotations(base, annotations)


def test_actionable_executable_and_observation_project_to_exact_views():
    mapper = actionable_mapper()

    strategy = build(mapper)

    assert strategy["schema_version"] == "intraday_overnight_strategy.v3"
    assert len(strategy["recommendations"]) == 1
    assert strategy["eligible_watchlist"] == []
    assert len(strategy["observations"]) == 1
    observation = strategy["observations"][0]
    for field in (
        "direction",
        "tradeability",
        "execution_role",
        "execution_condition",
        "t_plus_1_plan",
    ):
        assert field not in observation
    assert validate(strategy, DATE, mapper) == []


def test_non_actionable_executable_uses_not_applicable_stop():
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note["direction"] = "观望"
    note["tradeability"] = "Watch"
    note["execution_role"] = "watch"
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
    annotations["strategy"]["risk_posture"] = "zero"
    mapper = merge_annotations(base, annotations)

    strategy = build(mapper)

    assert strategy["recommendations"] == []
    assert len(strategy["eligible_watchlist"]) == 1
    assert (
        strategy["eligible_watchlist"][0]["t_plus_1_plan"]
        ["stop_loss_basis"]
        == "not_applicable"
    )
    assert validate(strategy, DATE, mapper) == []


def test_alternative_and_watch_project_only_to_eligible_watchlist():
    for role in ("alternative", "watch"):
        base, annotations = base_and_annotations()
        note = annotations["executable_annotations"][0]
        note.update(
            direction="观望",
            tradeability="Watch",
            execution_role=role,
        )
        note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
        annotations["strategy"]["risk_posture"] = "zero"
        mapper = merge_annotations(base, annotations)

        strategy = build(mapper)

        assert strategy["recommendations"] == []
        assert strategy["eligible_watchlist"][0]["execution_role"] == role
        assert validate(strategy, DATE, mapper) == []


def test_three_views_must_exactly_cover_mapper_pools():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["observations"] = []

    errors = validate(strategy, DATE, mapper)

    assert "observations must exactly cover observation pool" in errors


def test_executable_view_must_exactly_match_mapper_projection():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["recommendations"][0]["overnight_score"] = -1

    errors = validate(strategy, DATE, mapper)

    assert (
        "recommendations[0]: must exactly match mapper projection"
        in errors
    )


def test_observation_view_must_exactly_match_mapper_projection():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["observations"][0]["observation_reasons"] = ["altered"]

    errors = validate(strategy, DATE, mapper)

    assert "observations[0]: must exactly match mapper projection" in errors


def test_eligible_watchlist_rejects_unknown_direction():
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note["direction"] = "观望"
    note["tradeability"] = "Watch"
    note["execution_role"] = "watch"
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
    annotations["strategy"]["risk_posture"] = "zero"
    mapper = merge_annotations(base, annotations)
    strategy = build(mapper)
    strategy["eligible_watchlist"][0]["direction"] = "bogus"

    errors = validate(strategy, DATE, mapper)

    assert (
        "eligible_watchlist[0].direction must be one of ['观望']"
        in errors
    )


def test_empty_executable_pool_is_zero_position_and_normal_html():
    mapper = actionable_mapper()
    mapper["executable_stocks"] = []
    mapper["annotation_coverage"]["executable"] = {
        "expected": 0,
        "annotated": 0,
    }
    mapper["strategy"]["risk_posture"] = "zero"

    strategy = build(mapper)
    rendered = render(strategy, mapper)

    assert strategy["recommendations"] == []
    assert strategy["eligible_watchlist"] == []
    assert strategy["strategy"]["risk_posture"] == "zero"
    assert validate(strategy, DATE, mapper) == []
    assert "无合适执行候选" in rendered
    assert "系统故障" not in rendered


def test_observation_execution_field_is_rejected():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["observations"][0]["direction"] = "持有"

    errors = validate(strategy, DATE, mapper)

    assert "observations[0].direction: forbidden" in errors


def test_theme_shadow_is_rendered_but_rank_tier_is_hidden_from_html():
    mapper = actionable_mapper()
    strategy = build(mapper)

    rendered = render(strategy, mapper)

    assert "Theme Shadow" in rendered
    assert "Rank Tier" not in rendered
    assert "rank tier" not in rendered
    assert "rank_tier" not in rendered


def test_v3_report_preserves_established_decision_terminal_layout():
    mapper = actionable_mapper()
    rendered = render(build(mapper), mapper)

    for heading in (
        "隔夜策略决策看板",
        "市场判断 / Market Regime",
        "执行策略总览",
        "重点个股执行计划",
        "组合风控",
        "观察池",
        "明日关键关注",
    ):
        assert heading in rendered
    assert "交易板" not in rendered


def test_role_and_risk_posture_tampering_is_rejected():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["recommendations"][0]["execution_role"] = "watch"
    strategy["strategy"]["risk_posture"] = "zero"

    errors = validate(strategy, DATE, mapper)

    assert any("execution_role must be primary" in error for error in errors)
    assert any("must not be zero with recommendations" in error for error in errors)


def test_removed_account_sizing_fields_are_rejected():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["recommendations"][0]["position_pct"] = 10

    assert any(
        "removed account sizing field" in error
        for error in validate(strategy, DATE, mapper)
    )


def test_html_displays_v3_roles_conditions_and_qualitative_posture():
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note.update(
        direction="观望",
        tradeability="Watch",
        execution_role="alternative",
        execution_condition="仅在主选失效后重新评估",
    )
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
    annotations["strategy"]["risk_posture"] = "zero"
    mapper = merge_annotations(base, annotations)

    rendered = render(build(mapper), mapper)

    assert "备选" in rendered
    assert "暂不执行，仅作为替代" in rendered
    assert "仅在主选失效后重新评估" in rendered
    assert "风险姿态" in rendered
    assert "仓位上限" not in rendered
    assert "position_plan" not in rendered


def test_primary_is_labeled_primary_and_counted_once():
    mapper = actionable_mapper()

    rendered = render(build(mapper), mapper)

    assert "主选 · 谨慎持有" in rendered
    assert '<div class="big-number">1<small> 只</small></div>' in rendered


def test_strategy_overview_keeps_compact_single_line_layout():
    mapper = actionable_mapper()

    rendered = render(build(mapper), mapper)

    overview = rendered.split("执行策略总览", 1)[1].split(
        "重点个股执行计划", 1
    )[0]
    assert "<th>执行角色</th>" not in overview
    assert "<th>尾盘决策</th>" in overview
    assert "<th>开盘动作</th>" not in overview
    assert "<th>核心理由</th>" in overview
    assert "谨慎持有" in overview
    assert ">主选<" not in overview
    assert "<th>执行条件</th>" not in overview
    assert '<table class="overview-table">' in overview
    assert ".overview-table .reason{max-width:520px}" in rendered
    assert ".action,.reason{max-width:290px;overflow:hidden;" in rendered
    assert "text-overflow:ellipsis;white-space:nowrap" in rendered


def test_20260728_frozen_regression_records_v2_bulk_projection_and_v3_convergence():
    fixture_path = (
        Path(__file__).parents[1]
        / "fixtures"
        / "strategy"
        / "intraday_convergence_2026-07-28.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["executable_count"] == 30
    assert len(fixture["legacy_v2_actionable_codes"]) == 10
    assert set(fixture["v3_primary_codes"]) < set(
        fixture["legacy_v2_actionable_codes"]
    )
    assert len(fixture["v3_alternative_codes"]) == 2
    assert (
        len(fixture["v3_primary_codes"])
        + len(fixture["v3_alternative_codes"])
        + fixture["v3_watch_count"]
        == fixture["executable_count"]
    )
    assert fixture["risk_posture"] == "very_light"
