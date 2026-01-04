import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.signalk_ha.auth import (
    AccessRequestInfo,
    AccessRequestUnsupported,
    AuthRequired,
)
from custom_components.signalk_ha.const import (
    CONF_ACCESS_TOKEN,
    CONF_HOST,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    DOMAIN,
)


async def test_config_flow_creates_entry(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(return_value=vessel_data),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VESSEL_NAME] == "ONA"
    assert result["data"][CONF_VESSEL_ID] == "mmsi:261006533"


async def test_config_flow_unique_id_prevents_duplicates(hass, enable_custom_integrations) -> None:
    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(return_value=vessel_data),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_flow_auth_required(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == FlowResultType.FORM

    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url="http://sk.local/approve",
        status_url="http://sk.local/status",
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=[AuthRequired(), vessel_data]),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(return_value=access_request),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_poll_access_request",
            new=AsyncMock(return_value="token123"),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "auth"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCESS_TOKEN] == "token123"


async def test_config_flow_auth_timeout(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=AuthRequired()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(return_value=access_request),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_poll_access_request",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "auth"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_timeout"


async def test_config_flow_auth_not_supported(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=AuthRequired()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(side_effect=AccessRequestUnsupported()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_not_supported"


async def test_reauth_updates_token(hass, enable_custom_integrations) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_VERIFY_SSL: True,
            CONF_VESSEL_ID: "mmsi:261006533",
            CONF_VESSEL_NAME: "ONA",
        },
    )
    entry.add_to_hass(hass)

    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    vessel_data = {"name": "ONA", "mmsi": "261006533"}

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(return_value=access_request),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_poll_access_request",
            new=AsyncMock(return_value="token456"),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(return_value=vessel_data),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "auth"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "token456"


async def test_options_flow_updates_refresh_interval(hass, enable_custom_integrations) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_VERIFY_SSL: True,
            CONF_VESSEL_ID: "mmsi:261006533",
            CONF_VESSEL_NAME: "ONA",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_REFRESH_INTERVAL_HOURS: 12},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REFRESH_INTERVAL_HOURS] == 12
