import json
from pathlib import Path

from custom_components.signalk_ha.discovery import discover_entities


def test_discovery_finds_expected_paths() -> None:
    data = json.loads(Path("tests/vessel_self_testdata.json").read_text(encoding="utf-8"))
    result = discover_entities(data, scopes=("electrical", "environment", "tanks", "navigation"))
    paths = {entity.path for entity in result.entities}

    assert "navigation.speedOverGround" in paths
    assert "navigation.courseOverGroundTrue" in paths
    assert "environment.inside.saloon.temperature" in paths
    assert "electrical.ac.0.phase.A.lineNeutralVoltage" in paths
    assert "tanks.freshWater.0.currentLevel" in paths
    assert "navigation.position" in paths
    assert "notifications.navigation.course.perpendicularPassed" not in paths


def test_discovery_position_is_geo_location() -> None:
    data = json.loads(Path("tests/vessel_self_testdata.json").read_text(encoding="utf-8"))
    result = discover_entities(data, scopes=("navigation",))
    position = [entity for entity in result.entities if entity.path == "navigation.position"]
    assert position
    assert position[0].kind == "geo_location"


def test_discovery_walks_children_when_value_present() -> None:
    data = json.loads(Path("tests/vessel_self_testdata.json").read_text(encoding="utf-8"))
    result = discover_entities(data, scopes=("navigation",))
    paths = {entity.path for entity in result.entities}

    assert "navigation.courseGreatCircle.nextPoint.arrivalCircle" in paths
    assert "navigation.courseGreatCircle.nextPoint.steerError" in paths
