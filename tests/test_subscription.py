from custom_components.signalk_ws.subscription import (
    build_subscribe_payload,
    normalize_subscriptions,
    paths_to_subscriptions,
)


def test_paths_to_subscriptions_sanitizes_paths() -> None:
    subs = paths_to_subscriptions(
        ["  navigation.speedOverGround  ", "", "#comment", "   ", "navigation.speedOverGround"],
        period_ms=1000,
    )
    assert subs == [
        {
            "path": "navigation.speedOverGround",
            "period": 1000,
            "format": "delta",
            "policy": "ideal",
        }
    ]


def test_normalize_subscriptions_casts_period_and_min_period() -> None:
    subs = normalize_subscriptions(
        [
            {
                "path": "navigation.speedOverGround",
                "period": "2000",
                "format": "delta",
                "policy": "ideal",
                "minPeriod": "250",
            }
        ]
    )
    assert subs[0]["period"] == 2000
    assert subs[0]["minPeriod"] == 250


def test_build_subscribe_payload_uses_defaults_on_invalid_values() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        [
            {
                "path": "navigation.speedOverGround",
                "period": 1000,
                "format": "bad",
                "policy": "nope",
            }
        ],
    )
    assert payload["subscribe"][0]["format"] == "delta"
    assert payload["subscribe"][0]["policy"] == "ideal"
