from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ashare_pilot.mapping import daily_contract, intraday_contract
from ashare_pilot.mapping._commands.daily import validate_annotations as daily_validator
from ashare_pilot.mapping._commands.intraday import scan_pool
from ashare_pilot.mapping._commands.intraday import validate_annotations as intraday_validator

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "mapping"


def load_old(name: str, path: Path, aliases: dict[str, object] | None = None):
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    previous = {}
    for alias, module in (aliases or {}).items():
        previous[alias] = sys.modules.get(alias)
        sys.modules[alias] = module
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for alias in aliases or {}:
            if previous[alias] is None:
                sys.modules.pop(alias, None)
            else:
                sys.modules[alias] = previous[alias]


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_daily_mapper_contract_and_candidate_order_match_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = load_old(
        "legacy_daily_contract_batch4",
        ROOT / ".agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py",
    )
    data = fixture("daily_contract.json")
    monkeypatch.setattr(old, "utc_now_iso", lambda: "2026-07-14T06:30:00+00:00")
    monkeypatch.setattr(daily_contract, "utc_now_iso", lambda: "2026-07-14T06:30:00+00:00")

    old_base = old.build_deterministic_mapper_base(
        data["date"], copy.deepcopy(data["pool"]), copy.deepcopy(data["theme_stocks"])
    )
    new_base = daily_contract.build_deterministic_mapper_base(
        data["date"], copy.deepcopy(data["pool"]), copy.deepcopy(data["theme_stocks"])
    )
    assert new_base == old_base

    old_final = old.merge_annotations(old_base, copy.deepcopy(data["annotations"]), data["date"])
    new_final = daily_contract.merge_annotations(new_base, copy.deepcopy(data["annotations"]), data["date"])
    assert new_final == old_final
    assert [row["code"] for row in new_final["candidate_pool"]] == ["sz000001"]


def test_daily_validation_error_order_and_text_match_legacy() -> None:
    old_contract = load_old(
        "legacy_daily_contract_for_validation_batch4",
        ROOT / ".agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py",
    )
    old_validator = load_old(
        "legacy_daily_validator_batch4",
        ROOT / ".agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py",
        {"mapper_json_lib": old_contract},
    )
    invalid = {
        "schema_version": "wrong",
        "date": "2026-07-13",
        "themes": [{"name": "银行"}, {"name": "银行"}],
        "stocks": [{"code": "bad"}, {"code": "bad"}],
    }

    assert daily_validator.validate(invalid, {"sz000001"}) == old_validator.validate(
        invalid, {"sz000001"}
    )


def test_intraday_merge_and_validation_match_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_contract = load_old(
        "legacy_intraday_contract_batch4",
        ROOT / ".agents/skills/intraday-strategy/scripts/intraday_mapper_json_lib.py",
    )
    old_validator = load_old(
        "legacy_intraday_validator_batch4",
        ROOT / ".agents/skills/intraday-strategy/scripts/validate_intraday_mapper_annotations.py",
        {"intraday_mapper_json_lib": old_contract},
    )
    data = fixture("intraday_contract.json")
    monkeypatch.setattr(old_contract, "utc_now_iso", lambda: "2026-07-14T06:30:00+00:00")
    monkeypatch.setattr(intraday_contract, "utc_now_iso", lambda: "2026-07-14T06:30:00+00:00")

    old_result = old_contract.merge_annotations(
        copy.deepcopy(data["base"]), copy.deepcopy(data["annotations"])
    )
    new_result = intraday_contract.merge_annotations(
        copy.deepcopy(data["base"]), copy.deepcopy(data["annotations"])
    )
    assert new_result == old_result

    allowed = {"sz000001"}
    assert intraday_validator.validate(
        data["annotations"], data["date"], allowed, data["base"]
    ) == old_validator.validate(data["annotations"], data["date"], allowed, data["base"])


def test_scan_pool_scoring_and_order_match_legacy() -> None:
    old = load_old(
        "legacy_scan_pool_batch4",
        ROOT / ".agents/skills/intraday-market-scan/scripts/build_scan_pool.py",
    )
    rows = [
        {"code": "sz000001", "change_pct": "+3.0%", "amount": "100", "turnover": "8%", "volume_ratio": "2"},
        {"code": "sh600000", "change_pct": "+6.0%", "amount": "200", "turnover": "12%", "volume_ratio": "1.2"},
    ]
    for index, row in enumerate(rows):
        row["source_pool"] = "limit_up" if index == 0 else "turnover"

    assert scan_pool.compute_quick_score(copy.deepcopy(rows)) == old.compute_quick_score(
        copy.deepcopy(rows)
    )


def test_json_serialization_has_identical_content_hash(tmp_path: Path) -> None:
    old = load_old(
        "legacy_daily_writer_batch4",
        ROOT / ".agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py",
    )
    value = {"schema_version": "hash.v1", "stocks": [{"code": "sz000001", "name": "平安银行"}]}
    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    old.write_json(old_path, value)
    daily_contract.write_json(new_path, value)

    assert hashlib.sha256(new_path.read_bytes()).hexdigest() == hashlib.sha256(
        old_path.read_bytes()
    ).hexdigest()
