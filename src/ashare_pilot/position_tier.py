"""Qualitative position intent shared by morning and intraday workflows."""

from __future__ import annotations

POSITION_TIERS = {"WATCH_ONLY", "LIGHT", "STANDARD"}
POSITION_TIER_RANK = {"WATCH_ONLY": 0, "LIGHT": 1, "STANDARD": 2}
POSITION_TIER_LABELS = {
    "WATCH_ONLY": "仅观察",
    "LIGHT": "轻仓",
    "STANDARD": "标准仓",
}


def lower_position_tier(value: str) -> str:
    if value == "STANDARD":
        return "LIGHT"
    return "WATCH_ONLY"
