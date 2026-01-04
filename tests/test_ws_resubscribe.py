import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import WSMsgType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ha.const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_PORT,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DOMAIN,
)
from custom_components.signalk_ha.coordinator import SignalKCoordinator


async def test_subscribe_sent_on_connect(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_VERIFY_SSL: True,
            CONF_BASE_URL: "http://sk.local:3000/signalk/v1/api/",
            CONF_WS_URL: "ws://sk.local:3000/signalk/v1/stream?subscribe=none",
            CONF_VESSEL_ID: "mmsi:261006533",
            CONF_VESSEL_NAME: "ONA",
        },
    )
    entry.add_to_hass(hass)

    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock())
    coordinator._paths = ["navigation.speedOverGround"]
    coordinator._periods = {"navigation.speedOverGround": 1000}

    ws = SimpleNamespace(send_str=AsyncMock(), closed=False)

    async def _receive(timeout=None):
        coordinator._stop_event.set()
        return SimpleNamespace(type=WSMsgType.CLOSED)

    ws.receive = _receive

    @asynccontextmanager
    async def _ws_connect(*args, **kwargs):
        yield ws

    coordinator._session = SimpleNamespace(ws_connect=_ws_connect)

    await coordinator._run()

    ws.send_str.assert_called_once()
    payload = json.loads(ws.send_str.call_args.args[0])
    assert payload["subscribe"][0]["path"] == "navigation.speedOverGround"
