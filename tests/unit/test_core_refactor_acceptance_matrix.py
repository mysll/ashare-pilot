from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "core-refactor-acceptance-matrix.md"
MIGRATION_MAP = ROOT / "docs" / "core-refactor-migration-map.md"

ENTRY_ROW = re.compile(
    r"^\| (?P<id>(?:MD|IN|NW|TH|MP|ST|OP|RV|AU)\d{2}) "
    r"\| `(?P<legacy>[^`]+\.py)` \| `(?P<cli>[^`]+)` \|",
    re.MULTILINE,
)
MAPPED_ROW = re.compile(
    r"^\| `(?P<legacy>[^`]+\.py)` \|(?: `[^`]+` \|)? `(?P<cli>[^`]+)` \|$",
    re.MULTILINE,
)


def basename(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def test_acceptance_matrix_has_one_unique_row_for_every_mapped_entry() -> None:
    matrix_rows = ENTRY_ROW.findall(MATRIX.read_text(encoding="utf-8"))
    mapped_rows = MAPPED_ROW.findall(MIGRATION_MAP.read_text(encoding="utf-8"))

    assert len(matrix_rows) == 68
    assert len(mapped_rows) == 68
    assert len({entry_id for entry_id, _, _ in matrix_rows}) == 68
    assert len({cli for _, _, cli in matrix_rows}) == 68
    assert {(basename(legacy), cli) for _, legacy, cli in matrix_rows} == {
        (basename(legacy), cli) for legacy, cli in mapped_rows
    }


def test_acceptance_matrix_summary_matches_rows() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    rows = ENTRY_ROW.findall(text)
    pass_count = sum(
        1
        for line in text.splitlines()
        if ENTRY_ROW.match(line) and line.endswith("| PASS |")
    )

    assert f"- 旧运行入口：{len(rows)}。" in text
    assert f"- 唯一新 CLI：{len({cli for _, _, cli in rows})}。" in text
    assert f"- 当前 `PASS`：{pass_count}。" in text
    assert f"- 当前 `OPEN`：{len(rows) - pass_count}。" in text


def test_final_acceptance_has_no_open_entry() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    entry_lines = [line for line in text.splitlines() if ENTRY_ROW.match(line)]

    assert len(entry_lines) == 68
    assert all(line.endswith("| PASS |") for line in entry_lines)
    assert "- 当前 `PASS`：68。" in text
    assert "- 当前 `OPEN`：0。" in text
