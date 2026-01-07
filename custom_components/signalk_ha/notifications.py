"""Normalize user input for notification path selection."""

from __future__ import annotations

from typing import Any, Iterable


def normalize_notification_paths(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if not path:
            continue
        if not path.startswith("notifications."):
            path = f"notifications.{path}"
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def paths_to_text(paths: Iterable[str] | None) -> str:
    if not paths:
        return ""
    cleaned = [path.strip() for path in paths if isinstance(path, str) and path.strip()]
    return "\n".join(cleaned)
