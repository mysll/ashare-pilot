"""Reusable builders for the frozen intraday selection-pool cases."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "intraday"
    / "selection_pools_v1_cases.json"
)


def load_selection_pool_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _assign_dotted(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def build_selection_case(case_id: str) -> dict[str, Any]:
    """Materialize a frozen case, including deterministic boundary variants."""
    fixture = load_selection_pool_fixture()
    cases = {
        case["id"]: case
        for case in fixture["cases"]
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    if case_id not in cases:
        raise KeyError(case_id)
    case = copy.deepcopy(cases[case_id])
    if isinstance(case.get("stock"), dict):
        return case

    patch = case.get("stock_patch")
    if not isinstance(patch, dict) or not isinstance(patch.get("base_case"), str):
        raise ValueError(f"case {case_id} has neither stock nor valid stock_patch")
    base = build_selection_case(patch["base_case"])
    stock = copy.deepcopy(base["stock"])
    for key, value in patch.items():
        if key != "base_case":
            _assign_dotted(stock, key, value)
    case["stock"] = stock
    return case
