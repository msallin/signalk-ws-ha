from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_PATHS,
    DOMAIN,
    HEALTH_SENSOR_CONNECTION_STATE,
    HEALTH_SENSOR_LAST_ERROR,
    HEALTH_SENSOR_LAST_MESSAGE,
    HEALTH_SENSOR_RECONNECT_COUNT,
)
from .subscription import sanitize_paths


@dataclass(frozen=True)
class SignalKPathSpec:
    path: str
    name: str


@dataclass(frozen=True)
class HealthSpec:
    key: str
    name: str
    value_fn: Callable[[Any], Any]
    device_class: SensorDeviceClass | None = None
    always_available: bool = True


def _default_name_for_path(path: str) -> str:
    # navigation.speedOverGround -> Speed Over Ground
    last = path.split(".")[-1]
    spaced = "".join((" " + c if c.isupper() else c) for c in last).strip()
    return spaced[:1].upper() + spaced[1:]


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    host = entry.data["host"]
    port = entry.data["port"]
    ssl = entry.data["ssl"]
    scheme = "https" if ssl else "http"
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Signal K Server {host}",
        manufacturer="Signal K",
        configuration_url=f"{scheme}://{host}:{port}",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    paths = sanitize_paths(entry.options.get(CONF_PATHS, entry.data.get(CONF_PATHS, [])))

    entities: list[SensorEntity] = []
    for path in paths:
        entities.append(
            SignalKSensor(
                coordinator,
                entry,
                SignalKPathSpec(path=path, name=_default_name_for_path(path)),
            )
        )

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


class SignalKBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = _device_info(entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SignalKSensor(SignalKBaseSensor):
    def __init__(self, coordinator, entry: ConfigEntry, spec: SignalKPathSpec) -> None:
        super().__init__(coordinator, entry)
        self._spec = spec

        host = entry.data["host"]
        port = entry.data["port"]
        context = entry.data["context"]

        self._attr_name = f"Signal K {spec.name}"
        self._attr_unique_id = f"{DOMAIN}:{host}:{port}:{context}:{spec.path}"

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.get(self._spec.path)


class SignalKHealthSensor(SignalKBaseSensor):
    def __init__(self, coordinator, entry: ConfigEntry, spec: HealthSpec) -> None:
        super().__init__(coordinator, entry)
        self._spec = spec

        host = entry.data["host"]
        port = entry.data["port"]
        context = entry.data["context"]

        self._attr_name = f"Signal K {spec.name}"
        self._attr_unique_id = f"{DOMAIN}:{host}:{port}:{context}:health:{spec.key}"
        if spec.device_class:
            self._attr_device_class = spec.device_class
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return self._spec.always_available

    @property
    def native_value(self) -> Any:
        return self._spec.value_fn(self.coordinator)
