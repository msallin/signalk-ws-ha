from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import async_timeout
from aiohttp import ClientSession

from .auth import AuthRequired, build_auth_headers, build_ssl_param


def normalize_base_url(host: str, port: int, use_ssl: bool) -> str:
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{host}:{port}/signalk/v1/api/"


def normalize_ws_url(host: str, port: int, use_ssl: bool) -> str:
    scheme = "wss" if use_ssl else "ws"
    return f"{scheme}://{host}:{port}/signalk/v1/stream?subscribe=none"


def normalize_host_input(host: str) -> tuple[str, int | None, str | None]:
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urlsplit(host)
        hostname = (parsed.hostname or "").lower()
        return hostname, parsed.port, parsed.scheme
    return host.lower(), None, None


async def async_fetch_vessel_self(
    session: ClientSession, base_url: str, verify_ssl: bool, token: str | None = None
) -> dict[str, Any]:
    url = urlunsplit(urlsplit(base_url)._replace(path="/signalk/v1/api/vessels/self"))
    ssl_context = build_ssl_param(verify_ssl)
    headers = build_auth_headers(token)

    async with async_timeout.timeout(10):
        async with session.get(url, ssl=ssl_context, headers=headers) as resp:
            if resp.status in (401, 403):
                raise AuthRequired("Authentication required")
            resp.raise_for_status()
            data = await resp.json()
            if not isinstance(data, dict):
                raise ValueError("vessels/self did not return an object")
            return data
