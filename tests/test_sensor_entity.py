from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
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
    DOMAIN,
)
from custom_components.signalk_ha.coordinator import ConnectionState, SignalKCoordinator
from custom_components.signalk_ha.discovery import DiscoveredEntity, DiscoveryResult
from custom_components.signalk_ha.runtime import SignalKRuntimeData
from custom_components.signalk_ha.sensor import (
    SignalKHealthSensor,
    SignalKSensor,
    async_setup_entry,
)


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


async def test_sensor_unavailable_when_disconnected(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

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
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.DISCONNECTED
    coordinator.data = {"navigation.speedOverGround": 5.5}

    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    assert sensor.available is False


async def test_sensor_unavailable_when_path_missing(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

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
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.speedOverGround": 5.5}

    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    assert sensor.available is False


async def test_sensor_unavailable_when_raw_none(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

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
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.speedOverGround": None}

    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    assert sensor.available is False


async def test_sensor_extra_attributes_minimal(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    spec = DiscoveredEntity(
        path="navigation.speedOverGround",
        name="Speed Over Ground",
        kind="sensor",
        unit=None,
        device_class=None,
        state_class=None,
        conversion=None,
        tolerance=0.1,
        min_update_seconds=None,
        description=None,
    )
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.speedOverGround": 5.5}
    coordinator._last_update_by_path["navigation.speedOverGround"] = dt_util.utcnow()

    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    attrs = sensor.extra_state_attributes
    assert attrs["path"] == "navigation.speedOverGround"
    assert "description" not in attrs


async def test_sensor_handle_update_writes_state(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

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
    coordinator = SignalKCoordinator(hass, entry, Mock(), Mock(), SignalKAuthManager(None))
    coordinator._state = ConnectionState.CONNECTED
    coordinator.data = {"navigation.speedOverGround": 5.5}
    coordinator._last_update_by_path["navigation.speedOverGround"] = dt_util.utcnow()

    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    sensor.async_write_ha_state = Mock()
    sensor._handle_coordinator_update()

    sensor.async_write_ha_state.assert_called_once()


async def test_sensor_setup_entry_adds_entities(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

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

    await async_setup_entry(hass, entry, added.extend)

    assert any(isinstance(entity, SignalKSensor) for entity in added)
    assert any(isinstance(entity, SignalKHealthSensor) for entity in added)


async def test_sensor_setup_entry_without_runtime(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    entry.runtime_data = None

    added = []

    await async_setup_entry(hass, entry, added.extend)
    assert not added


async def test_sensor_setup_entry_uses_registry_when_no_specs(hass) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"signalk:{entry.entry_id}:navigation.depth",
        suggested_object_id="depth",
        config_entry=entry,
    )

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

    await async_setup_entry(hass, entry, added.extend)

    assert any(
        isinstance(entity, SignalKSensor) and entity._spec.path == "navigation.depth"
        for entity in added
    )


def test_sensor_sets_device_class_and_state_class() -> None:
    entry = _make_entry()
    spec = DiscoveredEntity(
        path="navigation.speedOverGround",
        name="Speed Over Ground",
        kind="sensor",
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=None,
        tolerance=None,
        min_update_seconds=None,
    )
    coordinator = SignalKCoordinator(Mock(), entry, Mock(), Mock(), SignalKAuthManager(None))
    discovery = SimpleNamespace(data=DiscoveryResult(entities=[spec], conflicts=[]))
    sensor = SignalKSensor(coordinator, discovery, entry, spec)
    assert sensor.device_class == SensorDeviceClass.SPEED
    assert sensor.state_class == SensorStateClass.MEASUREMENT
