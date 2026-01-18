from custom_components.signalk_ha.notifications import (
    normalize_notification_paths,
    normalize_notification_prefixes,
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
    paths = normalize_notification_paths(["notifications.navigation.anchor", "navigation.anchor"])
    assert paths == ["notifications.navigation.anchor"]


def test_normalize_notification_paths_invalid_input() -> None:
    assert normalize_notification_paths(42) == []


def test_normalize_notification_paths_skips_non_string_items() -> None:
    paths = normalize_notification_paths(["notifications.navigation.anchor", None])
    assert paths == ["notifications.navigation.anchor"]


def test_paths_to_text() -> None:
    assert (
        paths_to_text(["notifications.navigation.anchor", ""]) == "notifications.navigation.anchor"
    )


def test_paths_to_text_empty() -> None:
    assert paths_to_text(None) == ""


def test_normalize_notification_prefixes() -> None:
    prefixes = normalize_notification_prefixes(
        "notifications.security.*\nsecurity.accessRequest\n\n"
    )
    assert prefixes == [
        "notifications.security.",
        "notifications.security.accessRequest.",
    ]


def test_normalize_notification_prefixes_dedupes() -> None:
    prefixes = normalize_notification_prefixes(
        ["notifications.security.", "security", "notifications.security.*"]
    )
    assert prefixes == ["notifications.security."]


def test_normalize_notification_prefixes_invalid_input() -> None:
    assert normalize_notification_prefixes(42) == []


def test_normalize_notification_prefixes_empty() -> None:
    assert normalize_notification_prefixes(None) == []


def test_normalize_notification_prefixes_skips_non_string_items() -> None:
    prefixes = normalize_notification_prefixes(["notifications.security.", None])
    assert prefixes == ["notifications.security."]
