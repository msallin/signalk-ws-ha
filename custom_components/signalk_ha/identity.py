from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VesselIdentity:
    vessel_id: str
    vessel_name: str


def normalize_vessel_name(value: Any) -> str:
    name = str(value).strip() if value is not None else ""
    return name or "Unknown Vessel"


def resolve_vessel_identity(data: dict[str, Any], base_url: str) -> VesselIdentity:
    name = normalize_vessel_name(data.get("name"))

    mmsi = data.get("mmsi")
    if isinstance(mmsi, str) and mmsi.isdigit() and 7 <= len(mmsi) <= 9:
        return VesselIdentity(vessel_id=f"mmsi:{mmsi}", vessel_name=name)

    for key in ("self", "uuid", "id", "urn", "vesselId"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            return VesselIdentity(vessel_id=raw.strip(), vessel_name=name)

    digest = hashlib.sha256(f"{base_url}|{name}".encode("utf-8")).hexdigest()[:12]
    return VesselIdentity(vessel_id=f"hash:{digest}", vessel_name=name)


def build_instance_id(base_url: str, vessel_id: str) -> str:
    digest = hashlib.sha256(f"{base_url}|{vessel_id}".encode("utf-8")).hexdigest()[:12]
    return f"instance:{digest}"
