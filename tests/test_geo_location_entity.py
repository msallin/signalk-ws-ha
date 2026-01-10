import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.helpers import entity_registry as er
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
    DEFAULT_MAX_IDLE_WRITE_SECONDS,
    DEFAULT_MIN_UPDATE_MS,
    DOMAIN,
)
from custom_components.signalk_ha.coordinator import ConnectionState, SignalKCoordinator
from custom_components.signalk_ha.discovery import DiscoveredEntity, DiscoveryResult
from custom_components.signalk_ha.geo_location import (
    SignalKPositionGeolocation,
    _coord_distance,
    _is_stale,
    _path_available,
    _position_description,
    _position_spec_known,
    _registry_has_geolocation,
    _should_create_geolocation,
    _SignalKDiscoveryListener,
)
from custom_components.signalk_ha.runtime import SignalKRuntimeData


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
        spec_known=True,
    )
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[spec], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()
    coordinator._last_source_by_path["navigation.position"] = "src1"

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)

    assert geo.latitude == 1.0
    assert geo.longitude == 2.0
    assert geo.distance == 0.0
    assert geo.available is True
    attrs = geo.state_attributes
    assert attrs["description"] == "Vessel position"
    assert attrs["source"] == "src1"
    assert attrs["spec_known"] is True


async def test_geo_location_unavailable_when_stale(hass, enable_custom_integrations) -> None:
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
    )
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[spec], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow() - timedelta(
        seconds=999999
    )

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.available is False


async def test_geo_location_setup_entry_creates_entity(hass) -> None:
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
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[spec], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=discovery,
        auth=SignalKAuthManager(None),
    )

    added = []

    def _add(entities):
        added.extend(entities)

    from custom_components.signalk_ha.geo_location import async_setup_entry

    await async_setup_entry(hass, entry, _add)
    assert added


