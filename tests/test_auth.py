import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.signalk_ha.auth import (
    AccessRequestInfo,
    AccessRequestRejected,
    AccessRequestUnsupported,
    async_create_access_request,
    async_poll_access_request,
)


class _MockResponse:
    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
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
