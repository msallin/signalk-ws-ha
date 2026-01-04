from __future__ import annotations

from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SUBSCRIPTIONS, CONF_VESSEL_NAME, DEFAULT_VESSEL_NAME, DOMAIN
from .subscription import subscriptions_to_paths

_POSITION_PATH = "navigation.position"


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


def _should_create_position(paths: list[str]) -> bool:
    if _POSITION_PATH in paths:
        return True
    return any(_matches_position(path) for path in paths)


def _matches_position(path: str) -> bool:
    if "*" in path or "?" in path or "[" in path:
        import fnmatch

        return fnmatch.fnmatchcase(_POSITION_PATH, path)
    return False


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

    if not _should_create_position(paths):
        return

    async_add_entities([SignalKGeoLocation(coordinator, entry)])


class SignalKGeoLocation(CoordinatorEntity, GeolocationEvent):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = _device_info(entry)

        host = entry.data["host"]
        port = entry.data["port"]
        context = entry.data["context"]
        vessel = _vessel_name(entry)

        self._attr_name = f"{vessel} Position"
        self._attr_unique_id = f"{DOMAIN}:{host}:{port}:{context}:{_POSITION_PATH}:geo"
        self._attr_source = "Signal K"

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected

    @property
    def latitude(self) -> float | None:
        position = self._position_value()
        if not position:
            return None
        return position.get("latitude")

    @property
    def longitude(self) -> float | None:
        position = self._position_value()
        if not position:
            return None
        return position.get("longitude")

    @property
    def distance(self) -> float | None:
        return None

    def _position_value(self) -> dict[str, Any] | None:
        value = self.coordinator.data.get(_POSITION_PATH)
        return value if isinstance(value, dict) else None
