"""Global HTTP settings loaded from config/setting.json."""

from __future__ import annotations

import json
import re
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
    """Return the project-configured proxies, or None for a direct connection."""
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
    """GET using only proxy settings from config/setting.json."""
    kwargs.pop("proxies", None)
    with configured_session() as session:
        return session.get(url, **kwargs)


def apply_session_proxies(session: requests.Session) -> None:
    """Make config/setting.json the session's only proxy source."""
    session.trust_env = False
    session.proxies.clear()
    proxies = load_http_proxies()
    if proxies is not None:
        session.proxies.update(proxies)


def configured_session() -> requests.Session:
    """Create a Session that never reads proxy settings from the environment."""
    session = requests.Session()
    apply_session_proxies(session)
    return session


def describe_proxy_for_request(
    session: requests.Session, url: str
) -> str:
    """Return the config-selected proxy URL for *url*, or ``none``."""
    proxies = load_http_proxies()
    if proxies is None:
        return "none"
    scheme = "https" if url.startswith("https://") else "http"
    return str(proxies.get(scheme) or proxies.get(scheme.rstrip("s")) or "none")


_CHROME_VERSION = re.compile(r"(?:Chrome|Chromium)/(\d+)")


def browser_client_hint_headers(user_agent: str) -> dict[str, str]:
    """Build Client Hints consistent with a Chromium user agent.

    Firefox and other non-Chromium user agents must not send Chromium-only
    ``sec-ch-ua`` headers.
    """
    match = _CHROME_VERSION.search(user_agent)
    if match is None:
        return {}

    version = match.group(1)
    if "Windows" in user_agent:
        platform = "Windows"
    elif "Macintosh" in user_agent or "Mac OS X" in user_agent:
        platform = "macOS"
    elif "Linux" in user_agent:
        platform = "Linux"
    else:
        platform = "Unknown"

    return {
        "sec-ch-ua": (
            f'"Not;A=Brand";v="8", "Chromium";v="{version}", '
            f'"Google Chrome";v="{version}"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{platform}"',
    }
