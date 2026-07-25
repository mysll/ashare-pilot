"""Validated fetch settings for the theme-library data sources."""

from __future__ import annotations

import json
from pathlib import Path

from ashare_pilot.themes.runtime import theme_config_path

DEFAULT_CONCEPT_BOARD_PAGE_SIZE = 50
DEFAULT_CONCEPT_MEMBER_PAGE_SIZE = 50
MAX_EASTMONEY_PAGE_SIZE = 100
DEFAULT_CONCEPT_REQUEST_DELAY: tuple[float, float] = (3.0, 5.0)


def _page_size(settings: dict, key: str, default: int) -> int:
    value = settings.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"fetch_settings.{key} must be an integer")
    if not 1 <= value <= MAX_EASTMONEY_PAGE_SIZE:
        raise ValueError(
            f"fetch_settings.{key} must be between 1 and "
            f"{MAX_EASTMONEY_PAGE_SIZE}"
        )
    return value


def load_fetch_page_sizes(
    config_file: str | Path | None = None,
) -> tuple[int, int]:
    """Return ``(concept board page size, concept member page size)``."""
    path = Path(config_file) if config_file is not None else Path(
        theme_config_path("theme-config.json")
    )
    with open(path, "r", encoding="utf-8") as stream:
        config = json.load(stream)
    settings = config.get("fetch_settings", {})
    if not isinstance(settings, dict):
        raise ValueError("fetch_settings must be an object")
    return (
        _page_size(
            settings,
            "concept_board_page_size",
            DEFAULT_CONCEPT_BOARD_PAGE_SIZE,
        ),
        _page_size(
            settings,
            "concept_member_page_size",
            DEFAULT_CONCEPT_MEMBER_PAGE_SIZE,
        ),
    )


def load_first_page_only(
    config_file: str | Path | None = None,
) -> bool:
    """Return whether to only fetch the first page for all concept members."""
    path = Path(config_file) if config_file is not None else Path(
        theme_config_path("theme-config.json")
    )
    with open(path, "r", encoding="utf-8") as stream:
        config = json.load(stream)
    settings = config.get("fetch_settings", {})
    if not isinstance(settings, dict):
        return False
    value = settings.get("concept_member_first_page_only", False)
    if isinstance(value, bool):
        return value
    if not value:
        return False
    return bool(value)


def load_concept_request_delay(
    config_file: str | Path | None = None,
) -> tuple[float, float]:
    """Return ``(min_delay, max_delay)`` for inter-concept/inter-page waits."""
    path = Path(config_file) if config_file is not None else Path(
        theme_config_path("theme-config.json")
    )
    with open(path, "r", encoding="utf-8") as stream:
        config = json.load(stream)
    settings = config.get("fetch_settings", {})
    if not isinstance(settings, dict):
        return DEFAULT_CONCEPT_REQUEST_DELAY
    value = settings.get("concept_request_delay")
    if isinstance(value, list) and len(value) == 2:
        try:
            lo, hi = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return DEFAULT_CONCEPT_REQUEST_DELAY
        if 0 <= lo <= hi:
            return (lo, hi)
    return DEFAULT_CONCEPT_REQUEST_DELAY
