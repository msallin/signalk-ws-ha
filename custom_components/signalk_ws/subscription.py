from __future__ import annotations

from typing import Any


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


def build_subscribe_payload(context: str, paths: list[str], period_ms: int) -> dict[str, Any]:
    period = int(period_ms)
    subscribe = [
        {"path": path, "period": period, "format": "delta", "policy": "ideal"}
        for path in sanitize_paths(paths)
    ]
    return {"context": context, "subscribe": subscribe}
