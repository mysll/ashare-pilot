"""Composable command registration for the unified CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from ashare_pilot.automation.cli import register_cli as register_automation
from ashare_pilot.indicators.cli import register_cli as register_indicators
from ashare_pilot.mapping.cli import register_cli as register_mapping
from ashare_pilot.market_data.cli import register_cli as register_market_data
from ashare_pilot.news.cli import register_cli as register_news
from ashare_pilot.operations.cli import register_cli as register_operations
from ashare_pilot.review.cli import register_cli as register_review
from ashare_pilot.strategy.cli import register_cli as register_strategy
from ashare_pilot.themes.cli import register_cli as register_themes

CommandRegistrar = Callable[[argparse._SubParsersAction], None]

COMMAND_REGISTRARS: tuple[CommandRegistrar, ...] = (
    register_market_data,
    register_news,
    register_indicators,
    register_themes,
    register_mapping,
    register_strategy,
    register_operations,
    register_review,
    register_automation,
)


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    for register in COMMAND_REGISTRARS:
        register(subparsers)
