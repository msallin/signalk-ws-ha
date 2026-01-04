from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


def _redact_url(url: str) -> str:
    if not url:
        return url
    # Diagnostics should be shareable without exposing endpoints or credentials.
    return "<redacted>"


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {"error": "no_runtime_data"}
    coordinator = runtime.coordinator
    discovery = runtime.discovery
    auth = runtime.auth
    cfg = coordinator.config

    last_message = coordinator.last_message
    last_message_iso = dt_util.as_utc(last_message).isoformat() if last_message else None

    updates: dict[str, str | None] = {}
    for path, timestamp in coordinator.last_update_by_path.items():
        updates[path] = dt_util.as_utc(timestamp).isoformat() if timestamp else None

    last_refresh = discovery.last_refresh
    last_refresh_iso = dt_util.as_utc(last_refresh).isoformat() if last_refresh else None

    auth_last_success = auth.last_success if auth else None
    auth_last_success_iso = (
        dt_util.as_utc(auth_last_success).isoformat() if auth_last_success else None
    )
    last_notification = coordinator.last_notification
    if last_notification and last_notification.get("received_at"):
        received_at = last_notification["received_at"]
        last_notification = {
            **last_notification,
            "received_at": dt_util.as_utc(received_at).isoformat(),
        }

    return {
        "config": {
            "rest_url": _redact_url(cfg.base_url),
            "ws_url": _redact_url(cfg.ws_url),
            "vessel_id": cfg.vessel_id,
            "vessel_name": cfg.vessel_name,
        },
        "auth": {
            "state": auth.state.value if auth else None,
            "access_request_active": auth.access_request_active if auth else None,
            "token_present": auth.token_present if auth else None,
            "last_error": auth.last_error if auth else None,
            "last_success": auth_last_success_iso,
        },
        "connection_state": coordinator.connection_state,
        "last_error": coordinator.last_error,
        "counters": coordinator.counters,
        "reconnect_count": coordinator.reconnect_count,
        "last_backoff_seconds": coordinator.last_backoff,
        "last_message": last_message_iso,
        "last_rest_refresh": last_refresh_iso,
        "subscribed_path_count": len(coordinator.subscribed_paths),
        "notifications": {
            "count": coordinator.notification_count,
            "last": last_notification,
        },
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
