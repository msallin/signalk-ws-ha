from custom_components.signalk_ha.notifications import (
    normalize_notification_paths,
    paths_to_text,
)


def test_normalize_notification_paths() -> None:
    paths = normalize_notification_paths(
        "notifications.navigation.anchor\nnavigation.course.arrival\n\n"
    )
    assert paths == [
        "notifications.navigation.anchor",
        "notifications.navigation.course.arrival",
    ]


def test_normalize_notification_paths_dedupes() -> None:
    paths = normalize_notification_paths(
        ["notifications.navigation.anchor", "navigation.anchor"]
    )
    assert paths == ["notifications.navigation.anchor"]


def test_normalize_notification_paths_invalid_input() -> None:
    assert normalize_notification_paths(42) == []


def test_normalize_notification_paths_skips_non_string_items() -> None:
    paths = normalize_notification_paths(["notifications.navigation.anchor", None])
    assert paths == ["notifications.navigation.anchor"]


def test_paths_to_text() -> None:
    assert (
        paths_to_text(["notifications.navigation.anchor", ""])
        == "notifications.navigation.anchor"
    )


def test_paths_to_text_empty() -> None:
    assert paths_to_text(None) == ""
