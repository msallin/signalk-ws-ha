from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from .const import DEFAULT_PERIOD_MS, SK_PATH_POSITION
from .mapping import Conversion, apply_conversion, lookup_mapping

_RESERVED_KEYS = {
    "meta",
    "value",
    "$source",
    "timestamp",
    "values",
    "source",
    "pgn",
    "sentence",
}


@dataclass(frozen=True)
class MetadataConflict:
    path: str
    meta_units: str | None
    expected_units: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveredEntity:
    path: str
    name: str
    kind: str
    unit: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None
    conversion: Conversion | None
    tolerance: float | None
    min_update_seconds: float | None
    meta_units: str | None = None
    icon: str | None = None
    period_ms: int = DEFAULT_PERIOD_MS
    description: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    entities: list[DiscoveredEntity]
    conflicts: list[MetadataConflict]


def discover_entities(data: dict[str, Any], scopes: Iterable[str]) -> DiscoveryResult:
    entities: list[DiscoveredEntity] = []
    conflicts: list[MetadataConflict] = []
    for scope in scopes:
        node = data.get(scope)
        if isinstance(node, dict):
            _walk(node, scope, entities, conflicts)
    return DiscoveryResult(entities=entities, conflicts=conflicts)


def _walk(
    node: dict[str, Any],
    prefix: str,
    entities: list[DiscoveredEntity],
    conflicts: list[MetadataConflict],
) -> None:
    if "value" in node:
        _add_entity(prefix, node, entities, conflicts)

    for key, value in node.items():
        if key in _RESERVED_KEYS:
            continue
        if not isinstance(value, dict):
            continue
        _walk(value, f"{prefix}.{key}", entities, conflicts)


def _add_entity(
    path: str,
    node: dict[str, Any],
    entities: list[DiscoveredEntity],
    conflicts: list[MetadataConflict],
) -> None:
    value = node.get("value")
    meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
    meta_units = meta.get("units") if isinstance(meta, dict) else None

    if path == SK_PATH_POSITION:
        description = meta.get("description") if isinstance(meta.get("description"), str) else None
        entities.append(
            DiscoveredEntity(
                path=path,
                name="Position",
                kind="geo_location",
                unit=None,
                device_class=None,
                state_class=None,
                conversion=None,
                tolerance=0.00002,
                min_update_seconds=None,
                meta_units=meta_units,
                period_ms=DEFAULT_PERIOD_MS,
                description=description,
            )
        )
        return

    if isinstance(value, (dict, list)):
        return

    if path.endswith(".href"):
        return
    description = meta.get("description") if isinstance(meta, dict) else ""
    if isinstance(description, str) and "url" in description.lower():
        return
    description = description if isinstance(description, str) else None

    mapping = lookup_mapping(path)
    if mapping and meta_units and mapping.expected_units:
        if meta_units not in mapping.expected_units:
            conflicts.append(
                MetadataConflict(
                    path=path,
                    meta_units=meta_units,
                    expected_units=tuple(mapping.expected_units),
                )
            )

    name = _display_name(path, meta)
    conversion = mapping.conversion if mapping else _conversion_from_meta(path, meta_units)
    unit = mapping.unit if mapping else _unit_from_meta(meta_units, conversion)
    device_class = mapping.device_class if mapping else None
    state_class = mapping.state_class if mapping else None
    tolerance = mapping.tolerance if mapping else _tolerance_from_meta(meta_units)
    min_update_seconds = mapping.min_update_seconds if mapping else None

    period_ms = (
        mapping.period_ms if mapping and mapping.period_ms is not None else DEFAULT_PERIOD_MS
    )

    entities.append(
        DiscoveredEntity(
            path=path,
            name=name,
            kind="sensor",
            unit=unit,
            device_class=device_class,
            state_class=state_class,
            conversion=conversion,
            tolerance=tolerance,
            min_update_seconds=min_update_seconds,
            meta_units=meta_units,
            period_ms=period_ms,
            description=description,
        )
    )


def _display_name(path: str, meta: dict[str, Any]) -> str:
    for key in ("displayName", "shortName"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    last = path.split(".")[-1]
    spaced = "".join((" " + c if c.isupper() else c) for c in last).strip()
    return spaced[:1].upper() + spaced[1:]


def _unit_from_meta(meta_units: Any, conversion: Conversion | None) -> str | None:
    if conversion == Conversion.K_TO_C:
        return "degC"
    if conversion == Conversion.PA_TO_HPA:
        return "hPa"
    if conversion == Conversion.RATIO_TO_PERCENT:
        return "%"
    return str(meta_units) if isinstance(meta_units, str) and meta_units else None


def _conversion_from_meta(path: str, meta_units: Any) -> Conversion | None:
    if not isinstance(meta_units, str):
        return None
    units = meta_units.lower()
    if units == "k" and path.endswith(".temperature"):
        return Conversion.K_TO_C
    if units == "pa" and path.endswith(".pressure"):
        return Conversion.PA_TO_HPA
    if units == "ratio" and path.endswith("relativeHumidity"):
        return Conversion.RATIO_TO_PERCENT
    if units == "ratio" and path.endswith("currentLevel"):
        return Conversion.RATIO_TO_PERCENT
    return None


def _tolerance_from_meta(meta_units: Any) -> float | None:
    if not isinstance(meta_units, str):
        return None
    units = meta_units.lower()
    if units in ("k", "degc", "c"):
        return 0.1
    if units in ("pa", "hpa"):
        return 0.5
    if units == "ratio":
        return 0.01
    return None


def convert_value(value: Any, conversion: Conversion | None) -> Any:
    if conversion is None:
        return value
    if isinstance(value, (int, float)):
        return apply_conversion(float(value), conversion)
    return value
