from custom_components.signalk_ws.config_flow import _text_to_paths


def test_text_to_paths_ignores_blanks_and_comments() -> None:
    text = "  navigation.speedOverGround  \n\n# comment\n  navigation.position\n"
    assert _text_to_paths(text) == ["navigation.speedOverGround", "navigation.position"]
