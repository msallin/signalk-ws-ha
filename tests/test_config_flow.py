from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ws.const import (
    CONF_CONTEXT,
    CONF_FORMAT,
    CONF_HOST,
    CONF_MIN_PERIOD_MS,
    CONF_PATH,
    CONF_POLICY,
    CONF_PORT,
    CONF_PRESET,
    CONF_SSL,
    CONF_SUBSCRIPTIONS,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PRESET_CUSTOM,
)


async def test_config_flow_creates_entry(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_CUSTOM},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "config"

    with patch(
        "custom_components.signalk_ws.config_flow.ConfigFlow._async_validate_connection",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
                CONF_CONTEXT: "vessels.self",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "subscription"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PATH: "navigation.speedOverGround",
            CONF_FORMAT: "delta",
            CONF_POLICY: "ideal",
            CONF_MIN_PERIOD_MS: 0,
            "add_another": False,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Signal K (sk.local)"
    assert result["data"][CONF_SUBSCRIPTIONS][0]["path"] == "navigation.speedOverGround"
    assert result["data"][CONF_VERIFY_SSL] is DEFAULT_VERIFY_SSL


async def test_config_flow_unique_id_prevents_duplicates(hass, enable_custom_integrations) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{DOMAIN}:sk.local:3000:vessels.self",
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
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_CUSTOM},
    )

    with patch(
        "custom_components.signalk_ws.config_flow.ConfigFlow._async_validate_connection",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
                CONF_CONTEXT: "vessels.self",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_options(hass, enable_custom_integrations) -> None:
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
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_VERIFY_SSL: False,
            "edit_subscriptions": True,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "subscription"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PATH: "navigation.speedOverGround",
            CONF_FORMAT: "delta",
            CONF_POLICY: "ideal",
            CONF_MIN_PERIOD_MS: 0,
            "add_another": True,
        },
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PATH: "navigation.position",
            CONF_FORMAT: "delta",
            CONF_POLICY: "ideal",
            CONF_MIN_PERIOD_MS: 0,
            "add_another": False,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_VERIFY_SSL] is False
    assert entry.options[CONF_SUBSCRIPTIONS][1]["path"] == "navigation.position"


async def test_custom_preset_defaults_to_empty_paths(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_CUSTOM},
    )

    with patch(
        "custom_components.signalk_ws.config_flow.ConfigFlow._async_validate_connection",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
                CONF_CONTEXT: "vessels.self",
            },
        )

    data = result["data_schema"]({})
    assert data[CONF_PATH] == ""


async def test_config_flow_stores_verify_ssl_false(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_CUSTOM},
    )

    with patch(
        "custom_components.signalk_ws.config_flow.ConfigFlow._async_validate_connection",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: True,
                CONF_VERIFY_SSL: False,
                CONF_CONTEXT: "vessels.self",
            },
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PATH: "navigation.speedOverGround",
            CONF_FORMAT: "delta",
            CONF_POLICY: "ideal",
            CONF_MIN_PERIOD_MS: 0,
            "add_another": False,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VERIFY_SSL] is False
