"""Overnight strategy v2 exact three-view projection tests."""

from __future__ import annotations

import copy

from ashare_pilot.mapping.intraday_contract import merge_annotations
from ashare_pilot.strategy._commands.overnight.build import build
from ashare_pilot.strategy._commands.overnight.render_report import render
from ashare_pilot.strategy._commands.overnight.validate import validate
from tests.unit.test_intraday_mapper_v2 import DATE, base_and_annotations


def actionable_mapper():
    base, annotations = base_and_annotations()
    return merge_annotations(base, annotations)


def test_actionable_executable_and_observation_project_to_exact_views():
    mapper = actionable_mapper()

    strategy = build(mapper)

    assert strategy["schema_version"] == "intraday_overnight_strategy.v2"
    assert len(strategy["recommendations"]) == 1
    assert strategy["eligible_watchlist"] == []
    assert len(strategy["observations"]) == 1
    observation = strategy["observations"][0]
    for field in (
        "direction",
        "tradeability",
        "position_plan",
        "t_plus_1_plan",
    ):
        assert field not in observation
    assert validate(strategy, DATE, mapper) == []


def test_non_actionable_executable_uses_not_applicable_stop():
    base, annotations = base_and_annotations()
    note = annotations["executable_annotations"][0]
    note["direction"] = "观望"
    note["tradeability"] = "Watch"
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
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
    note["t_plus_1_plan"]["stop_loss_basis"] = "not_applicable"
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

    strategy = build(mapper)
    rendered = render(strategy, mapper)

    assert strategy["recommendations"] == []
    assert strategy["eligible_watchlist"] == []
    assert strategy["strategy"]["position_cap"] == "0%"
    assert validate(strategy, DATE, mapper) == []
    assert "无合适执行候选" in rendered
    assert "系统故障" not in rendered


def test_observation_execution_field_is_rejected():
    mapper = actionable_mapper()
    strategy = build(mapper)
    strategy["observations"][0]["direction"] = "持有"

    errors = validate(strategy, DATE, mapper)

    assert "observations[0].direction: forbidden" in errors


def test_theme_shadow_is_rendered_but_rank_tier_is_not_called_buy_grade():
    mapper = actionable_mapper()
    strategy = build(mapper)

    rendered = render(strategy, mapper)

    assert "Theme Shadow" in rendered
    assert "rank tier 仅表示相对排名，不是买入等级" in rendered
