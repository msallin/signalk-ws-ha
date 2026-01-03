from __future__ import annotations

import json
from typing import Any


def _context_matches(expected: str | None, incoming: str | None) -> bool:
    if not expected:
        return True
    if not incoming:
        return True
    if incoming == expected:
        return True
    if expected.endswith(".*") and incoming.startswith(expected[:-1]):
        return True
    if expected == "vessels.self" and incoming.startswith("vessels.urn:"):
        return True
    return False


def extract_values(delta_obj: dict[str, Any], expected_context: str | None) -> dict[str, Any]:
    if not isinstance(delta_obj, dict):
        return {}

    if "context" in delta_obj and not _context_matches(expected_context, delta_obj["context"]):
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


def parse_delta_text(text: str, expected_context: str | None) -> dict[str, Any]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(obj, dict):
        return {}

    return extract_values(obj, expected_context)
