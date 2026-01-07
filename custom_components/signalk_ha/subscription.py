"""Build Signal K WebSocket subscription payloads."""

from __future__ import annotations

from typing import Any, Iterable

from .const import (
    DEFAULT_FORMAT,
    DEFAULT_MIN_UPDATE_MS,
    DEFAULT_PERIOD_MS,
    DEFAULT_POLICY,
    DEFAULT_STALE_SECONDS,
)

# Avoid requesting sub-1s updates; most servers/plugins treat this as a spam signal.
_MIN_PERIOD_FLOOR_MS = 1000


def build_subscribe_payload(
    context: str,
    subscriptions: Iterable[dict[str, Any]],
    *,
    fmt: str = DEFAULT_FORMAT,
    policy: str = DEFAULT_POLICY,
) -> dict[str, Any]:
    subscribe: list[dict[str, Any]] = []
    seen: set[str] = set()
    # We set both period (keepalive) and minPeriod (max rate) so the server can
    # enforce throttling before HA ever sees bursts.
    for raw in subscriptions:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path", "")).strip()
        if not path or path.startswith("#"):
            continue
        if path in seen:
            continue
        # period: resend even without changes (keeps entities from going stale).
        period = _sanitize_period(raw.get("period"))
        # minPeriod: cap the fastest rate the server should emit.
        min_period = _sanitize_min_period(raw.get("minPeriod"), period)
        subscribe.append(
            {
                "path": path,
                # Period controls keepalive updates when values have not changed.
                "period": period,
                # MinPeriod caps the fastest update rate the server should send.
                "minPeriod": min_period,
                "format": fmt,
                "policy": policy,
            }
        )
        seen.add(path)
    return {"context": context, "subscribe": subscribe}


def _sanitize_period(value: Any) -> int:
    period = _coerce_int(value, DEFAULT_PERIOD_MS)
    if period <= 0:
        period = DEFAULT_PERIOD_MS
    stale_limit = int(DEFAULT_STALE_SECONDS * 1000)
    # Keepalive must be strictly below the staleness timeout so a healthy stream
    # does not mark entities unavailable.
    if stale_limit > 0 and period >= stale_limit:
        period = max(stale_limit - _MIN_PERIOD_FLOOR_MS, _MIN_PERIOD_FLOOR_MS)
    return period


def _sanitize_min_period(value: Any, period: int) -> int:
    # Default minPeriod to our HA-side guard so the server doesn't overwhelm us.
    if value is None:
        min_period = min(DEFAULT_MIN_UPDATE_MS, period)
    else:
        min_period = _coerce_int(value, period)
    if min_period <= 0:
        min_period = min(DEFAULT_MIN_UPDATE_MS, period)
    # Never let minPeriod exceed period; otherwise keepalives are suppressed.
    if min_period > period:
        min_period = period
    return min_period


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
