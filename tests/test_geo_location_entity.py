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
from custom_components.signalk_ha.geo_location import SignalKPositionGeolocation


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


async def test_geo_location_updates(hass, enable_custom_integrations) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    spec = DiscoveredEntity(
        path="navigation.position",
        name="Position",
        kind="geo_location",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=0.00001,
        min_update_seconds=None,
        description="Vessel position",
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()
    coordinator._last_source_by_path["navigation.position"] = "src1"

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)

    assert geo.latitude == 1.0
    assert geo.longitude == 2.0
    assert geo.available is True
    attrs = geo.state_attributes
    assert attrs["description"] == "Vessel position"
    assert attrs["source"] == "src1"
