"""Notification event entities and dynamic path filtering."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NOTIFICATION_PATHS,
    DEFAULT_NOTIFICATION_PATHS,
    DOMAIN,
    NOTIFICATION_EVENT_TYPES,
)
from .coordinator import SignalKCoordinator
from .device_info import build_device_info
from .notifications import normalize_notification_paths


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    if runtime is None:
        return
    coordinator: SignalKCoordinator = runtime.coordinator
    if not coordinator.notifications_enabled:
        return
    allowed_paths = normalize_notification_paths(
        entry.options.get(CONF_NOTIFICATION_PATHS, DEFAULT_NOTIFICATION_PATHS)
    )
    # If the user hasn't opted in to any notification paths, keep the event platform idle.
    if not allowed_paths:
        return

    registry = er.async_get(hass)
    entities: list[SignalKNotificationEvent] = []

    allow_all = "notifications.*" in allowed_paths
    allowed_specific = {path for path in allowed_paths if path != "notifications.*"}
    # Create only explicitly selected events up front; wildcard events are created lazily.

    for path in allowed_specific:
        unique_id = f"signalk:{entry.entry_id}:{path}"
        entity_id = registry.async_get_entity_id("event", DOMAIN, unique_id)
        if entity_id:
            registry_entry = registry.async_get(entity_id)
            if registry_entry and registry_entry.disabled:
                continue
        entities.append(SignalKNotificationEvent(coordinator, entry, path))

    if entities:
        async_add_entities(entities)

    listener = _SignalKNotificationListener(
        coordinator,
        entry,
        registry,
        async_add_entities,
        allowed_paths=allowed_specific,
        allow_all=allow_all,
        entities={entity._path: entity for entity in entities},
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
        self._attr_device_info = build_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected and self.coordinator.notifications_enabled

    @callback
    def handle_notification(self, event_data: dict[str, Any]) -> None:
        if not self.coordinator.notifications_enabled:
            return
        # Events are per-path entities, so filter to the configured notification path.
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
        *,
        allowed_paths: set[str],
        allow_all: bool,
        entities: dict[str, SignalKNotificationEvent] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._registry = registry
        self._async_add_entities = async_add_entities
        self._entities: dict[str, SignalKNotificationEvent] = entities or {}
        self._allowed_paths = allowed_paths
        self._allow_all = allow_all
        # Path filtering keeps event entity creation explicit and bounded.

    @callback
    def handle_notification(self, event_data: dict[str, Any]) -> None:
        path = event_data.get("path")
        if not isinstance(path, str) or not path.startswith("notifications."):
            return
        if not self._allow_all and path not in self._allowed_paths:
            return
        entity = self._entities.get(path)
        if entity is None:
            # Create event entities on demand to avoid a large static entity list.
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
