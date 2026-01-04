import json

from custom_components.signalk_ha.parser import extract_sources, extract_values, parse_delta_text


def test_parse_invalid_json_returns_empty() -> None:
    assert parse_delta_text("not json", None) == {}


def test_parse_non_delta_returns_empty() -> None:
    payload = json.dumps({"name": "signalk-server"})
    assert parse_delta_text(payload, None) == {}


def test_parse_single_update_single_value() -> None:
    payload = json.dumps(
        {
            "context": "vessels.self",
            "updates": [{"values": [{"path": "navigation.speedOverGround", "value": 1.2}]}],
        }
    )
    assert parse_delta_text(payload, ["vessels.self"]) == {"navigation.speedOverGround": 1.2}


def test_parse_multiple_updates_multiple_values() -> None:
    payload = json.dumps(
        {
            "context": "vessels.self",
            "updates": [
                {
                    "values": [
                        {"path": "navigation.speedOverGround", "value": 1.2},
                        {"path": "navigation.courseOverGroundTrue", "value": 3.4},
                    ]
                },
                {"values": [{"path": "navigation.position", "value": {"lat": 1, "lon": 2}}]},
            ],
        }
    )
    assert parse_delta_text(payload, ["vessels.self"]) == {
        "navigation.speedOverGround": 1.2,
        "navigation.courseOverGroundTrue": 3.4,
        "navigation.position": {"lat": 1, "lon": 2},
    }


def test_parse_value_types() -> None:
    payload = json.dumps(
        {
            "context": "vessels.self",
            "updates": [
                {
                    "values": [
                        {"path": "p.int", "value": 1},
                        {"path": "p.float", "value": 1.5},
                        {"path": "p.bool", "value": True},
                        {"path": "p.str", "value": "ok"},
                        {"path": "p.obj", "value": {"x": 1}},
                        {"path": "p.null", "value": None},
                    ]
                }
            ],
        }
    )
    assert parse_delta_text(payload, ["vessels.self"]) == {
        "p.int": 1,
        "p.float": 1.5,
        "p.bool": True,
        "p.str": "ok",
        "p.obj": {"x": 1},
        "p.null": None,
    }


def test_extract_values_missing_fields() -> None:
    assert extract_values({}, None) == {}
    assert extract_values({"updates": "nope"}, None) == {}
    assert extract_values({"updates": [{"values": "nope"}]}, None) == {}
    assert extract_values({"updates": [{"values": [{"value": 1}]}]}, None) == {}
    assert extract_values({"updates": [{"values": [{"path": "p"}]}]}, None) == {}


def test_context_mismatch_returns_empty() -> None:
    payload = {"context": "vessels.other", "updates": [{"values": [{"path": "p", "value": 1}]}]}
    assert extract_values(payload, ["vessels.self"]) == {}


def test_context_missing_is_accepted() -> None:
    payload = {"updates": [{"values": [{"path": "p", "value": 1}]}]}
    assert extract_values(payload, ["vessels.self"]) == {"p": 1}


def test_context_wildcard_accepts_prefixed_context() -> None:
    payload = {
        "context": "vessels.urn:uuid:123",
        "updates": [{"values": [{"path": "p", "value": 1}]}],
    }
    assert extract_values(payload, ["vessels.*"]) == {"p": 1}


def test_context_self_accepts_resolved_context() -> None:
    payload = {
        "context": "vessels.urn:uuid:123",
        "updates": [{"values": [{"path": "p", "value": 1}]}],
    }
    assert extract_values(payload, ["vessels.self"]) == {"p": 1}


def test_context_mmsi_accepts_resolved_context() -> None:
    payload = {
        "context": "vessels.urn:mrn:imo:mmsi:261006533",
        "updates": [{"values": [{"path": "p", "value": 1}]}],
    }
    assert extract_values(payload, ["mmsi:261006533"]) == {"p": 1}


def test_extract_sources_from_update() -> None:
    payload = {
        "context": "vessels.self",
        "updates": [
            {
                "$source": "src1",
                "values": [
                    {"path": "navigation.speedOverGround", "value": 1.2},
                    {"path": "navigation.headingTrue", "value": 3.4},
                ],
            }
        ],
    }
    assert extract_sources(payload, ["vessels.self"]) == {
        "navigation.speedOverGround": "src1",
        "navigation.headingTrue": "src1",
    }
