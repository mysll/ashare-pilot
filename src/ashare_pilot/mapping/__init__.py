"""Candidate pools, evidence, and mapper contracts."""

from ashare_pilot.mapping.api import (
    build_daily_mapper,
    build_scan_pool,
    build_strategy_view,
    compute_quick_score,
    merge_daily_mapper,
    merge_intraday_mapper,
    publish_theme_stocks,
    reasoning_invariant_errors,
    validate_daily_annotations,
    validate_daily_mapper,
    validate_intraday_annotations,
    validate_theme_stocks,
)

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
