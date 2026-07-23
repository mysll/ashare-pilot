from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from ashare_pilot.market_data._commands import (
    board_money_flow,
    breadth,
    concept_ranking,
    history,
    limit_up_pool,
    money_flow,
    quote,
    special,
    stocks_all,
    turnover_ranking,
)
from ashare_pilot.market_data._datasources.sina import SinaDataSource
from ashare_pilot.market_data._commands import auth

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "market_data"
OLD_FETCH = ROOT / ".opencode" / "lib" / "fetch"


def load_old(name: str, filename: str) -> ModuleType:
    path = OLD_FETCH / filename
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def results() -> dict:
    return json.loads((FIXTURES / "batch2_cli_results.json").read_text(encoding="utf-8"))


def invoke_old(
    module: ModuleType,
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", [module.__name__, *args])
    code = 0
    try:
        module.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def invoke_new(
    module: ModuleType,
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = 0
    try:
        module.main(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    ("filename", "new_module", "function_name", "fixture_key", "args"),
    [
        ("fetch_stock.py", quote, "fetch_stocks", "quote", ["sh600000", "--json"]),
        ("fetch_history.py", history, "fetch_history", "history", ["sh600000", "--json"]),
        ("fetch_all_astocks.py", stocks_all, "fetch_all_astocks", "stocks_all", ["--json"]),
        ("fetch_money_flow.py", money_flow, "fetch_money_flow", "money_flow", ["--json"]),
        ("fetch_special.py", special, "fetch_lhb", "special", ["lhb", "--json"]),
    ],
)
def test_function_backed_cli_output_is_equivalent(
    filename: str,
    new_module: ModuleType,
    function_name: str,
    fixture_key: str,
    args: list[str],
    results: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_module = load_old(f"legacy_{filename.removesuffix('.py')}", filename)
    value = results[fixture_key]
    monkeypatch.setattr(old_module, function_name, lambda *a, **kw: value)
    monkeypatch.setattr(new_module, function_name, lambda *a, **kw: value)

    old_result = invoke_old(old_module, args, monkeypatch, capsys)
    new_result = invoke_new(new_module, args, capsys)

    assert new_result == old_result


@pytest.mark.parametrize(
    ("filename", "new_module", "method", "fixture_key", "args"),
    [
        ("fetch_market_breadth.py", breadth, "fetch_market_breadth", "breadth", ["--json"]),
        ("fetch_board_money_flow.py", board_money_flow, "fetch_board_money_flow_by_field", "board_money_flow", ["concept", "--json"]),
        ("fetch_concept_ranking.py", concept_ranking, "fetch_concept_ranking", "concept_ranking", ["--json"]),
        ("fetch_turnover_ranking.py", turnover_ranking, "fetch_turnover_ranking", "turnover_ranking", ["--json"]),
        ("fetch_limit_up_pool.py", limit_up_pool, "fetch_limit_up_pool", "limit_up_pool", ["--json"]),
    ],
)
def test_datasource_backed_cli_output_is_equivalent(
    filename: str,
    new_module: ModuleType,
    method: str,
    fixture_key: str,
    args: list[str],
    results: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_module = load_old(f"legacy_{filename.removesuffix('.py')}", filename)
    value = results[fixture_key]
    fake = SimpleNamespace(**{method: lambda *a, **kw: value})
    monkeypatch.setattr(old_module, "_ds", fake)
    monkeypatch.setattr(new_module, "_ds", fake)

    old_result = invoke_old(old_module, args, monkeypatch, capsys)
    new_result = invoke_new(new_module, args, capsys)

    assert new_result == old_result


@pytest.mark.parametrize(
    ("filename", "new_module", "function_name", "args"),
    [
        ("fetch_stock.py", quote, "fetch_stocks", ["sh600000", "--json"]),
        ("fetch_history.py", history, "fetch_history", ["sh600000", "--json"]),
        ("fetch_all_astocks.py", stocks_all, "fetch_all_astocks", ["--json"]),
        ("fetch_money_flow.py", money_flow, "fetch_money_flow", ["--json"]),
        ("fetch_special.py", special, "fetch_lhb", ["lhb", "--json"]),
    ],
)
def test_function_backed_empty_boundary_is_equivalent(
    filename: str,
    new_module: ModuleType,
    function_name: str,
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_module = load_old(f"legacy_empty_{filename.removesuffix('.py')}", filename)
    monkeypatch.setattr(old_module, function_name, lambda *a, **kw: [])
    monkeypatch.setattr(new_module, function_name, lambda *a, **kw: [])

    assert invoke_new(new_module, args, capsys) == invoke_old(
        old_module, args, monkeypatch, capsys
    )


@pytest.mark.parametrize(
    ("filename", "new_module", "method", "args", "empty"),
    [
        ("fetch_market_breadth.py", breadth, "fetch_market_breadth", ["--json"], {}),
        ("fetch_board_money_flow.py", board_money_flow, "fetch_board_money_flow_by_field", ["concept", "--json"], []),
        ("fetch_concept_ranking.py", concept_ranking, "fetch_concept_ranking", ["--json"], []),
        ("fetch_turnover_ranking.py", turnover_ranking, "fetch_turnover_ranking", ["--json"], []),
        ("fetch_limit_up_pool.py", limit_up_pool, "fetch_limit_up_pool", ["--json"], []),
    ],
)
def test_datasource_backed_empty_boundary_is_equivalent(
    filename: str,
    new_module: ModuleType,
    method: str,
    args: list[str],
    empty: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_module = load_old(f"legacy_empty_{filename.removesuffix('.py')}", filename)
    fake = SimpleNamespace(**{method: lambda *a, **kw: empty})
    monkeypatch.setattr(old_module, "_ds", fake)
    monkeypatch.setattr(new_module, "_ds", fake)

    assert invoke_new(new_module, args, capsys) == invoke_old(
        old_module, args, monkeypatch, capsys
    )


def test_recorded_sina_response_parses_equivalently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = json.loads(
        (FIXTURES / "sina_quote_response.json").read_text(encoding="utf-8")
    )
    old_module = load_old("legacy_sina_parser", "fetch_stock.py")
    old_source = old_module.SinaDataSource()
    new_source = SinaDataSource()
    monkeypatch.setattr(old_source, "_request_with_retry", lambda *a, **kw: fixture["response_text"])
    monkeypatch.setattr(new_source, "_request_with_retry", lambda *a, **kw: fixture["response_text"])

    assert old_source.fetch_quotes(["sh600000"]) == fixture["expected"]
    assert new_source.fetch_quotes(["sh600000"]) == fixture["expected"]


def test_empty_all_stocks_failure_is_equivalent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old_module = load_old("legacy_empty_all_stocks", "fetch_all_astocks.py")
    monkeypatch.setattr(old_module, "fetch_all_astocks", lambda *a, **kw: [])
    monkeypatch.setattr(stocks_all, "fetch_all_astocks", lambda *a, **kw: [])

    old_result = invoke_old(old_module, [], monkeypatch, capsys)
    new_result = invoke_new(stocks_all, [], capsys)

    assert new_result == old_result == (
        1,
        "No data fetched. API may be rate-limited.\n",
        "",
    )


def test_cookie_serialization_is_equivalent() -> None:
    legacy_path = ROOT / ".opencode" / "scripts" / "get_cookie.py"
    if not legacy_path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location(
        "legacy_get_cookie_batch2", legacy_path
    )
    assert spec and spec.loader
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    cookies = [
        {
            "domain": ".example.invalid",
            "path": "/",
            "secure": True,
            "expires": 0,
            "name": "session",
            "value": "redacted",
        }
    ]

    assert auth.format_cookies_simple(cookies) == old.format_cookies_simple(cookies)
    assert auth.format_cookies_netscape(cookies) == old.format_cookies_netscape(cookies)
    assert auth.format_cookies_simple([]) == old.format_cookies_simple([]) == ""
    assert auth.format_cookies_netscape([]) == old.format_cookies_netscape([])
