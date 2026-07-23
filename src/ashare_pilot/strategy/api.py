"""Public APIs for deterministic strategy computation and contracts."""

from __future__ import annotations

from typing import Any

from ashare_pilot.strategy._commands.daily.finalize import materialize, validate_draft
from ashare_pilot.strategy._commands.daily.llm_input import build_input as build_daily_llm_input
from ashare_pilot.strategy._commands.daily.normalize_selection import normalize as normalize_selection
from ashare_pilot.strategy._commands.daily.render_report import render_report as render_daily_report
from ashare_pilot.strategy._commands.daily.trade_profile import compute_trade_profile
from ashare_pilot.strategy._commands.daily.validate_strategy import validate as validate_daily_strategy
from ashare_pilot.strategy._commands.overnight.build import build as build_overnight_strategy
from ashare_pilot.strategy._commands.overnight.render_report import render as render_overnight_report
from ashare_pilot.strategy._commands.overnight.score import compute_scores
from ashare_pilot.strategy._commands.overnight.validate import validate as validate_overnight_strategy


def finalize_daily_strategy(
    draft: dict[str, Any], compact_input: dict[str, Any]
) -> dict[str, Any]:
    """Materialize a validated selected-only LLM draft into the final contract."""

    return materialize(draft, compact_input)


__all__ = [
    "build_daily_llm_input",
    "build_overnight_strategy",
    "compute_scores",
    "compute_trade_profile",
    "finalize_daily_strategy",
    "normalize_selection",
    "render_daily_report",
    "render_overnight_report",
    "validate_daily_strategy",
    "validate_draft",
    "validate_overnight_strategy",
]
