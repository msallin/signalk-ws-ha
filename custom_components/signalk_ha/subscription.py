"""Build Signal K WebSocket subscription payloads."""

from __future__ import annotations

from typing import Any, Iterable

from .const import DEFAULT_FORMAT, DEFAULT_PERIOD_MS, DEFAULT_POLICY


def build_subscribe_payload(
    context: str,
    subscriptions: Iterable[dict[str, Any]],
    *,
    fmt: str = DEFAULT_FORMAT,
    policy: str = DEFAULT_POLICY,
) -> dict[str, Any]:
    subscribe: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Include minPeriod to request server-side throttling before HA sees any deltas.
    for raw in subscriptions:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path", "")).strip()
        if not path or path.startswith("#"):
            continue
        if path in seen:
            continue
        period = raw.get("period", DEFAULT_PERIOD_MS)
        if period is None:
            period = DEFAULT_PERIOD_MS
        min_period = raw.get("minPeriod", period)
        if min_period is None:
            min_period = period
        subscribe.append(
            {
                "path": path,
                "period": int(period),
                "minPeriod": int(min_period),
                "format": fmt,
                "policy": policy,
            }
        )
        seen.add(path)
    return {"context": context, "subscribe": subscribe}
