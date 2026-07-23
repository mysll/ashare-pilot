from __future__ import annotations

import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
MANIFEST = FIXTURES / "manifest.json"


def test_fixture_manifest_covers_every_versioned_fixture() -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = document["fixtures"]
    declared = {entry["path"] for entry in entries}
    actual = {
        path.relative_to(FIXTURES).as_posix()
        for path in FIXTURES.rglob("*")
        if path.is_file()
        and path.name not in {".gitkeep", "manifest.json"}
        and "__pycache__" not in path.parts
    }

    assert declared == actual
    assert len(declared) == len(entries)


def test_fixture_manifest_has_complete_provenance_and_no_sensitive_paths() -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    serialized = json.dumps(document, ensure_ascii=False).lower()
    for forbidden in ("cookie=", "password", "eastmoney_username", "/home/", "c:\\users\\"):
        assert forbidden not in serialized

    for entry in document["fixtures"]:
        date.fromisoformat(entry["source_date"])
        assert entry["legacy_commands"]
        assert entry["scenario"].strip()
        assert entry["provenance"].strip()
