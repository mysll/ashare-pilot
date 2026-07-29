"""Public APIs for deterministic daily and intraday mapping contracts."""

from __future__ import annotations

from typing import Any

from ashare_pilot.mapping._commands.daily.strategy_view import (
    build_view as build_strategy_view,
)
from ashare_pilot.mapping._commands.daily.validate_annotations import (
    validate as validate_daily_annotations,
)
from ashare_pilot.mapping._commands.daily.validate_mapper import (
    check_doc as validate_daily_mapper,
)
from ashare_pilot.mapping._commands.daily.validate_theme_stocks import (
    check_doc as validate_theme_stocks,
)
from ashare_pilot.mapping._commands.intraday.scan_pool import (
    build_scan_pool,
    compute_quick_score,
)
from ashare_pilot.mapping._commands.intraday.validate_annotations import (
    validate as validate_intraday_annotations,
)
from ashare_pilot.mapping.daily_contract import (
    build_deterministic_mapper_base,
    merge_annotations as merge_daily_annotations,
    publish_theme_stocks,
)
from ashare_pilot.mapping.intraday_contract import (
    merge_annotations as merge_intraday_annotations,
    reasoning_invariant_errors,
)


def build_daily_mapper(
    date: str,
    pool: dict[str, dict[str, Any]],
    theme_stocks: dict[str, Any],
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic daily mapper perception layer."""

    return build_deterministic_mapper_base(date, pool, theme_stocks, scope)


def merge_daily_mapper(
    base: dict[str, Any], annotations: dict[str, Any], date: str
) -> dict[str, Any]:
    """Merge validated reasoning annotations into a daily mapper base."""

    return merge_daily_annotations(base, annotations, date)


def merge_intraday_mapper(
    base: dict[str, Any], annotations: dict[str, Any]
) -> dict[str, Any]:
    """Merge validated reasoning annotations into an intraday mapper base."""

    return merge_intraday_annotations(base, annotations)


__all__ = [
    "build_daily_mapper",
    "build_scan_pool",
    "build_strategy_view",
    "compute_quick_score",
    "merge_daily_mapper",
    "merge_intraday_mapper",
    "publish_theme_stocks",
    "reasoning_invariant_errors",
    "validate_daily_annotations",
    "validate_daily_mapper",
    "validate_intraday_annotations",
    "validate_theme_stocks",
]
