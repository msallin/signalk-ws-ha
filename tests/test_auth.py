import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.signalk_ha.auth import (
    AccessRequestInfo,
    AccessRequestRejected,
    AccessRequestUnsupported,
    AuthRequired,
    SignalKAuthManager,
    _extract_approval_url,
    _extract_request_id,
    _extract_status_url,
    _extract_token,
    _is_rejected,
    _resolve_url,
    async_create_access_request,
    async_fetch_access_request,
    async_poll_access_request,
    build_auth_headers,
    build_ssl_context,
)


class _MockResponse:
    def __init__(self, status: int, payload, headers: dict | None = None) -> None:
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


async def test_access_request_create_success() -> None:
    session = SimpleNamespace()
    session.post = Mock(
        return_value=_MockResponse(
            200,
            {"requestId": "req123", "approvalUrl": "http://sk/approve"},
            headers={"Location": "http://sk/status/req123"},
        )
    )

    request = await async_create_access_request(
        session,
        "http://sk.local:3000/signalk/v1/api/",
        True,
        client_id="signalk:test",
    )

    assert request.request_id == "req123"
    assert request.approval_url == "http://sk/approve"


async def test_access_request_create_unsupported() -> None:
    session = SimpleNamespace()
    session.post = Mock(return_value=_MockResponse(404, {}))

    with pytest.raises(AccessRequestUnsupported):
        await async_create_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            client_id="signalk:test",
        )


async def test_access_request_create_auth_required() -> None:
    session = SimpleNamespace()
    session.post = Mock(return_value=_MockResponse(401, {}))

    with pytest.raises(AuthRequired):
        await async_create_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            client_id="signalk:test",
        )


async def test_access_request_missing_id() -> None:
    session = SimpleNamespace()
    session.post = Mock(return_value=_MockResponse(200, {"approvalUrl": "http://sk/approve"}))

    with pytest.raises(AccessRequestUnsupported):
        await async_create_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            client_id="signalk:test",
        )


async def test_access_request_uses_location_for_id() -> None:
    session = SimpleNamespace()
    session.post = Mock(
        return_value=_MockResponse(
            200,
            {"approvalUrl": "/approve"},
            headers={"Location": "http://sk.local/status/req42"},
        )
    )

    request = await async_create_access_request(
        session,
        "http://sk.local:3000/signalk/v1/api/",
        True,
        client_id="signalk:test",
    )

    assert request.request_id == "req42"
    assert request.approval_url == "http://sk.local:3000/approve"
    assert request.status_url == "http://sk.local/status/req42"


async def test_access_request_non_object_payload() -> None:
    session = SimpleNamespace()
    session.post = Mock(return_value=_MockResponse(200, ["not", "a", "dict"]))

    with pytest.raises(AccessRequestUnsupported):
        await async_create_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            client_id="signalk:test",
        )


