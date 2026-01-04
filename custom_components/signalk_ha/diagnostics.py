from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN


def _redact_url(url: str) -> str:
    if not url:
        return url
    return "<redacted>"


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    discovery = data["discovery"]
    cfg = coordinator.config

    last_message = coordinator.last_message
    last_message_iso = dt_util.as_utc(last_message).isoformat() if last_message else None

    updates: dict[str, str | None] = {}
    for path, timestamp in coordinator.last_update_by_path.items():
        updates[path] = dt_util.as_utc(timestamp).isoformat() if timestamp else None

    last_refresh = discovery.last_refresh
    last_refresh_iso = dt_util.as_utc(last_refresh).isoformat() if last_refresh else None

    return {
        "config": {
            "rest_url": _redact_url(cfg.base_url),
            "ws_url": _redact_url(cfg.ws_url),
            "vessel_id": cfg.vessel_id,
            "vessel_name": cfg.vessel_name,
        },
        "connection_state": coordinator.connection_state,
        "last_error": coordinator.last_error,
        "counters": coordinator.counters,
        "reconnect_count": coordinator.reconnect_count,
        "last_backoff_seconds": coordinator.last_backoff,
        "last_message": last_message_iso,
        "last_rest_refresh": last_refresh_iso,
        "subscribed_path_count": len(coordinator.subscribed_paths),
        "metadata_conflicts": [
            {
                "path": conflict.path,
                "meta_units": conflict.meta_units,
                "expected": conflict.expected_units,
            }
            for conflict in discovery.conflicts
        ],
        "last_update_by_path": updates,
    }
