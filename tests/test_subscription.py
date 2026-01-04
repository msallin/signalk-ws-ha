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
