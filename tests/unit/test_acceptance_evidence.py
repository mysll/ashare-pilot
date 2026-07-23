from __future__ import annotations

import re
from pathlib import Path

from tests.equivalence.acceptance_evidence import ENTRY_EVIDENCE


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "core-refactor-acceptance-matrix.md"
ENTRY_ID = re.compile(r"^\| ((?:MD|IN|NW|TH|MP|ST|OP|RV|AU)\d{2}) ", re.MULTILINE)


def test_every_matrix_entry_has_all_five_evidence_categories() -> None:
    matrix_ids = set(ENTRY_ID.findall(MATRIX.read_text(encoding="utf-8")))

    assert len(matrix_ids) == 68
    assert set(ENTRY_EVIDENCE) == matrix_ids
    for item in ENTRY_EVIDENCE.values():
        assert item.normal
        assert item.boundary
        assert item.failure
        assert item.cli
        assert item.api


def test_every_registered_test_node_exists() -> None:
    for item in ENTRY_EVIDENCE.values():
        for reference in {
            *item.normal,
            *item.boundary,
            *item.failure,
            *item.cli,
            *item.api,
        }:
            path_text, test_name = reference.split("::", 1)
            path = ROOT / path_text
            assert path.is_file(), reference
            assert f"def {test_name}(" in path.read_text(encoding="utf-8"), reference
