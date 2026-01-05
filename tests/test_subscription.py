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
                "minPeriod": 1000,
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
            "minPeriod": DEFAULT_PERIOD_MS,
            "format": "delta",
            "policy": "ideal",
        },
        {
            "path": "navigation.depth",
            "period": 500,
            "minPeriod": 500,
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
            "minPeriod": DEFAULT_PERIOD_MS,
            "format": "delta",
            "policy": "ideal",
        }
    ]


def test_build_subscribe_payload_handles_none_periods() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            {"path": "navigation.depth", "period": None, "minPeriod": None},
        ],
    )
    assert payload["subscribe"] == [
        {
            "path": "navigation.depth",
            "period": DEFAULT_PERIOD_MS,
            "minPeriod": DEFAULT_PERIOD_MS,
            "format": "delta",
            "policy": "ideal",
        }
    ]


def test_build_subscribe_payload_respects_min_period_override() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            {"path": "navigation.speedOverGround", "period": 5000, "minPeriod": 1000},
        ],
    )
    assert payload["subscribe"] == [
        {
            "path": "navigation.speedOverGround",
            "period": 5000,
            "minPeriod": 1000,
            "format": "delta",
            "policy": "ideal",
        }
    ]
