import json

from custom_components.signalk_ha.parser import (
    _context_matches,
    extract_notifications,
    extract_sources,
    extract_values,
    parse_delta_text,
)


def test_parse_invalid_json_returns_empty() -> None:
    assert parse_delta_text("not json", None) == {}


def test_parse_non_delta_returns_empty() -> None:
    payload = json.dumps({"name": "signalk-server"})
    assert parse_delta_text(payload, None) == {}


def test_parse_non_object_json_returns_empty() -> None:
    assert parse_delta_text(json.dumps([1, 2, 3]), None) == {}


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


def test_extract_values_skips_invalid_updates() -> None:
    payload = {
        "updates": [
            "bad",
            {"values": ["bad", {"path": "p", "value": 1}]},
        ]
    }
    assert extract_values(payload, None) == {"p": 1}


def test_extract_values_non_dict_delta() -> None:
    assert extract_values([], None) == {}


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


def test_context_matches_empty_expected_or_incoming() -> None:
    assert _context_matches(None, "vessels.self") is True
    assert _context_matches("vessels.self", None) is True


def test_context_urn_matches_full_context() -> None:
    payload = {
        "context": "vessels.urn:mrn:imo:mmsi:123456789",
        "updates": [{"values": [{"path": "p", "value": 1}]}],
    }
    assert extract_values(payload, ["urn:mrn:imo:mmsi:123456789"]) == {"p": 1}


def test_context_mmsi_empty_returns_false() -> None:
    assert _context_matches("mmsi:", "vessels.self") is False


def test_context_urn_mismatch_returns_false() -> None:
    assert (
        _context_matches("urn:mrn:imo:mmsi:123456789", "vessels.urn:mrn:imo:mmsi:987654321")
        is False
    )


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


def test_extract_sources_skips_invalid_entries() -> None:
    payload = {
        "updates": [
            "bad",
            {"values": ["bad", {"path": "navigation.speedOverGround"}]},
            {"values": [{"path": "navigation.headingTrue", "$source": "src2"}]},
        ]
    }
    assert extract_sources(payload, None) == {"navigation.headingTrue": "src2"}


def test_extract_sources_non_dict_delta() -> None:
    assert extract_sources([], None) == {}


def test_extract_sources_updates_not_list() -> None:
    payload = {"updates": "nope"}
    assert extract_sources(payload, None) == {}


def test_extract_sources_context_mismatch() -> None:
    payload = {
        "context": "vessels.other",
        "updates": [{"values": [{"path": "p", "$source": "src"}]}],
    }
    assert extract_sources(payload, ["vessels.self"]) == {}


def test_extract_sources_values_not_list() -> None:
    payload = {"updates": [{"values": "bad"}]}
    assert extract_sources(payload, None) == {}


def test_extract_sources_path_not_string() -> None:
    payload = {"updates": [{"$source": "src", "values": [{"path": 123, "$source": "s2"}]}]}
    assert extract_sources(payload, None) == {}


def test_extract_notifications_collects_entries() -> None:
    payload = {
        "context": "vessels.self",
        "updates": [
            {
                "$source": "src1",
                "timestamp": "2026-01-03T22:34:57.853Z",
                "values": [
                    {"path": "navigation.speedOverGround", "value": 1.2},
                    {
                        "path": "notifications.navigation.anchor",
                        "value": {"state": "alert", "message": "Anchor", "method": ["sound"]},
                    },
                    {
                        "path": "notifications.navigation.course",
                        "value": None,
                        "$source": "src2",
                        "timestamp": "2026-01-03T22:35:00.000Z",
                    },
                ],
            }
        ],
    }

    assert extract_notifications(payload, ["vessels.self"]) == [
        {
            "path": "notifications.navigation.anchor",
            "value": {"state": "alert", "message": "Anchor", "method": ["sound"]},
            "source": "src1",
            "timestamp": "2026-01-03T22:34:57.853Z",
        },
        {
            "path": "notifications.navigation.course",
            "value": None,
            "source": "src2",
            "timestamp": "2026-01-03T22:35:00.000Z",
        },
    ]


def test_extract_notifications_context_mismatch() -> None:
    payload = {
        "context": "vessels.other",
        "updates": [
            {"values": [{"path": "notifications.navigation.anchor", "value": {"state": "alert"}}]}
        ],
    }
    assert extract_notifications(payload, ["vessels.self"]) == []


def test_extract_notifications_non_dict() -> None:
    assert extract_notifications([], None) == []


def test_extract_notifications_updates_not_list() -> None:
    assert extract_notifications({"updates": "nope"}, None) == []


def test_extract_notifications_skips_invalid_entries() -> None:
    payload = {
        "updates": [
            "bad",
            {"values": "nope"},
            {"values": ["bad", {"path": "notifications.navigation.anchor", "value": 1}]},
            {"values": [{"path": "notifications.navigation.speed"}]},
            {"values": [{"path": 123, "value": 2}]},
        ]
    }
    assert extract_notifications(payload, None) == [
        {"path": "notifications.navigation.anchor", "value": 1}
    ]
