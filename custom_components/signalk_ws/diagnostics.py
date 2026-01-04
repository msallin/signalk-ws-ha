from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN


def _redact_host(host: str) -> str:
    if not host:
        return host
    return "<redacted>"


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    cfg = coordinator.config

    last_message = coordinator.last_message
    last_message_iso = dt_util.as_utc(last_message).isoformat() if last_message else None

    updates: dict[str, str | None] = {}
    for path in cfg.paths:
        timestamp = coordinator.last_update_by_path.get(path)
        updates[path] = dt_util.as_utc(timestamp).isoformat() if timestamp else None

    return {
        "config": {
            "host": _redact_host(cfg.host),
            "port": cfg.port,
            "ssl": cfg.ssl,
            "verify_ssl": cfg.verify_ssl,
            "context": cfg.context,
            "period_ms": cfg.period_ms,
            "paths": list(cfg.paths),
            "subscriptions": list(cfg.subscriptions),
        },
        "connection_state": coordinator.connection_state,
        "last_error": coordinator.last_error,
        "counters": coordinator.counters,
        "reconnect_count": coordinator.reconnect_count,
        "last_message": last_message_iso,
        "last_update_by_path": updates,
    }
