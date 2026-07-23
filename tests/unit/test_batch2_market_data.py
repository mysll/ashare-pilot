from __future__ import annotations

from pathlib import Path

from ashare_pilot.market_data._commands import auth
from ashare_pilot.market_data._datasources import kline_cache
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def make_workspace(path: Path) -> Workspace:
    path.mkdir()
    (path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (path / "config").mkdir()
    return Workspace(path.resolve())


def test_default_kline_cache_is_scoped_to_explicit_workspace(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "workspace")
    records = [{"date": "2026-07-21", "close": "10.00"}]

    with use_workspace(workspace):
        kline_cache.save_cache("sh600000", records, source="fixture")
        loaded = kline_cache.load_cache("sh600000", source="fixture")

    assert loaded is not None
    assert loaded["records"] == records
    assert (workspace.cache_dir / "kline" / "fixture" / "sh600000.json").is_file()


def test_cookie_formatters_preserve_legacy_contract() -> None:
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

    assert auth.format_cookies_simple(cookies) == "session=redacted"
    assert "\tTRUE\t/\tTRUE\t0\tsession\tredacted" in auth.format_cookies_netscape(cookies)