async def test_geo_location_setup_entry_without_runtime(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    entry.runtime_data = None
    added = []

    from custom_components.signalk_ha.geo_location import async_setup_entry

    await async_setup_entry(hass, entry, added.extend)
    assert not added


async def test_geo_location_setup_entry_no_spec(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    entry.runtime_data = SignalKRuntimeData(
        coordinator=coordinator,
        discovery=discovery,
        auth=SignalKAuthManager(None),
    )

    added = []
    from custom_components.signalk_ha.geo_location import async_setup_entry

    await async_setup_entry(hass, entry, added.extend)
    assert not added


def test_geo_location_registry_helpers(hass) -> None:
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
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    assert _should_create_geolocation(discovery) is True
    assert _registry_has_geolocation(hass, entry) is False


def test_registry_has_geolocation_true(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "geo_location",
        DOMAIN,
        f"signalk:{entry.entry_id}:navigation.position",
        suggested_object_id="position",
        config_entry=entry,
    )
    assert _registry_has_geolocation(hass, entry) is True


def test_should_create_geolocation_false() -> None:
    discovery = SimpleNamespace(data=None)
    assert _should_create_geolocation(discovery) is False


def test_position_description_none() -> None:
    discovery = SimpleNamespace(data=None)
    assert _position_description(discovery) is None


def test_position_description_unmatched() -> None:
    spec = DiscoveredEntity(
        path="navigation.speedOverGround",
        name="Speed Over Ground",
        kind="sensor",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    assert _position_description(discovery) is None


def test_position_spec_known_false() -> None:
    discovery = SimpleNamespace(data=None)
    assert _position_spec_known(discovery) is False


def test_position_spec_known_unmatched() -> None:
    spec = DiscoveredEntity(
        path="navigation.speedOverGround",
        name="Speed Over Ground",
        kind="sensor",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
        spec_known=True,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    assert _position_spec_known(discovery) is False


def test_position_spec_known_true() -> None:
    spec = DiscoveredEntity(
        path="navigation.position",
        name="Position",
        kind="geo_location",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
        spec_known=True,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    assert _position_spec_known(discovery) is True


def test_geo_location_handle_update_without_last_seen(hass) -> None:
    entry = _make_entry()
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    discovery = SimpleNamespace(data=None)
    entity = SignalKPositionGeolocation(coordinator, discovery, entry)
    entity.async_write_ha_state = Mock()

    entity._handle_coordinator_update()

    assert entity._last_seen_at is None
    entity.async_write_ha_state.assert_called_once()


def test_geo_location_should_write_state_idle_without_last_seen(hass) -> None:
    entry = _make_entry()
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    discovery = SimpleNamespace(data=None)
    entity = SignalKPositionGeolocation(coordinator, discovery, entry)
    entity._last_write = time.monotonic() - (DEFAULT_MAX_IDLE_WRITE_SECONDS + 1)
    entity._last_available = True
    entity._last_coords = (1.0, 2.0)

    assert entity._should_write_state((1.0, 2.0), True) is False


def test_geo_location_should_write_state_no_coords(hass) -> None:
    entry = _make_entry()
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    discovery = SimpleNamespace(data=None)
    entity = SignalKPositionGeolocation(coordinator, discovery, entry)
    entity._last_write = time.monotonic() - (DEFAULT_MIN_UPDATE_MS / 1000.0 + 1)
    entity._last_available = True
    entity._last_coords = None

    assert entity._should_write_state(None, True) is False


def test_geo_location_is_stale_without_timestamp(hass) -> None:
    entry = _make_entry()
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))

    assert _is_stale(coordinator) is True


def test_path_available_defaults_true() -> None:
    discovery = SimpleNamespace(data=None)
    assert _path_available(discovery) is True


def test_path_available_false_when_missing() -> None:
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    assert _path_available(discovery) is False


async def test_geo_location_unavailable_when_raw_invalid(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": "invalid"}

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.available is False


async def test_geo_location_unavailable_when_raw_invalid_with_path_available(hass) -> None:
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
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[spec], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": "invalid"}

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.available is False


async def test_geo_location_unavailable_when_disconnected(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.DISCONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.available is False


async def test_geo_location_lat_lon_none_when_invalid(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": "invalid"}

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.latitude is None
    assert geo.longitude is None


async def test_geo_location_distance_none_when_coords_missing(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator.data = {"navigation.position": {"latitude": 1.0}}
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.distance is None


async def test_geo_location_handle_update_writes_state(hass) -> None:
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
    )
    discovery = SimpleNamespace(
        data=DiscoveryResult(entities=[spec], conflicts=[]),
        async_add_listener=Mock(return_value=lambda: None),
    )
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo.async_write_ha_state = Mock()
    geo._handle_coordinator_update()

    geo.async_write_ha_state.assert_called_once()


async def test_geo_location_state_attributes_include_description(hass) -> None:
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
        tolerance=None,
        min_update_seconds=None,
        description="GPS position",
        spec_known=True,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()
    coordinator._state = ConnectionState.CONNECTED
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.state_attributes["description"] == "GPS position"
    assert geo.state_attributes["spec_known"] is True


async def test_geo_location_state_attributes_include_last_seen(hass) -> None:
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
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    timestamp = dt_util.utcnow()
    coordinator._last_update_by_path["navigation.position"] = timestamp
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}

    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo.state_attributes["last_seen"] == dt_util.as_utc(timestamp).isoformat()


def test_geo_location_coords_none() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator.data = {"navigation.position": {"latitude": 1.0}}
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert geo._coords() is None


def test_geo_location_should_write_state_respects_tolerance() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = True
    geo._last_write = time.monotonic() - (DEFAULT_MIN_UPDATE_MS / 1000.0)

    assert geo._should_write_state((1.000001, 2.000001), True) is False
    assert geo._should_write_state((1.01, 2.01), True) is True


def test_coord_distance() -> None:
    assert _coord_distance((1.0, 2.0), (1.0, 2.0)) == 0.0


def test_geo_location_listener_creates_entity(hass) -> None:
    entry = _make_entry()
    spec = DiscoveredEntity(
        path="navigation.position",
        name="Position",
        kind="geo_location",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    async_add = Mock()

    listener = _SignalKDiscoveryListener(
        coordinator,
        discovery,
        entry,
        async_add,
        created=False,
    )
    listener.handle_update()

    async_add.assert_called_once()


def test_geo_location_listener_skips_when_created(hass) -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    async_add = Mock()

    listener = _SignalKDiscoveryListener(
        coordinator,
        discovery,
        entry,
        async_add,
        created=True,
    )
    listener.handle_update()

    async_add.assert_not_called()


def test_geo_location_listener_skips_when_missing_spec(hass) -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    async_add = Mock()

    listener = _SignalKDiscoveryListener(
        coordinator,
        discovery,
        entry,
        async_add,
        created=False,
    )
    listener.handle_update()

    async_add.assert_not_called()


def test_geo_location_state_attributes_omit_last_seen(hass) -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._state = ConnectionState.CONNECTED
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    assert "last_seen" not in geo.state_attributes
    assert geo.state_attributes["spec_known"] is False


def test_geo_location_handle_update_skips_when_unchanged(hass) -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=None)
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.position": {"latitude": 1.0, "longitude": 2.0}}
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = True
    geo._last_write = time.monotonic()
    geo.async_write_ha_state = Mock()

    geo._handle_coordinator_update()

    geo.async_write_ha_state.assert_not_called()


def test_geo_location_should_write_state_available_change() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = False
    geo._last_write = time.monotonic()

    assert geo._should_write_state((1.0, 2.0), True) is True


def test_geo_location_should_write_state_min_interval() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = True
    geo._last_write = time.monotonic() - (DEFAULT_MIN_UPDATE_MS / 1000.0)

    assert geo._should_write_state((1.0, 2.0), True) is False


def test_geo_location_should_write_state_after_max_idle() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = True
    geo._last_write = time.monotonic() - DEFAULT_MAX_IDLE_WRITE_SECONDS - 1.0
    geo._last_seen_at = dt_util.utcnow() - timedelta(seconds=10)
    coordinator._last_update_by_path["navigation.position"] = dt_util.utcnow()

    assert geo._should_write_state((1.0, 2.0), True) is True


def test_geo_location_should_write_state_when_coords_cleared() -> None:
    entry = _make_entry()
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    geo = SignalKPositionGeolocation(coordinator, discovery, entry)
    geo._last_coords = (1.0, 2.0)
    geo._last_available = True
    geo._last_write = time.monotonic() - (DEFAULT_MIN_UPDATE_MS / 1000.0)

    assert geo._should_write_state(None, True) is True
