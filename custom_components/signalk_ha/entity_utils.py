"""Shared helpers for entity registry identifiers."""

from __future__ import annotations


def path_from_unique_id(unique_id: str | None) -> str | None:
    if not unique_id:
        return None
    prefix = "signalk:"
    if not unique_id.startswith(prefix):
        return None
    parts = unique_id.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[2]
