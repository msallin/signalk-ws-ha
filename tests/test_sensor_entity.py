from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ha.auth import SignalKAuthManager
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


async def test_coordinator_updates_sensor_state(hass, enable_custom_integrations) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    spec = DiscoveredEntity(
        path="navigation.speedOverGround",
        name="Speed Over Ground",
        kind="sensor",
        unit="kn",
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
        description="Speed over ground",
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.speedOverGround": 5.5}
    coordinator._last_update_by_path["navigation.speedOverGround"] = dt_util.utcnow()
    coordinator._last_source_by_path["navigation.speedOverGround"] = "src1"

    sensor = SignalKSensor(coordinator, discovery, entry, spec)

    assert sensor.native_value == 5.5
    assert sensor.available is True
    attrs = sensor.extra_state_attributes
    assert attrs["description"] == "Speed over ground"
    assert attrs["source"] == "src1"
