"""Global HTTP settings loaded from config/setting.json."""

from __future__ import annotations

import json
import socket
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import requests

from ashare_pilot.workspace import resolve_workspace


def setting_json_path() -> str:
    return str(resolve_workspace().root / "config" / "setting.json")


def load_http_proxies() -> dict[str, str] | None:
    """Return requests proxies if config/setting.json has a non-empty proxy."""
    return _load_http_proxies(setting_json_path())


@lru_cache(maxsize=8)
def _load_http_proxies(path: str) -> dict[str, str] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(config, dict):
        return None

    http = config.get("http") or {}
    if not isinstance(http, dict):
        return None

    proxies = http.get("proxies")
    if isinstance(proxies, dict):
        cleaned = {
            str(scheme): str(url).strip()
            for scheme, url in proxies.items()
            if str(url).strip()
        }
        return cleaned or None

    proxy = http.get("proxy")
    if not isinstance(proxy, str):
        return None
    proxy = proxy.strip()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def request_proxies() -> dict[str, str] | None:
    """Proxies dict for a single requests call, or None to use defaults."""
    return load_http_proxies()


def proxy_endpoint(proxy_url: str) -> tuple[str, int] | None:
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return None
    return parsed.hostname, parsed.port


def check_proxy_reachable(proxies: dict[str, str] | None = None) -> str:
    """Return a short status string for the configured HTTP proxy."""
    proxies = proxies if proxies is not None else load_http_proxies()
    if not proxies:
        return "disabled"
    proxy_url = proxies.get("https") or proxies.get("http") or ""
    endpoint = proxy_endpoint(proxy_url)
    if endpoint is None:
        return f"invalid:{proxy_url}"
    host, port = endpoint
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return f"reachable:{host}:{port}"
    except OSError as exc:
        return f"unreachable:{host}:{port}:{exc}"


def http_get(url: str, **kwargs: Any) -> requests.Response:
    """requests.get with optional proxy from config/setting.json."""
    if "proxies" not in kwargs:
        proxies = load_http_proxies()
        if proxies is not None:
            kwargs["proxies"] = proxies
    return requests.get(url, **kwargs)


def apply_session_proxies(session: requests.Session) -> None:
    """Apply config proxy to a requests.Session when configured."""
    proxies = load_http_proxies()
    if proxies is not None:
        session.proxies.clear()
        session.proxies.update(proxies)
        # Prefer explicit config over HTTP(S)_PROXY / NO_PROXY env.
        session.trust_env = False


def describe_proxy_for_request(
    session: requests.Session, url: str
) -> str:
    """Return the effective proxy URL requests would use for *url*."""
    proxies = load_http_proxies()
    if proxies is None:
        return "none"
    try:
        merged = session.merge_environment_settings(
            url, proxies, stream=False, verify=True, cert=None
        )
        effective = merged.get("proxies") or {}
    except Exception:
        effective = proxies
    scheme = "https" if url.startswith("https://") else "http"
    return str(effective.get(scheme) or effective.get(scheme.rstrip("s")) or effective or "none")