async def test_poll_access_request_backoff(monkeypatch) -> None:
    delays: list[float] = []
    now = 0.0

    async def fake_fetch(*args, **kwargs):
        return {"state": "PENDING"}

    async def fake_sleep(delay: float):
        nonlocal now
        delays.append(delay)
        now += delay

    def fake_monotonic():
        return now

    monkeypatch.setattr("custom_components.signalk_ha.auth.async_fetch_access_request", fake_fetch)
    monkeypatch.setattr("custom_components.signalk_ha.auth.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("custom_components.signalk_ha.auth.time.monotonic", fake_monotonic)

    with pytest.raises(asyncio.TimeoutError):
        await async_poll_access_request(
            SimpleNamespace(),
            "http://sk.local:3000/signalk/v1/api/",
            True,
            AccessRequestInfo(request_id="req1", approval_url=None, status_url=None),
            timeout=5,
        )

    assert delays == [1, 2, 5]


async def test_poll_access_request_returns_token(monkeypatch) -> None:
    async def fake_fetch(*args, **kwargs):
        return {"token": "token123"}

    monkeypatch.setattr("custom_components.signalk_ha.auth.async_fetch_access_request", fake_fetch)

    token = await async_poll_access_request(
        SimpleNamespace(),
        "http://sk.local:3000/signalk/v1/api/",
        True,
        AccessRequestInfo(request_id="req1", approval_url=None, status_url=None),
        timeout=5,
    )

    assert token == "token123"


async def test_poll_access_request_rejected(monkeypatch) -> None:
    async def fake_fetch(*args, **kwargs):
        return {"state": "REJECTED"}

    monkeypatch.setattr("custom_components.signalk_ha.auth.async_fetch_access_request", fake_fetch)

    with pytest.raises(AccessRequestRejected):
        await async_poll_access_request(
            SimpleNamespace(),
            "http://sk.local:3000/signalk/v1/api/",
            True,
            AccessRequestInfo(request_id="req1", approval_url=None, status_url=None),
            timeout=5,
        )


async def test_poll_access_request_cancellation(monkeypatch) -> None:
    async def fake_fetch(*args, **kwargs):
        await asyncio.sleep(10)
        return {}

    monkeypatch.setattr("custom_components.signalk_ha.auth.async_fetch_access_request", fake_fetch)

    task = asyncio.create_task(
        async_poll_access_request(
            SimpleNamespace(),
            "http://sk.local:3000/signalk/v1/api/",
            True,
            AccessRequestInfo(request_id="req1", approval_url=None, status_url=None),
            timeout=60,
        )
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_build_auth_headers() -> None:
    assert build_auth_headers(None) is None
    assert build_auth_headers("abc") == {"Authorization": "Bearer abc"}


def test_build_ssl_context() -> None:
    assert build_ssl_context(True) is None
    context = build_ssl_context(False)
    assert context is not None
    assert context.check_hostname is False


def test_extract_request_id_from_href() -> None:
    assert _extract_request_id({"href": "/signalk/v1/access/requests/abc"}) == "abc"


def test_extract_token_nested() -> None:
    token = _extract_token({"nested": {"access_token": "token123"}})
    assert token == "token123"


def test_extract_token_nested_deep() -> None:
    token = _extract_token({"nested": {"inner": {"jwt": "token789"}}})
    assert token == "token789"


def test_extract_token_from_list() -> None:
    token = _extract_token({"items": [{"jwt": "token456"}]})
    assert token == "token456"


def test_extract_token_from_list_nested() -> None:
    token = _extract_token({"items": [{"inner": {"jwtToken": "token999"}}]})
    assert token == "token999"


def test_is_rejected() -> None:
    assert _is_rejected({"state": "REJECTED"}) is True
    assert _is_rejected({"status": "denied"}) is True
    assert _is_rejected({"state": "pending"}) is False


def test_auth_manager_state_transitions() -> None:
    manager = SignalKAuthManager(None)
    manager.update_token("abc")
    assert manager.state.value == "access_granted"
    manager.update_token(None)
    assert manager.state.value == "none"
    manager.mark_failure("failed")
    assert manager.state.value == "failed"
    manager.mark_access_request_active()
    assert manager.state.value == "access_request_pending"


def test_auth_manager_update_token_does_not_clear_failure() -> None:
    manager = SignalKAuthManager(None)
    manager.mark_failure("failed")
    manager.update_token(None)
    assert manager.state.value == "failed"


async def test_fetch_access_request_status_errors() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(403, {}))
    request = AccessRequestInfo(request_id="req1", approval_url=None, status_url=None)

    with pytest.raises(AuthRequired):
        await async_fetch_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            request,
        )


async def test_fetch_access_request_unsupported_status() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(500, {}))
    request = AccessRequestInfo(request_id="req1", approval_url=None, status_url=None)

    with pytest.raises(AccessRequestUnsupported):
        await async_fetch_access_request(
            session,
            "http://sk.local:3000/signalk/v1/api/",
            True,
            request,
        )


async def test_fetch_access_request_success() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(200, {"status": "PENDING"}))
    request = AccessRequestInfo(request_id="req1", approval_url=None, status_url=None)

    data = await async_fetch_access_request(
        session,
        "http://sk.local:3000/signalk/v1/api/",
        True,
        request,
    )
    assert data["status"] == "PENDING"


def test_resolve_url() -> None:
    assert _resolve_url("http://sk.local:3000/signalk/v1/api/", None) is None
    assert (
        _resolve_url("http://sk.local:3000/signalk/v1/api/", "/admin/")
        == "http://sk.local:3000/admin/"
    )


def test_extract_status_url() -> None:
    assert _extract_status_url({"statusUrl": "/status/abc"}) == "/status/abc"


def test_extract_approval_url_invalid() -> None:
    assert _extract_approval_url({"approvalUrl": 123}) is None
