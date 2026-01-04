from __future__ import annotations

import fnmatch
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
    CONF_SUBSCRIPTIONS,
    CONF_VESSEL_NAME,
    DEFAULT_VESSEL_NAME,
    DOMAIN,
    HEALTH_SENSOR_CONNECTION_STATE,
    HEALTH_SENSOR_LAST_ERROR,
    HEALTH_SENSOR_LAST_MESSAGE,
    HEALTH_SENSOR_RECONNECT_COUNT,
)
from .subscription import subscriptions_to_paths


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


def _vessel_name(entry: ConfigEntry) -> str:
    name = entry.options.get(CONF_VESSEL_NAME, entry.data.get(CONF_VESSEL_NAME))
    name = str(name).strip() if name else ""
    return name or DEFAULT_VESSEL_NAME


def _is_wildcard(path: str) -> bool:
    return any(ch in path for ch in ("*", "?", "["))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if CONF_SUBSCRIPTIONS in entry.options:
        subscriptions = entry.options.get(CONF_SUBSCRIPTIONS)
    elif CONF_SUBSCRIPTIONS in entry.data:
        subscriptions = entry.data.get(CONF_SUBSCRIPTIONS)
    else:
        subscriptions = None

    paths = subscriptions_to_paths(subscriptions)
    if subscriptions is None:
        paths = subscriptions_to_paths(coordinator.config.subscriptions)

    entities: list[SensorEntity] = []
    exact_paths = [path for path in paths if not _is_wildcard(path)]
    wildcard_paths = [path for path in paths if _is_wildcard(path)]
    for path in exact_paths:
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

    if wildcard_paths:
        manager = _SignalKDynamicSensors(
            coordinator,
            entry,
            wildcard_paths,
            async_add_entities,
            known_paths=set(exact_paths),
        )
        unsubscribe = manager.start()
        entry.async_on_unload(unsubscribe)


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
        vessel = _vessel_name(entry)

        self._attr_name = f"{vessel} {spec.name}"
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
        vessel = _vessel_name(entry)

        self._attr_name = f"{vessel} {spec.name}"
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


class _SignalKDynamicSensors:
    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        patterns: list[str],
        async_add_entities: AddEntitiesCallback,
        *,
        known_paths: set[str] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._patterns = patterns
        self._async_add_entities = async_add_entities
        self._known_paths = known_paths or set()

    def start(self) -> Callable[[], None]:
        self._add_matching_paths(self._coordinator.data.keys())
        return self._coordinator.async_add_listener(self._handle_update)

    def _handle_update(self) -> None:
        self._add_matching_paths(self._coordinator.data.keys())

    def _add_matching_paths(self, paths: Any) -> None:
        new_entities: list[SensorEntity] = []
        for path in paths:
            if not isinstance(path, str):
                continue
            if path in self._known_paths:
                continue
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in self._patterns):
                continue
            self._known_paths.add(path)
            new_entities.append(
                SignalKSensor(
                    self._coordinator,
                    self._entry,
                    SignalKPathSpec(path=path, name=_default_name_for_path(path)),
                )
            )

        if new_entities:
            self._async_add_entities(new_entities)
