import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.signalk_ha.auth import AuthRequired
from custom_components.signalk_ha.rest import (
    async_fetch_discovery,
    async_fetch_vessel_self,
    normalize_host_input,
    normalize_server_url,
    parse_discovery,
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


def test_parse_discovery_success() -> None:
    data = {
        "endpoints": {
            "v1": {
                "signalk-http": "http://sk.local:3000/signalk/v1/api/",
                "signalk-ws": "ws://sk.local:3000/signalk/v1/stream",
                "version": "2.0.0",
            }
        },
        "server": {"id": "signalk-server-node", "version": "2.1.0"},
    }
    info = parse_discovery(data)
    assert info.base_url.endswith("/signalk/v1/api/")
    assert info.ws_url.endswith("subscribe=none")
    assert info.server_id == "signalk-server-node"
    assert info.server_version == "2.1.0"


def test_parse_discovery_from_file() -> None:
    data = Path("tests/discovery_testdata.json").read_text(encoding="utf-8")
    info = parse_discovery(json.loads(data))
    assert info.base_url.endswith("/signalk/v1/api/")
    assert info.ws_url.startswith("wss://")
    assert info.ws_url.endswith("subscribe=none")
    assert info.server_id == "signalk-server-node"
    assert info.server_version == "2.19.0"


def test_parse_discovery_missing_endpoints_v1() -> None:
    with pytest.raises(ValueError):
        parse_discovery({"endpoints": {}})


def test_parse_discovery_fallback_version() -> None:
    data = {
        "endpoints": {
            "v1": {
                "signalk-http": "http://sk.local:3000/signalk/v1/api/",
                "signalk-ws": "ws://sk.local:3000/signalk/v1/stream",
                "version": "2.0.0",
            }
        },
        "server": {"id": "signalk-server-node"},
    }
    info = parse_discovery(data)
    assert info.server_version == "2.0.0"


async def test_async_fetch_discovery_success() -> None:
    payload = {
        "endpoints": {
            "v1": {
                "signalk-http": "http://sk.local:3000/signalk/v1/api/",
                "signalk-ws": "ws://sk.local:3000/signalk/v1/stream",
                "version": "2.0.0",
            }
        },
        "server": {"id": "signalk-server-node", "version": "2.1.0"},
    }
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(200, payload))

    server_url = normalize_server_url("sk.local", 3000, False)
    info = await async_fetch_discovery(session, server_url, True)
    assert info.server_id == "signalk-server-node"


async def test_async_fetch_discovery_http_error() -> None:
    session = SimpleNamespace()
    session.get = Mock(return_value=_MockResponse(500, {}))

    server_url = normalize_server_url("sk.local", 3000, False)
    with pytest.raises(RuntimeError):
        await async_fetch_discovery(session, server_url, True)
