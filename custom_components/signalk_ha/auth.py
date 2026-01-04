from __future__ import annotations

import asyncio
import ssl
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import async_timeout
from aiohttp import ClientSession
from homeassistant.util import dt as dt_util

_AUTH_POLL_DELAYS = (1, 2, 5, 10)
_AUTH_TIMEOUT_SECONDS = 120


class AuthRequired(Exception):
    """Signal K server requires authentication."""


class AccessRequestError(Exception):
    """Access request failed."""


class AccessRequestUnsupported(AccessRequestError):
    """Access requests are not supported."""


class AccessRequestRejected(AccessRequestError):
    """Access request was rejected."""


class AuthState(str, Enum):
    NONE = "none"
    ACCESS_REQUEST_PENDING = "access_request_pending"
    ACCESS_GRANTED = "access_granted"
    FAILED = "failed"


@dataclass(frozen=True)
class AccessRequestInfo:
    request_id: str
    approval_url: str | None
    status_url: str | None


class SignalKAuthManager:
    def __init__(self, token: str | None) -> None:
        self._token = token
        self._state = AuthState.ACCESS_GRANTED if token else AuthState.NONE
        self._access_request_active = False
        self._last_error: str | None = None
        self._last_success = None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def token_present(self) -> bool:
        return bool(self._token)

    @property
    def state(self) -> AuthState:
        return self._state

    @property
    def access_request_active(self) -> bool:
        return self._access_request_active

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def last_success(self):
        return self._last_success

    def update_token(self, token: str | None) -> None:
        self._token = token
        if token:
            self._state = AuthState.ACCESS_GRANTED
        elif self._state != AuthState.FAILED:
            self._state = AuthState.NONE

    def mark_success(self) -> None:
        self._last_success = dt_util.utcnow()
        self._last_error = None
        self._access_request_active = False
        self._state = AuthState.ACCESS_GRANTED if self._token else AuthState.NONE

    def mark_failure(self, message: str) -> None:
        self._last_error = message[:200] if message else "auth failed"
        self._state = AuthState.FAILED

    def mark_access_request_active(self) -> None:
        self._access_request_active = True
        self._state = AuthState.ACCESS_REQUEST_PENDING


def build_auth_headers(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def build_ssl_param(verify_ssl: bool) -> ssl.SSLContext | bool | None:
    """Return the aiohttp ssl parameter for the current TLS verification setting."""
    if verify_ssl:
        return None
    return False


async def async_create_access_request(
    session: ClientSession,
    base_url: str,
    verify_ssl: bool,
    *,
    client_id: str,
    description: str = "Home Assistant Signal K integration",
) -> AccessRequestInfo:
    url = _access_requests_url(base_url)
    payload = {
        "clientId": client_id,
        "description": description,
        "permissions": [
            {
                "context": "vessels.self",
                "resources": [
                    {
                        "path": "*",
                        "read": True,
                        "write": False,
                    }
                ],
            }
        ],
    }

    ssl_context = build_ssl_param(verify_ssl)
    location = None
    async with async_timeout.timeout(10):
        async with session.post(url, ssl=ssl_context, json=payload) as resp:
            if resp.status in (401, 403):
                raise AuthRequired("Access requests require authentication")
            if resp.status >= 400:
                raise AccessRequestUnsupported(f"Access request failed: {resp.status}")
            data = await _safe_json(resp)
            location = resp.headers.get("Location")

    request_id = _extract_request_id(data)
    approval_url = _extract_approval_url(data)
    status_url = _extract_status_url(data) or location

    if not request_id and status_url:
        request_id = _extract_request_id({"href": status_url})

    if not request_id:
        raise AccessRequestUnsupported("Access request did not return an id")

    return AccessRequestInfo(
        request_id=request_id,
        approval_url=_resolve_url(base_url, approval_url) if approval_url else None,
        status_url=_resolve_url(base_url, status_url) if status_url else None,
    )


async def async_poll_access_request(
    session: ClientSession,
    base_url: str,
    verify_ssl: bool,
    request: AccessRequestInfo,
    timeout: int = _AUTH_TIMEOUT_SECONDS,
) -> str:
    start = time.monotonic()
    delay_index = 0
    while True:
        data = await async_fetch_access_request(session, base_url, verify_ssl, request)
        token = _extract_token(data)
        if token:
            return token
        if _is_rejected(data):
            raise AccessRequestRejected("Access request rejected")

        if time.monotonic() - start >= timeout:
            raise asyncio.TimeoutError()

        delay = _AUTH_POLL_DELAYS[min(delay_index, len(_AUTH_POLL_DELAYS) - 1)]
        delay_index += 1
        await asyncio.sleep(delay)


async def async_fetch_access_request(
    session: ClientSession,
    base_url: str,
    verify_ssl: bool,
    request: AccessRequestInfo,
) -> dict[str, Any]:
    url = request.status_url or _access_request_status_url(base_url, request.request_id)
    ssl_context = build_ssl_param(verify_ssl)
    async with async_timeout.timeout(10):
        async with session.get(url, ssl=ssl_context) as resp:
            if resp.status in (401, 403):
                raise AuthRequired("Access request status requires authentication")
            if resp.status >= 400:
                raise AccessRequestUnsupported(f"Access request status failed: {resp.status}")
            data = await _safe_json(resp)
            return data


async def _safe_json(resp) -> dict[str, Any]:
    data = await resp.json()
    if not isinstance(data, dict):
        raise AccessRequestUnsupported("Access request response was not a JSON object")
    return data


def _access_requests_url(base_url: str) -> str:
    return urlunsplit(urlsplit(base_url)._replace(path="/signalk/v1/access/requests", query=""))


def _access_request_status_url(base_url: str, request_id: str) -> str:
    return urlunsplit(
        urlsplit(base_url)._replace(path=f"/signalk/v1/access/requests/{request_id}", query="")
    )


def _resolve_url(base_url: str, url: str | None) -> str | None:
    if not url:
        return None
    return urljoin(base_url, url)


def _extract_request_id(data: dict[str, Any]) -> str | None:
    for key in ("requestId", "request_id", "id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    href = data.get("href") or data.get("statusUrl") or data.get("url")
    if isinstance(href, str):
        parts = href.rstrip("/").split("/")
        if parts:
            return parts[-1]
    return None


def _extract_approval_url(data: dict[str, Any]) -> str | None:
    for key in ("approvalUrl", "approval_url", "href", "url"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_status_url(data: dict[str, Any]) -> str | None:
    for key in ("statusUrl", "status_url", "status", "href"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_token(data: dict[str, Any]) -> str | None:
    token_keys = ("token", "accessToken", "access_token", "jwt", "jwtToken")
    for key in token_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in data.values():
        found = _extract_token_from_value(value, token_keys)
        if found:
            return found
    return None


def _extract_token_from_value(value: Any, token_keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in token_keys:
            token = value.get(key)
            if isinstance(token, str) and token.strip():
                return token.strip()
        for nested in value.values():
            token = _extract_token_from_value(nested, token_keys)
            if token:
                return token
    elif isinstance(value, list):
        for item in value:
            token = _extract_token_from_value(item, token_keys)
            if token:
                return token
    return None


def _is_rejected(data: dict[str, Any]) -> bool:
    status = data.get("state") or data.get("status")
    if isinstance(status, str) and status.lower() in ("rejected", "denied", "revoked"):
        return True
    return False
