import ssl

from custom_components.signalk_ws.coordinator import SignalKConfig, SignalKCoordinator


def test_build_ssl_context_disabled() -> None:
    cfg = SignalKConfig(
        host="sk.local",
        port=3000,
        ssl=True,
        verify_ssl=False,
        context="vessels.self",
        period_ms=1000,
        paths=["navigation.speedOverGround"],
        subscriptions=[
            {
                "path": "navigation.speedOverGround",
                "period": 1000,
                "format": "delta",
                "policy": "ideal",
            }
        ],
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
        context="vessels.self",
        period_ms=1000,
        paths=["navigation.speedOverGround"],
        subscriptions=[
            {
                "path": "navigation.speedOverGround",
                "period": 1000,
                "format": "delta",
                "policy": "ideal",
            }
        ],
    )

    assert SignalKCoordinator._build_ssl_context(cfg) is None


def test_build_ssl_context_no_tls() -> None:
    cfg = SignalKConfig(
        host="sk.local",
        port=3000,
        ssl=False,
        verify_ssl=False,
        context="vessels.self",
        period_ms=1000,
        paths=["navigation.speedOverGround"],
        subscriptions=[
            {
                "path": "navigation.speedOverGround",
                "period": 1000,
                "format": "delta",
                "policy": "ideal",
            }
        ],
    )

    assert SignalKCoordinator._build_ssl_context(cfg) is None
