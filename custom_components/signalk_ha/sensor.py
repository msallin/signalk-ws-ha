from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_URL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    DEFAULT_MIN_UPDATE_SECONDS,
    DEFAULT_STALE_SECONDS,
    DOMAIN,
    HEALTH_SENSOR_CONNECTION_STATE,
    HEALTH_SENSOR_LAST_ERROR,
    HEALTH_SENSOR_LAST_MESSAGE,
    HEALTH_SENSOR_RECONNECT_COUNT,
)
from .coordinator import SignalKCoordinator, SignalKDiscoveryCoordinator
from .discovery import DiscoveredEntity, convert_value

PARALLEL_UPDATES = 1


@dataclass(frozen=True)
class HealthSpec:
    key: str
    name: str
    value_fn: Callable[[Any], Any]
    device_class: SensorDeviceClass | None = None
    always_available: bool = True
    enabled_default: bool = True


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    host = entry.data["host"]
    port = entry.data["port"]
    ssl = entry.data["ssl"]
    scheme = "https" if ssl else "http"
    vessel_name = entry.data.get(CONF_VESSEL_NAME, "Unknown Vessel")
    base_url = entry.data.get(CONF_BASE_URL)
    vessel_id = entry.data.get(CONF_VESSEL_ID)
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=vessel_name,
        manufacturer="Signal K",
        configuration_url=base_url or f"{scheme}://{host}:{port}",
        serial_number=vessel_id,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    if runtime is None:
        return
    coordinator: SignalKCoordinator = runtime.coordinator
    discovery: SignalKDiscoveryCoordinator = runtime.discovery

    entities: list[SensorEntity] = []
    specs = _sensor_specs(discovery)
    if not specs:
        specs = _registry_sensor_specs(hass, entry)

    for spec in specs:
        entities.append(SignalKSensor(coordinator, discovery, entry, spec))

    health_specs = [
        HealthSpec(
            HEALTH_SENSOR_CONNECTION_STATE,
            "Connection State",
            lambda coord: coord.connection_state,
        ),
        HealthSpec(
            HEALTH_SENSOR_LAST_MESSAGE,
            "Last Message",
            lambda coord: coord.last_message,
            device_class=SensorDeviceClass.TIMESTAMP,
            enabled_default=False,
        ),
        HealthSpec(
            HEALTH_SENSOR_RECONNECT_COUNT,
            "Reconnect Count",
            lambda coord: coord.reconnect_count,
        ),
        HealthSpec(
            HEALTH_SENSOR_LAST_ERROR,
            "Last Error",
            lambda coord: coord.last_error,
        ),
    ]

    for spec in health_specs:
        entities.append(SignalKHealthSensor(coordinator, entry, spec))

    async_add_entities(entities)

    manager = _SignalKDiscoveryListener(
        coordinator, discovery, entry, async_add_entities, known_paths={spec.path for spec in specs}
    )
    entry.async_on_unload(discovery.async_add_listener(manager.handle_update))


def _sensor_specs(discovery: SignalKDiscoveryCoordinator) -> list[DiscoveredEntity]:
    data = discovery.data
    if not data:
        return []
    return [spec for spec in data.entities if spec.kind == "sensor"]


def _registry_sensor_specs(hass: HomeAssistant, entry: ConfigEntry) -> list[DiscoveredEntity]:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    specs: list[DiscoveredEntity] = []
    for registry_entry in entries:
        if registry_entry.domain != "sensor":
            continue
        path = _path_from_unique_id(registry_entry.unique_id)
        if not path:
            continue
        name = registry_entry.original_name or registry_entry.name or path.split(".")[-1]
        specs.append(
            DiscoveredEntity(
                path=path,
                name=name,
                kind="sensor",
                unit=None,
                device_class=None,
                state_class=None,
                conversion=None,
                tolerance=None,
                min_update_seconds=None,
            )
        )
    return specs


class SignalKBaseSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SignalKCoordinator,
        discovery: SignalKDiscoveryCoordinator | None,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._discovery = discovery
        self._attr_device_info = _device_info(entry)
        self._last_native_value: Any = None
        self._last_write: float | None = None
        self._last_available: bool | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        available = self.available
        value = self.native_value
        if self._should_write_state(value, available):
            self._last_native_value = value
            self._last_available = available
            self._last_write = time.monotonic()
            self.async_write_ha_state()

    def _should_write_state(self, value: Any, available: bool) -> bool:
        if self._last_write is None:
            return True
        if available != self._last_available:
            return True

        now = time.monotonic()
        min_interval = self._min_update_seconds()
        if now - self._last_write < min_interval:
            return False

        if value is None and self._last_native_value is not None:
            return True

        if isinstance(value, (int, float)) and isinstance(self._last_native_value, (int, float)):
            tolerance = self._tolerance()
            if tolerance is None:
                return value != self._last_native_value
            return abs(value - self._last_native_value) > tolerance

        return value != self._last_native_value

    def _tolerance(self) -> float | None:
        return None

    def _min_update_seconds(self) -> float:
        return DEFAULT_MIN_UPDATE_SECONDS


