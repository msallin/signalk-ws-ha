from __future__ import annotations

import json
from typing import Any, Iterable


def _context_matches(expected: str | None, incoming: str | None) -> bool:
    if not expected:
        return True
    if not incoming:
        return True
    if incoming == expected:
        return True
    if expected.endswith(".*") and incoming.startswith(expected[:-1]):
        return True
    if expected.startswith("mmsi:"):
        mmsi = expected.split(":", 1)[1]
        if mmsi and mmsi in incoming:
            return True
    if expected.startswith(("urn:", "mrn:")):
        if incoming.endswith(expected) or incoming == f"vessels.{expected}":
            return True
    if expected == "vessels.self" and incoming.startswith("vessels.urn:"):
        return True
    return False


def extract_values(
    delta_obj: dict[str, Any], expected_contexts: Iterable[str] | None
) -> dict[str, Any]:
    if not isinstance(delta_obj, dict):
        return {}

    if expected_contexts and "context" in delta_obj:
        incoming = delta_obj.get("context")
        if not any(_context_matches(expected, incoming) for expected in expected_contexts):
            return {}

    updates = delta_obj.get("updates")
    if not isinstance(updates, list):
        return {}

    changed: dict[str, Any] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        values = update.get("values")
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            path = value.get("path")
            if not isinstance(path, str):
                continue
            if "value" not in value:
                continue
            changed[path] = value.get("value")

    return changed


def extract_sources(
    delta_obj: dict[str, Any], expected_contexts: Iterable[str] | None
) -> dict[str, str]:
    if not isinstance(delta_obj, dict):
        return {}

    if expected_contexts and "context" in delta_obj:
        incoming = delta_obj.get("context")
        if not any(_context_matches(expected, incoming) for expected in expected_contexts):
            return {}

    updates = delta_obj.get("updates")
    if not isinstance(updates, list):
        return {}

    sources: dict[str, str] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_source = update.get("$source")
        if not isinstance(update_source, str):
            update_source = None
        values = update.get("values")
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            path = value.get("path")
            if not isinstance(path, str):
                continue
            value_source = value.get("$source")
            source = value_source if isinstance(value_source, str) else update_source
            if source is None:
                continue
            sources[path] = source

    return sources


def extract_notifications(
    delta_obj: dict[str, Any], expected_contexts: Iterable[str] | None
) -> list[dict[str, Any]]:
    if not isinstance(delta_obj, dict):
        return []

    if expected_contexts and "context" in delta_obj:
        incoming = delta_obj.get("context")
        if not any(_context_matches(expected, incoming) for expected in expected_contexts):
            return []

    updates = delta_obj.get("updates")
    if not isinstance(updates, list):
        return []

    notifications: list[dict[str, Any]] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_source = update.get("$source")
        if not isinstance(update_source, str):
            update_source = None
        update_timestamp = update.get("timestamp")
        if not isinstance(update_timestamp, str):
            update_timestamp = None
        values = update.get("values")
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            path = value.get("path")
            if not isinstance(path, str) or not path.startswith("notifications."):
                continue
            if "value" not in value:
                continue
            entry: dict[str, Any] = {"path": path, "value": value.get("value")}
            value_source = value.get("$source")
            if isinstance(value_source, str):
                entry["source"] = value_source
            elif update_source is not None:
                entry["source"] = update_source
            value_timestamp = value.get("timestamp")
            if isinstance(value_timestamp, str):
                entry["timestamp"] = value_timestamp
            elif update_timestamp is not None:
                entry["timestamp"] = update_timestamp
            notifications.append(entry)

    return notifications


def parse_delta_text(text: str, expected_contexts: Iterable[str] | None) -> dict[str, Any]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(obj, dict):
        return {}

    return extract_values(obj, expected_contexts)
