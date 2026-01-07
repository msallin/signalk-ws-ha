from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ha.auth import SignalKAuthManager
from custom_components.signalk_ha.const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_NOTIFICATION_PATHS,
    CONF_PORT,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DOMAIN,
)
from custom_components.signalk_ha.coordinator import ConnectionState, SignalKCoordinator
from custom_components.signalk_ha.event import _notification_event_type, async_setup_entry
from custom_components.signalk_ha.runtime import SignalKRuntimeData


def _make_entry(options=None) -> MockConfigEntry:
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
        options=options or {},
    )


def test_notification_event_type_normalizes() -> None:
    assert _notification_event_type("ALERT") == "alert"
    assert _notification_event_type(None) == "unknown"


async def test_event_entity_updates_on_notification(hass) -> None:
    entry = _make_entry(options={CONF_NOTIFICATION_PATHS: ["notifications.navigation.anchor"]})
    entry.add_to_hass(hass)

    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED

    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=Mock(),
        auth=SignalKAuthManager(None),
    )

    added = []
    await async_setup_entry(hass, entry, added.extend)

    notification = {
        "path": "notifications.navigation.anchor",
        "value": {"state": "alert", "method": ["visual"], "message": "Anchor Alarm"},
        "source": "anchoralarm",
        "timestamp": "2026-01-03T22:34:57.853Z",
    }

    coordinator._fire_notification(notification, coordinator.config)

    assert len(added) == 1
    entity = added[0]
    assert entity.state is not None
    attrs = entity.state_attributes
    assert attrs["event_type"] == "alert"
    assert attrs["path"] == "notifications.navigation.anchor"
    assert attrs["message"] == "Anchor Alarm"
    assert attrs["source"] == "anchoralarm"
    assert attrs["timestamp"] == "2026-01-03T22:34:57.853Z"
    assert attrs["received_at"]