class SignalKSensor(SignalKBaseSensor):
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SignalKCoordinator,
        discovery: SignalKDiscoveryCoordinator,
        entry: ConfigEntry,
        spec: DiscoveredEntity,
    ) -> None:
        super().__init__(coordinator, discovery, entry)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_unique_id = f"signalk:{entry.entry_id}:{spec.path}"
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.state_class:
            self._attr_state_class = spec.state_class
        if spec.unit:
            self._attr_native_unit_of_measurement = spec.unit

    @property
    def available(self) -> bool:
        if not self.coordinator.is_connected:
            return False
        if not _path_available(self._spec.path, self._discovery):
            return False
        raw = self.coordinator.data.get(self._spec.path)
        if raw is None:
            return False
        return not _is_stale(self._spec.path, self.coordinator)

    @property
    def native_value(self) -> Any:
        raw = self.coordinator.data.get(self._spec.path)
        return convert_value(raw, self._spec.conversion)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_seen = _last_seen(self._spec.path, self.coordinator)
        attrs: dict[str, Any] = {"path": self._spec.path, "last_seen": last_seen}
        if self._spec.description:
            attrs["description"] = self._spec.description
        source = self.coordinator.last_source_by_path.get(self._spec.path)
        if source:
            attrs["source"] = source
        return attrs

    def _tolerance(self) -> float | None:
        return self._spec.tolerance

    def _min_update_seconds(self) -> float:
        if self._spec.min_update_seconds is None:
            return DEFAULT_MIN_UPDATE_SECONDS
        return self._spec.min_update_seconds


class SignalKHealthSensor(SignalKBaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: SignalKCoordinator, entry: ConfigEntry, spec: HealthSpec
    ) -> None:
        super().__init__(coordinator, None, entry)
        self._spec = spec
        self._attr_name = spec.name
        self._attr_unique_id = f"signalk:{entry.entry_id}:health:{spec.key}"
        self._attr_entity_registry_enabled_default = spec.enabled_default
        if spec.device_class:
            self._attr_device_class = spec.device_class

    @property
    def available(self) -> bool:
        return self._spec.always_available

    @property
    def native_value(self) -> Any:
        return self._spec.value_fn(self.coordinator)


class _SignalKDiscoveryListener:
    def __init__(
        self,
        coordinator: SignalKCoordinator,
        discovery: SignalKDiscoveryCoordinator,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
        *,
        known_paths: set[str] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._discovery = discovery
        self._entry = entry
        self._async_add_entities = async_add_entities
        self._known_paths: set[str] = known_paths or set()

    @callback
    def handle_update(self) -> None:
        specs = _sensor_specs(self._discovery)
        new_entities: list[SensorEntity] = []
        for spec in specs:
            if spec.path in self._known_paths:
                continue
            self._known_paths.add(spec.path)
            new_entities.append(
                SignalKSensor(self._coordinator, self._discovery, self._entry, spec)
            )

        if new_entities:
            self._async_add_entities(new_entities)


def _last_seen(path: str, coordinator: SignalKCoordinator) -> str | None:
    timestamp = coordinator.last_update_by_path.get(path)
    if not timestamp:
        return None
    return dt_util.as_utc(timestamp).isoformat()


def _is_stale(path: str, coordinator: SignalKCoordinator) -> bool:
    timestamp = coordinator.last_update_by_path.get(path)
    if not timestamp:
        return True
    age = dt_util.utcnow() - timestamp
    return age.total_seconds() > DEFAULT_STALE_SECONDS


def _path_available(path: str, discovery: SignalKDiscoveryCoordinator | None) -> bool:
    if not discovery or not discovery.data:
        return True
    return path in discovery.data.paths


def _path_from_unique_id(unique_id: str | None) -> str | None:
    if not unique_id:
        return None
    prefix = "signalk:"
    if not unique_id.startswith(prefix):
        return None
    parts = unique_id.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[2]
