from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DEVICE_CLASS_ANGLE = getattr(SensorDeviceClass, "ANGLE", None)
DEVICE_CLASS_DEPTH = getattr(SensorDeviceClass, "DEPTH", None)


class Conversion(str, Enum):
    RAD_TO_DEG = "rad_to_deg"
    MS_TO_KNOTS = "ms_to_knots"
    K_TO_C = "k_to_c"
    PA_TO_HPA = "pa_to_hpa"
    RATIO_TO_PERCENT = "ratio_to_percent"


@dataclass(frozen=True)
class PathMapping:
    unit: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None
    conversion: Conversion | None
    expected_units: tuple[str, ...] = ()
    tolerance: float | None = None
    min_update_seconds: float | None = None
    period_ms: int | None = None


_EXACT_MAPPING: dict[str, PathMapping] = {
    "navigation.speedOverGround": PathMapping(
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.MS_TO_KNOTS,
        expected_units=("m/s",),
        tolerance=0.02,
    ),
    "navigation.speedThroughWater": PathMapping(
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.MS_TO_KNOTS,
        expected_units=("m/s",),
        tolerance=0.02,
    ),
    "navigation.courseOverGroundTrue": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "navigation.courseOverGroundMagnetic": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "navigation.headingTrue": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "navigation.headingMagnetic": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "environment.depth.belowTransducer": PathMapping(
        unit="m",
        device_class=DEVICE_CLASS_DEPTH,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=None,
        expected_units=("m",),
        tolerance=0.05,
    ),
    "environment.depth.belowSurface": PathMapping(
        unit="m",
        device_class=DEVICE_CLASS_DEPTH,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=None,
        expected_units=("m",),
        tolerance=0.05,
    ),
    "environment.depth.belowKeel": PathMapping(
        unit="m",
        device_class=DEVICE_CLASS_DEPTH,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=None,
        expected_units=("m",),
        tolerance=0.05,
    ),
    "environment.wind.speedApparent": PathMapping(
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.MS_TO_KNOTS,
        expected_units=("m/s",),
        tolerance=0.1,
    ),
    "environment.wind.speedTrue": PathMapping(
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.MS_TO_KNOTS,
        expected_units=("m/s",),
        tolerance=0.1,
    ),
    "environment.wind.speedOverGround": PathMapping(
        unit="kn",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.MS_TO_KNOTS,
        expected_units=("m/s",),
        tolerance=0.1,
    ),
    "environment.wind.angleApparent": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "environment.wind.angleTrueWater": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "environment.wind.angleTrueGround": PathMapping(
        unit="deg",
        device_class=DEVICE_CLASS_ANGLE,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RAD_TO_DEG,
        expected_units=("rad",),
        tolerance=0.1,
    ),
    "tanks.freshWater.0.currentLevel": PathMapping(
        unit="%",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        conversion=Conversion.RATIO_TO_PERCENT,
        expected_units=("ratio",),
        tolerance=0.5,
    ),
}


def lookup_mapping(path: str) -> PathMapping | None:
    return _EXACT_MAPPING.get(path)


def expected_units(mapping: PathMapping | None) -> Iterable[str]:
    return mapping.expected_units if mapping else ()


def apply_conversion(value: float, conversion: Conversion | None) -> float:
    if conversion == Conversion.RAD_TO_DEG:
        return value * 57.29577951308232
    if conversion == Conversion.MS_TO_KNOTS:
        return value * 1.9438444924406
    if conversion == Conversion.K_TO_C:
        return value - 273.15
    if conversion == Conversion.PA_TO_HPA:
        return value / 100.0
    if conversion == Conversion.RATIO_TO_PERCENT:
        return value * 100.0
    return value
