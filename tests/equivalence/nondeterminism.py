"""Central allowlist for approved non-deterministic equivalence fields."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AllowedField:
    path: tuple[str, ...]
    reason: str


APPROVED_NONDETERMINISTIC_FIELDS: dict[str, tuple[AllowedField, ...]] = {
    "concept_dashboard": (
        AllowedField(
            ("meta", "timestamp"),
            "The legacy and new builders sample wall-clock time independently.",
        ),
    ),
    "daily_verification": (
        AllowedField(
            ("generated_at",),
            "The verification contract records the wall-clock generation time.",
        ),
    ),
}


def normalize_nondeterminism(value: Any, contract: str) -> Any:
    """Return a deep copy with only centrally approved fields removed."""

    if contract not in APPROVED_NONDETERMINISTIC_FIELDS:
        raise KeyError(f"unknown non-determinism contract: {contract}")
    result = copy.deepcopy(value)
    for allowed in APPROVED_NONDETERMINISTIC_FIELDS[contract]:
        parent = result
        for part in allowed.path[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                raise AssertionError(
                    f"approved non-deterministic path is absent: {'.'.join(allowed.path)}"
                )
            parent = parent[part]
        leaf = allowed.path[-1]
        if not isinstance(parent, dict) or leaf not in parent:
            raise AssertionError(
                f"approved non-deterministic path is absent: {'.'.join(allowed.path)}"
            )
        del parent[leaf]
    return result
