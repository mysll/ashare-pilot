from __future__ import annotations

import requests

from ashare_pilot import http_settings
from ashare_pilot.market_data._datasources.eastmoney import EastMoneyDataSource
from ashare_pilot.market_data._datasources.intraday import (
    EastMoneyIntradayDataSource,
)
from ashare_pilot.themes.datasource import EastMoneyConceptSource


CHROME_120_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
FIREFOX_121_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
    "Gecko/20100101 Firefox/121.0"
)


def test_configured_session_ignores_environment_without_config(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://environment.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://environment.invalid:8080")
    monkeypatch.setattr(http_settings, "load_http_proxies", lambda: None)

    session = http_settings.configured_session()
    merged = session.merge_environment_settings(
        "https://example.invalid", {}, stream=False, verify=True, cert=None
    )

    assert session.trust_env is False
    assert session.proxies == {}
    assert merged["proxies"] == {}


def test_configured_session_uses_only_config_proxy(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://environment.invalid:8080")
    configured = {
        "http": "http://configured.invalid:7890",
        "https": "http://configured.invalid:7890",
    }
    monkeypatch.setattr(http_settings, "load_http_proxies", lambda: configured)

    session = http_settings.configured_session()

    assert session.trust_env is False
    assert session.proxies == configured


def test_http_get_discards_caller_proxy_override(monkeypatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.trust_env = True
            self.proxies: dict[str, str] = {}
            self.kwargs = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url, **kwargs):
            self.kwargs = kwargs
            return object()

    fake = FakeSession()
    monkeypatch.setattr(requests, "Session", lambda: fake)
    monkeypatch.setattr(http_settings, "load_http_proxies", lambda: None)

    http_settings.http_get(
        "https://example.invalid",
        proxies={"https": "http://caller.invalid:8080"},
    )

    assert fake.trust_env is False
    assert fake.proxies == {}
    assert "proxies" not in fake.kwargs


def test_chromium_client_hints_match_version_and_platform() -> None:
    hints = http_settings.browser_client_hint_headers(CHROME_120_MAC)

    assert '"Chromium";v="120"' in hints["sec-ch-ua"]
    assert '"Google Chrome";v="120"' in hints["sec-ch-ua"]
    assert hints["sec-ch-ua-platform"] == '"macOS"'
    assert hints["sec-ch-ua-mobile"] == "?0"


def test_firefox_does_not_send_chromium_client_hints() -> None:
    assert http_settings.browser_client_hint_headers(FIREFOX_121_WINDOWS) == {}


def test_all_eastmoney_header_builders_use_matching_client_hints(
    monkeypatch,
) -> None:
    intraday = EastMoneyIntradayDataSource()
    eastmoney = EastMoneyDataSource()
    concept = EastMoneyConceptSource()
    for source in (intraday, eastmoney, concept):
        monkeypatch.setattr(source, "_get_random_ua", lambda: CHROME_120_MAC)

    headers = [
        intraday._get_push2_headers(),
        eastmoney._get_push2_headers(),
        eastmoney._get_stock_money_flow_headers(),
        concept._get_push2_headers(),
    ]

    for value in headers:
        assert value["user-agent"] == CHROME_120_MAC
        assert '"Chromium";v="120"' in value["sec-ch-ua"]
        assert value["sec-ch-ua-platform"] == '"macOS"'


def test_all_eastmoney_header_builders_omit_hints_for_firefox(
    monkeypatch,
) -> None:
    intraday = EastMoneyIntradayDataSource()
    eastmoney = EastMoneyDataSource()
    concept = EastMoneyConceptSource()
    for source in (intraday, eastmoney, concept):
        monkeypatch.setattr(source, "_get_random_ua", lambda: FIREFOX_121_WINDOWS)

    headers = [
        intraday._get_push2_headers(),
        eastmoney._get_push2_headers(),
        eastmoney._get_stock_money_flow_headers(),
        concept._get_push2_headers(),
    ]

    for value in headers:
        assert value["user-agent"] == FIREFOX_121_WINDOWS
        assert not any(key.startswith("sec-ch-ua") for key in value)
