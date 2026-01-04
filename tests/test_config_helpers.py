from custom_components.signalk_ha.rest import normalize_host_input


def test_normalize_host_input_with_scheme() -> None:
    host, port, scheme = normalize_host_input("https://Sk.Local:1234")
    assert host == "sk.local"
    assert port == 1234
    assert scheme == "https"


def test_normalize_host_input_without_scheme() -> None:
    host, port, scheme = normalize_host_input("sk.local")
    assert host == "sk.local"
    assert port is None
    assert scheme is None
