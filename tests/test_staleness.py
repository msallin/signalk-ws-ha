from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.util import dt as dt_util
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
    DEFAULT_STALE_SECONDS,
    DOMAIN,
)
from custom_components.signalk_ha.coordinator import ConnectionState, SignalKCoordinator
from custom_components.signalk_ha.discovery import DiscoveredEntity, DiscoveryResult
from custom_components.signalk_ha.sensor import SignalKSensor


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
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


async def test_sensor_staleness_transitions(hass, enable_custom_integrations) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    path = "navigation.speedOverGround"
    spec = DiscoveredEntity(
        path=path,
        name="Speed Over Ground",
        kind="sensor",
        unit="kn",
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock())
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {path: 5.5}

    sensor = SignalKSensor(coordinator, discovery, entry, spec)

    coordinator._last_update_by_path[path] = dt_util.utcnow() - timedelta(
        seconds=DEFAULT_STALE_SECONDS + 1
    )
    assert sensor.available is False

    coordinator._last_update_by_path[path] = dt_util.utcnow()
    assert sensor.available is True
