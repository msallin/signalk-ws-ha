from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_PORT,
    CONF_SERVER_ID,
    CONF_SERVER_VERSION,
    CONF_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    DOMAIN,
    NOTIFICATION_EVENT_TYPES,
)
from .coordinator import SignalKCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    if runtime is None:
        return
    coordinator: SignalKCoordinator = runtime.coordinator
    registry = er.async_get(hass)
    entities: list[SignalKNotificationEvent] = []
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain != "event":
            continue
        path = _path_from_unique_id(entry.entry_id, registry_entry.unique_id)
        if not path:
            continue
        if registry_entry.disabled:
            continue
        entities.append(SignalKNotificationEvent(coordinator, entry, path))

    if entities:
        async_add_entities(entities)

    listener = _SignalKNotificationListener(
        coordinator,
        entry,
        registry,
        async_add_entities,
    )
    entry.async_on_unload(coordinator.async_add_notification_listener(listener.handle_notification))


class SignalKNotificationEvent(CoordinatorEntity, EventEntity):
    _attr_has_entity_name = True
    _attr_event_types = list(NOTIFICATION_EVENT_TYPES)

    def __init__(self, coordinator: SignalKCoordinator, entry: ConfigEntry, path: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._path = path
        self._attr_unique_id = f"signalk:{entry.entry_id}:{path}"
        self._attr_name = _notification_name(path)
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected and self.coordinator.notifications_enabled

    @callback
    def handle_notification(self, event_data: dict[str, Any]) -> None:
        if event_data.get("path") != self._path:
            return
        event_type = _notification_event_type(event_data.get("state"))
        attributes = _notification_attributes(event_data)
        self._trigger_event(event_type, attributes)
        if self.hass is not None:
            self.async_write_ha_state()


class _SignalKNotificationListener:
    def __init__(
        self,
        coordinator: SignalKCoordinator,
        entry: ConfigEntry,
        registry: er.EntityRegistry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._registry = registry
        self._async_add_entities = async_add_entities
        self._entities: dict[str, SignalKNotificationEvent] = {}

    @callback
    def handle_notification(self, event_data: dict[str, Any]) -> None:
        if not self._coordinator.notifications_enabled:
            return
        path = event_data.get("path")
        if not isinstance(path, str) or not path.startswith("notifications."):
            return
        entity = self._entities.get(path)
        if entity is None:
            unique_id = f"signalk:{self._entry.entry_id}:{path}"
            existing = self._registry.async_get_entity_id("event", DOMAIN, unique_id)
            if existing:
                registry_entry = self._registry.async_get(existing)
                if registry_entry and registry_entry.disabled:
                    return
            entity = SignalKNotificationEvent(self._coordinator, self._entry, path)
            self._entities[path] = entity
            self._async_add_entities([entity])
        entity.handle_notification(event_data)


def _notification_event_type(state: Any) -> str:
    if isinstance(state, str):
        normalized = state.strip().lower()
        if normalized in NOTIFICATION_EVENT_TYPES:
            return normalized
    return "unknown"


def _notification_attributes(event_data: dict[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for key in (
        "path",
        "state",
        "message",
        "method",
        "timestamp",
        "source",
        "vessel_id",
        "vessel_name",
        "entry_id",
        "value",
    ):
        value = event_data.get(key)
        if value is not None:
            attributes[key] = value
    received_at = event_data.get("received_at")
    if received_at:
        attributes["received_at"] = dt_util.as_utc(received_at).isoformat()
    return attributes


def _notification_name(path: str) -> str:
    parts = path.split(".")
    if parts and parts[0] == "notifications":
        parts = parts[1:]
    label = " ".join(_humanize_segment(part) for part in parts if part)
    if not label:
        return "Notification"
    return f"{label} Notification"


def _humanize_segment(segment: str) -> str:
    if not segment:
        return ""
    spaced = "".join((" " + c if c.isupper() else c) for c in segment).strip()
    spaced = spaced.replace("_", " ")
    return spaced[:1].upper() + spaced[1:] if spaced else ""


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    ssl = entry.data[CONF_SSL]
    scheme = "https" if ssl else "http"
    vessel_name = entry.data.get(CONF_VESSEL_NAME, "Unknown Vessel")
    base_url = entry.data.get(CONF_BASE_URL)
    vessel_id = entry.data.get(CONF_VESSEL_ID)
    server_id = entry.data.get(CONF_SERVER_ID) or None
    server_version = entry.data.get(CONF_SERVER_VERSION) or None
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=vessel_name,
        manufacturer="Signal K",
        model=server_id,
        sw_version=server_version,
        configuration_url=base_url or f"{scheme}://{host}:{port}",
        serial_number=vessel_id,
    )


def _path_from_unique_id(entry_id: str, unique_id: str | None) -> str | None:
    if not unique_id:
        return None
    prefix = f"signalk:{entry_id}:"
    if not unique_id.startswith(prefix):
        return None
    path = unique_id[len(prefix) :]
    return path if path.startswith("notifications.") else None
