from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ws.config_flow import _entry_subscriptions
from custom_components.signalk_ws.const import (
    CONF_CONTEXT,
    CONF_HOST,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_PORT,
    CONF_SSL,
    CONF_SUBSCRIPTIONS,
    DOMAIN,
)


def test_entry_subscriptions_falls_back_to_paths() -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_CONTEXT: "vessels.self",
            CONF_PERIOD_MS: 1500,
            CONF_PATHS: ["navigation.speedOverGround"],
        },
    )

    subs = _entry_subscriptions(entry)
    assert subs == [
        {
            "path": "navigation.speedOverGround",
            "period": 1500,
            "format": "delta",
            "policy": "ideal",
        }
    ]


def test_entry_subscriptions_prefers_subscription_list() -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_CONTEXT: "vessels.self",
            CONF_SUBSCRIPTIONS: [
                {
                    "path": "navigation.speedOverGround",
                    "period": 1000,
                    "format": "delta",
                    "policy": "ideal",
                }
            ],
        },
    )

    subs = _entry_subscriptions(entry)
    assert subs[0]["path"] == "navigation.speedOverGround"
