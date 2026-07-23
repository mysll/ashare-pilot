from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ashare_pilot.indicators._commands import calculate, pool_enrich, pool_fetch

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "indicators" / "history.json"


def load_old(name: str, path: Path):
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def records() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]


def invoke_old(module, args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [module.__name__, *args])
    code = 0
    try:
        module.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def invoke_new(module, args, capsys):
    code = 0
    try:
        module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_all_indicator_formulas_match_legacy(records: list) -> None:
    old = load_old(
        "legacy_fetch_indicators",
        ROOT / ".opencode" / "lib" / "fetch" / "fetch_indicators.py",
    )
    names = list(old.INDICATORS)

    assert calculate.calculate_indicators(records, names) == old.calculate_indicators(
        records, names
    )


def test_calculate_cli_json_is_equivalent(
    records: list,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = load_old(
        "legacy_indicator_cli",
        ROOT / ".opencode" / "lib" / "fetch" / "fetch_indicators.py",
    )
    monkeypatch.setattr(old, "fetch_history", lambda *a, **kw: copy.deepcopy(records))
    monkeypatch.setattr(calculate, "fetch_history", lambda *a, **kw: copy.deepcopy(records))
    args = ["sh600000", "--indicators", "rsi,macd,boll", "--json"]

    old_result = invoke_old(old, args, monkeypatch, capsys)
    new_result = invoke_new(calculate, args, capsys)

    assert new_result == old_result


def test_pool_fetch_json_contract_is_equivalent(
    records: list,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = load_old(
        "legacy_pool_indicators",
        ROOT / ".opencode" / "skills" / "daily-stock-mapping" / "scripts" / "fetch_pool_indicators.py",
    )
    monkeypatch.setattr(old, "fetch_history", lambda *a, **kw: copy.deepcopy(records))
    monkeypatch.setattr(pool_fetch, "fetch_history", lambda *a, **kw: copy.deepcopy(records))

    old_result = invoke_old(old, ["sh600000", "--json"], monkeypatch, capsys)
    new_result = invoke_new(pool_fetch, ["sh600000", "--json"], capsys)

    assert old_result[0] == new_result[0] == 0
    assert json.loads(old_result[1]) == json.loads(new_result[1])


def test_pool_enrichment_contract_is_equivalent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = load_old(
        "legacy_enrich_technicals",
        ROOT / ".opencode" / "skills" / "intraday-stock-discovery" / "scripts" / "enrich_technicals.py",
    )
    input_path = tmp_path / "pool.json"
    input_path.write_text(
        json.dumps({"compute_pool": [{"code": "sh600000", "price": "12.00"}]}),
        encoding="utf-8",
    )
    technicals = {
        "ma5": 11.8,
        "boll_zone": "upper_half",
        "ma_alignment": "bullish",
        "above_ma5": True,
    }
    monkeypatch.setattr(old, "_fetch_and_compute", lambda *a: technicals)
    monkeypatch.setattr(pool_enrich, "_fetch_and_compute", lambda *a: technicals)

    old_result = invoke_old(old, [str(input_path), "--json"], monkeypatch, capsys)
    new_result = invoke_new(pool_enrich, [str(input_path), "--json"], capsys)

    assert old_result[0] == new_result[0] == 0
    assert json.loads(old_result[1]) == json.loads(new_result[1])
