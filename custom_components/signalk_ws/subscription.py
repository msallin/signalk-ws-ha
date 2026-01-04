from __future__ import annotations

from typing import Any

from .const import (
    DEFAULT_FORMAT,
    DEFAULT_MIN_PERIOD_MS,
    DEFAULT_PERIOD_MS,
    DEFAULT_POLICY,
)

_FORMATS = {"delta", "full"}
_POLICIES = {"instant", "ideal", "fixed"}


def _safe_int(value: Any, default: int | str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def sanitize_paths(paths: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if raw is None:
            continue
        path = str(raw).strip()
        if not path or path.startswith("#"):
            continue
        if path in seen:
            continue
        seen.add(path)
        cleaned.append(path)
    return cleaned


def paths_to_subscriptions(
    paths: list[str],
    period_ms: int | str = DEFAULT_PERIOD_MS,
    fmt: str = DEFAULT_FORMAT,
    policy: str = DEFAULT_POLICY,
    min_period_ms: int | str = DEFAULT_MIN_PERIOD_MS,
) -> list[dict[str, Any]]:
    period = _safe_int(period_ms, DEFAULT_PERIOD_MS)
    min_period = _safe_int(min_period_ms, DEFAULT_MIN_PERIOD_MS)
    base: dict[str, Any] = {
        "period": period,
        "format": fmt,
        "policy": policy,
    }
    if min_period:
        base["minPeriod"] = min_period

    return [{"path": path, **base} for path in sanitize_paths(paths)]


def normalize_subscriptions(
    subscriptions: list[dict[str, Any]] | None,
    *,
    default_period_ms: int | str = DEFAULT_PERIOD_MS,
    default_format: str = DEFAULT_FORMAT,
    default_policy: str = DEFAULT_POLICY,
    default_min_period_ms: int | str = DEFAULT_MIN_PERIOD_MS,
) -> list[dict[str, Any]]:
    if not subscriptions:
        return []

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in subscriptions:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path", "")).strip()
        if not path or path.startswith("#"):
            continue
        if path in seen:
            continue

        period_raw = raw.get("period", raw.get("period_ms", default_period_ms))
        period = _safe_int(period_raw, default_period_ms)

        fmt = str(raw.get("format", default_format)).lower()
        if fmt not in _FORMATS:
            fmt = default_format

        policy = str(raw.get("policy", default_policy)).lower()
        if policy not in _POLICIES:
            policy = default_policy

        min_period_raw = raw.get(
            "minPeriod",
            raw.get("min_period", raw.get("min_period_ms", default_min_period_ms)),
        )
        min_period = _safe_int(min_period_raw, default_min_period_ms)

        spec: dict[str, Any] = {
            "path": path,
            "period": period,
            "format": fmt,
            "policy": policy,
        }
        if min_period:
            spec["minPeriod"] = min_period

        seen.add(path)
        cleaned.append(spec)

    return cleaned


def subscriptions_to_paths(subscriptions: list[dict[str, Any]] | None) -> list[str]:
    return [spec["path"] for spec in normalize_subscriptions(subscriptions)]


def build_subscribe_payload(
    context: str,
    subscriptions: list[dict[str, Any]] | None,
    *,
    default_period_ms: int | str = DEFAULT_PERIOD_MS,
) -> dict[str, Any]:
    subscribe = normalize_subscriptions(subscriptions, default_period_ms=default_period_ms)
    return {"context": context, "subscribe": subscribe}
