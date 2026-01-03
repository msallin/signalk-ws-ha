from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ws.const import (
    CONF_CONTEXT,
    CONF_HOST,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_PORT,
    CONF_PRESET,
    CONF_SSL,
    DOMAIN,
    PRESET_CUSTOM,
    PRESET_NAVIGATION,
)


async def test_config_flow_creates_entry(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_NAVIGATION},
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
                CONF_CONTEXT: "vessels.self",
                CONF_PERIOD_MS: 1000,
                CONF_PATHS: "navigation.speedOverGround",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Signal K (sk.local)"


async def test_config_flow_unique_id_prevents_duplicates(hass, enable_custom_integrations) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{DOMAIN}:sk.local:3000:vessels.self",
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_CONTEXT: "vessels.self",
            CONF_PERIOD_MS: 1000,
            CONF_PATHS: ["navigation.speedOverGround"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_NAVIGATION},
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
                CONF_CONTEXT: "vessels.self",
                CONF_PERIOD_MS: 1000,
                CONF_PATHS: "navigation.speedOverGround",
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
            CONF_PERIOD_MS: 1000,
            CONF_PATHS: ["navigation.speedOverGround"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PERIOD_MS: 2000,
            CONF_PATHS: "navigation.speedOverGround\nnavigation.position",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_PERIOD_MS] == 2000
    assert entry.options[CONF_PATHS] == ["navigation.speedOverGround", "navigation.position"]


async def test_custom_preset_defaults_to_empty_paths(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PRESET: PRESET_CUSTOM},
    )

    data = result["data_schema"]({CONF_HOST: "sk.local"})
    assert data[CONF_PATHS] == ""
