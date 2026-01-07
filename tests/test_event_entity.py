from unittest.mock import Mock

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
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
from custom_components.signalk_ha.event import (
    _humanize_segment,
    _notification_attributes,
    _notification_event_type,
    _notification_name,
    async_setup_entry,
)
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


def test_notification_name_humanizes() -> None:
    assert _humanize_segment("speedOverGround") == "Speed Over Ground"
    assert _notification_name("notifications.navigation.anchor") == "Navigation Anchor Notification"
    assert _notification_name("notifications") == "Notification"


def test_notification_attributes_formats_received_at() -> None:
    received_at = dt_util.utcnow()
    attrs = _notification_attributes(
        {
            "path": "notifications.navigation.anchor",
            "state": "alert",
            "message": "Anchor Alarm",
            "received_at": received_at,
        }
    )
    assert attrs["path"] == "notifications.navigation.anchor"
    assert attrs["received_at"] == dt_util.as_utc(received_at).isoformat()


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


async def test_event_listener_skips_disabled_entity(hass) -> None:
    entry = _make_entry(options={CONF_NOTIFICATION_PATHS: ["notifications.*"]})
    entry.add_to_hass(hass)

    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED

    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=Mock(),
        auth=SignalKAuthManager(None),
    )

    registry = er.async_get(hass)
    unique_id = f"signalk:{entry.entry_id}:notifications.navigation.anchor"
    registry.async_get_or_create(
        "event",
        DOMAIN,
        unique_id,
        suggested_object_id="anchor",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    added: list = []
    await async_setup_entry(hass, entry, added.extend)

    notification = {
        "path": "notifications.navigation.anchor",
        "value": {"state": "alert"},
        "timestamp": dt_util.utcnow().isoformat(),
    }

    coordinator._fire_notification(notification, coordinator.config)
    assert added == []


async def test_event_listener_creates_entity_for_wildcard(hass) -> None:
    entry = _make_entry(options={CONF_NOTIFICATION_PATHS: ["notifications.*"]})
    entry.add_to_hass(hass)

    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED

    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=Mock(),
        auth=SignalKAuthManager(None),
    )

    added: list = []
    await async_setup_entry(hass, entry, added.extend)

    notification = {
        "path": "notifications.navigation.anchor",
        "value": {"state": "alert"},
        "timestamp": "2026-01-03T22:34:57.853Z",
    }

    coordinator._fire_notification(notification, coordinator.config)
    assert len(added) == 1


async def test_event_listener_creates_after_reenable(hass) -> None:
    entry = _make_entry(options={CONF_NOTIFICATION_PATHS: ["notifications.*"]})
    entry.add_to_hass(hass)

    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED

    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=Mock(),
        auth=SignalKAuthManager(None),
    )

    registry = er.async_get(hass)
    unique_id = f"signalk:{entry.entry_id}:notifications.navigation.anchor"
    disabled_id = registry.async_get_or_create(
        "event",
        DOMAIN,
        unique_id,
        suggested_object_id="anchor",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    ).entity_id

    added: list = []
    await async_setup_entry(hass, entry, added.extend)

    coordinator._fire_notification(
        {"path": "notifications.navigation.anchor", "value": {"state": "alert"}},
        coordinator.config,
    )
    assert added == []

    registry.async_update_entity(disabled_id, disabled_by=None)

    coordinator._fire_notification(
        {
            "path": "notifications.navigation.anchor",
            "value": {"state": "alert"},
            "timestamp": "2026-01-03T22:34:57.853Z",
        },
        coordinator.config,
    )
    assert len(added) == 1
