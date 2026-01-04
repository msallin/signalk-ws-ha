from custom_components.signalk_ha.const import DEFAULT_PERIOD_MS
from custom_components.signalk_ha.subscription import build_subscribe_payload


def test_build_subscribe_payload_sanitizes_paths() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            {"path": "  navigation.speedOverGround  ", "period": 1000},
            {"path": "", "period": 1000},
            {"path": "#comment", "period": 1000},
            {"path": "   ", "period": 1000},
            {"path": "navigation.speedOverGround", "period": 1000},
        ],
    )
    assert payload == {
        "context": "vessels.self",
        "subscribe": [
            {
                "path": "navigation.speedOverGround",
                "period": 1000,
                "format": "delta",
                "policy": "ideal",
            }
        ],
    }


def test_build_subscribe_payload_skips_invalid_items() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            "not-a-dict",
            {"path": "navigation.speedOverGround"},
            {"path": "navigation.depth", "period": 500},
        ],
    )
    assert payload["subscribe"] == [
        {
            "path": "navigation.speedOverGround",
            "period": DEFAULT_PERIOD_MS,
            "format": "delta",
            "policy": "ideal",
        },
        {
            "path": "navigation.depth",
            "period": 500,
            "format": "delta",
            "policy": "ideal",
        },
    ]


def test_build_subscribe_payload_defaults_period() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            {"path": "navigation.speedOverGround"},
        ],
    )
    assert payload["subscribe"] == [
        {
            "path": "navigation.speedOverGround",
            "period": DEFAULT_PERIOD_MS,
            "format": "delta",
            "policy": "ideal",
        }
    ]
