from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

from .const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_INSTANCE_ID,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DEFAULT_PERIOD_MS,
    DEFAULT_PORT,
    DEFAULT_REFRESH_INTERVAL_HOURS,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import SignalKCoordinator, SignalKDiscoveryCoordinator
from .identity import build_instance_id
from .rest import normalize_base_url, normalize_ws_url

PLATFORMS: list[str] = ["sensor", "geo_location"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    discovery = SignalKDiscoveryCoordinator(hass, entry, session)
    coordinator = SignalKCoordinator(hass, entry, session, discovery)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "discovery": discovery,
    }

    await discovery.async_refresh()
    await coordinator.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_update_subscriptions(hass, entry)

    @callback
    def _registry_updated(event):
        entity_id = event.data.get("entity_id")
        if not entity_id or event.data.get("action") not in ("update", "create", "remove"):
            return
        registry = er.async_get(hass)
        entry_data = registry.async_get(entity_id)
        if entry_data and entry_data.config_entry_id == entry.entry_id:
            hass.async_create_task(_async_update_subscriptions(hass, entry))

    entry.async_on_unload(hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, _registry_updated))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version >= 2:
        return True

    data = {**entry.data}
    host = data.get(CONF_HOST, "")
    port = data.get(CONF_PORT, DEFAULT_PORT)
    use_ssl = data.get(CONF_SSL, DEFAULT_SSL)

    if host:
        data.setdefault(CONF_BASE_URL, normalize_base_url(host, port, use_ssl))
        data.setdefault(CONF_WS_URL, normalize_ws_url(host, port, use_ssl))

    data.setdefault(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    data.setdefault(CONF_VESSEL_ID, "")
    data.setdefault(CONF_VESSEL_NAME, "Unknown Vessel")
    data.setdefault(CONF_REFRESH_INTERVAL_HOURS, DEFAULT_REFRESH_INTERVAL_HOURS)

    if CONF_INSTANCE_ID not in data:
        base_url = data.get(CONF_BASE_URL, host)
        vessel_id = data.get(CONF_VESSEL_ID, "")
        data[CONF_INSTANCE_ID] = build_instance_id(base_url, vessel_id)

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        await data["coordinator"].async_stop()
        await data["discovery"].async_stop()

    return unload_ok


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_update_subscriptions(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data:
        return
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    paths: list[str] = []
    periods: dict[str, int] = {}
    discovery = data.get("discovery")
    discovery_periods: dict[str, int] = {}
    if discovery and discovery.data:
        discovery_periods = {
            spec.path: spec.period_ms for spec in discovery.data.entities if spec.period_ms
        }
    for registry_entry in entries:
        if registry_entry.disabled:
            continue
        path = _path_from_unique_id(registry_entry.unique_id)
        if path:
            paths.append(path)
            periods[path] = discovery_periods.get(path, DEFAULT_PERIOD_MS)
    await data["coordinator"].async_update_paths(paths, periods)


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
