"""Centralize device metadata to keep registry entries consistent across platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

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
)


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
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
