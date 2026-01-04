from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.signalk_ha.auth import AuthRequired
from custom_components.signalk_ha.rest import (
    async_fetch_vessel_self,
    normalize_host_input,
)


class _MockResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"{self.status}")

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


async def test_async_fetch_vessel_self_success() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(200, {"name": "ONA"}))

    data = await async_fetch_vessel_self(
        session, "http://sk.local:3000/signalk/v1/api/", True, token=None
    )
    assert data["name"] == "ONA"


async def test_async_fetch_vessel_self_auth_required() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(401, {}))

    with pytest.raises(AuthRequired):
        await async_fetch_vessel_self(
            session, "http://sk.local:3000/signalk/v1/api/", True, token=None
        )


async def test_async_fetch_vessel_self_non_object() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(200, ["not", "dict"]))

    with pytest.raises(ValueError):
        await async_fetch_vessel_self(
            session, "http://sk.local:3000/signalk/v1/api/", True, token=None
        )


def test_normalize_host_input() -> None:
    host, port, scheme = normalize_host_input("https://Example.com:1234")
    assert host == "example.com"
    assert port == 1234
    assert scheme == "https"

    host, port, scheme = normalize_host_input("SK.LOCAL")
    assert host == "sk.local"
    assert port is None
    assert scheme is None
