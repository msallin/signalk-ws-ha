from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import async_timeout
from aiohttp import ClientSession

from .auth import AuthRequired, build_auth_headers, build_ssl_param


@dataclass(frozen=True)
class DiscoveryInfo:
    base_url: str
    ws_url: str
    server_id: str | None
    server_version: str | None


def normalize_base_url(host: str, port: int, use_ssl: bool) -> str:
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{host}:{port}/signalk/v1/api/"


def normalize_ws_url(host: str, port: int, use_ssl: bool) -> str:
    scheme = "wss" if use_ssl else "ws"
    return f"{scheme}://{host}:{port}/signalk/v1/stream?subscribe=none"


def normalize_server_url(host: str, port: int, use_ssl: bool) -> str:
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{host}:{port}"


def normalize_host_input(host: str) -> tuple[str, int | None, str | None]:
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urlsplit(host)
        hostname = (parsed.hostname or "").lower()
        return hostname, parsed.port, parsed.scheme
    return host.lower(), None, None


async def async_fetch_discovery(
    session: ClientSession, server_url: str, verify_ssl: bool
) -> DiscoveryInfo:
    url = urlunsplit(urlsplit(server_url)._replace(path="/signalk", query=""))
    ssl_context = build_ssl_param(verify_ssl)

    async with async_timeout.timeout(5):
        async with session.get(url, ssl=ssl_context) as resp:
            if resp.status in (401, 403):
                raise AuthRequired("Authentication required")
            resp.raise_for_status()
            data = await resp.json()
            if not isinstance(data, dict):
                raise ValueError("Discovery did not return an object")
            return parse_discovery(data)


def parse_discovery(data: dict[str, Any]) -> DiscoveryInfo:
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, dict):
        raise ValueError("Discovery missing endpoints")
    v1 = endpoints.get("v1")
    if not isinstance(v1, dict):
        raise ValueError("Discovery missing endpoints.v1")

    http_base = v1.get("signalk-http")
    ws_stream = v1.get("signalk-ws")
    if not isinstance(http_base, str) or not http_base:
        raise ValueError("Discovery missing endpoints.v1.signalk-http")
    if not isinstance(ws_stream, str) or not ws_stream:
        raise ValueError("Discovery missing endpoints.v1.signalk-ws")

    server = data.get("server") if isinstance(data.get("server"), dict) else {}
    server_id = server.get("id") if isinstance(server, dict) else None
    server_id = server_id if isinstance(server_id, str) and server_id.strip() else None
    server_version = server.get("version") if isinstance(server, dict) else None
    if not isinstance(server_version, str) or not server_version.strip():
        fallback_version = v1.get("version")
        server_version = (
            fallback_version if isinstance(fallback_version, str) and fallback_version else None
        )

    return DiscoveryInfo(
        base_url=_ensure_trailing_slash(http_base),
        ws_url=_ensure_subscribe_none(ws_stream),
        server_id=server_id,
        server_version=server_version,
    )


def _ensure_trailing_slash(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or ""
    if not path.endswith("/"):
        path = f"{path}/"
    return urlunsplit(parsed._replace(path=path))


def _ensure_subscribe_none(url: str) -> str:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if not query.get("subscribe"):
        query["subscribe"] = ["none"]
    new_query = urlencode(query, doseq=True)
    return urlunsplit(parsed._replace(query=new_query))


async def async_fetch_vessel_self(
    session: ClientSession, base_url: str, verify_ssl: bool, token: str | None = None
) -> dict[str, Any]:
    url = urlunsplit(urlsplit(base_url)._replace(path="/signalk/v1/api/vessels/self"))
    ssl_context = build_ssl_param(verify_ssl)
    headers = build_auth_headers(token)

    # Keep REST discovery snappy to avoid blocking HA startup on slow servers.
    async with async_timeout.timeout(5):
        async with session.get(url, ssl=ssl_context, headers=headers) as resp:
            if resp.status in (401, 403):
                raise AuthRequired("Authentication required")
            resp.raise_for_status()
            data = await resp.json()
            if not isinstance(data, dict):
                raise ValueError("vessels/self did not return an object")
            return data
