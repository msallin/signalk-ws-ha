from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import async_timeout
from aiohttp import ClientSession


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
    session: ClientSession, base_url: str, verify_ssl: bool
) -> dict[str, Any]:
    url = urlunsplit(urlsplit(base_url)._replace(path="/signalk/v1/api/vessels/self"))
    ssl_context = None
    if not verify_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    async with async_timeout.timeout(10):
        async with session.get(url, ssl=ssl_context) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if not isinstance(data, dict):
                raise ValueError("vessels/self did not return an object")
            return data
