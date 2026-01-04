import ssl

from custom_components.signalk_ha.coordinator import SignalKConfig, SignalKCoordinator


def test_build_ssl_context_disabled() -> None:
    cfg = SignalKConfig(
        host="sk.local",
        port=3000,
        ssl=True,
        verify_ssl=False,
        base_url="http://sk.local:3000/signalk/v1/api/",
        ws_url="wss://sk.local:3000/signalk/v1/stream?subscribe=none",
        vessel_id="mmsi:261006533",
        vessel_name="ONA",
    )

    context = SignalKCoordinator._build_ssl_context(cfg)
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_build_ssl_context_default() -> None:
    cfg = SignalKConfig(
        host="sk.local",
        port=3000,
        ssl=True,
        verify_ssl=True,
        base_url="http://sk.local:3000/signalk/v1/api/",
        ws_url="wss://sk.local:3000/signalk/v1/stream?subscribe=none",
        vessel_id="mmsi:261006533",
        vessel_name="ONA",
    )

    assert SignalKCoordinator._build_ssl_context(cfg) is None


def test_build_ssl_context_no_tls() -> None:
    cfg = SignalKConfig(
        host="sk.local",
        port=3000,
        ssl=False,
        verify_ssl=False,
        base_url="http://sk.local:3000/signalk/v1/api/",
        ws_url="ws://sk.local:3000/signalk/v1/stream?subscribe=none",
        vessel_id="mmsi:261006533",
        vessel_name="ONA",
    )

    assert SignalKCoordinator._build_ssl_context(cfg) is None
