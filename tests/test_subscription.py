from custom_components.signalk_ws.subscription import build_subscribe_payload


def test_build_subscribe_payload_sanitizes_paths() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        ["  navigation.speedOverGround  ", "", "#comment", "   ", "navigation.speedOverGround"],
        1000,
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


def test_build_subscribe_payload_casts_period() -> None:
    payload = build_subscribe_payload(
        "vessels.self",
        ["navigation.speedOverGround"],
        "2000",
    )
    assert payload["subscribe"][0]["period"] == 2000
