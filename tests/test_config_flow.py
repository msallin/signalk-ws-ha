import asyncio
import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.signalk_ha.auth import (
    AccessRequestInfo,
    AccessRequestRejected,
    AccessRequestUnsupported,
    AuthRequired,
)
from custom_components.signalk_ha.config_flow import _admin_access_url
from custom_components.signalk_ha.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_GROUPS,
    CONF_HOST,
    CONF_NOTIFICATION_PATHS,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SERVER_ID,
    CONF_SERVER_VERSION,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    DEFAULT_GROUPS,
    DOMAIN,
)
from custom_components.signalk_ha.rest import DiscoveryInfo, normalize_base_url, normalize_ws_url


def _discovery_info(
    *,
    host: str = "sk.local",
    port: int = 3000,
    use_ssl: bool = False,
    server_version: str | None = "2.19.0",
) -> DiscoveryInfo:
    return DiscoveryInfo(
        base_url=normalize_base_url(host, port, use_ssl),
        ws_url=normalize_ws_url(host, port, use_ssl),
        server_id="signalk-server-node",
        server_version=server_version,
    )


NOTIFICATION_STEP_INPUT = {
    CONF_ENABLE_NOTIFICATIONS: True,
    CONF_NOTIFICATION_PATHS: "notifications.*",
}


async def test_config_flow_creates_entry(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
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
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "notifications"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], NOTIFICATION_STEP_INPUT
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VESSEL_NAME] == "ONA"
    assert result["data"][CONF_VESSEL_ID] == "mmsi:261006533"
    assert result["data"][CONF_GROUPS] == list(DEFAULT_GROUPS)
    assert result["data"][CONF_SERVER_ID] == "signalk-server-node"
    assert result["data"][CONF_SERVER_VERSION] == "2.19.0"


async def test_config_flow_scheme_override(hass, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info(host="sk.local", port=1234, use_ssl=True)),
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
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "https://Sk.Local:1234",
                CONF_PORT: 3000,
                CONF_SSL: False,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "notifications"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], NOTIFICATION_STEP_INPUT
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SSL] is True
    assert result["data"][CONF_PORT] == 1234
    assert result["data"][CONF_HOST] == "sk.local"


async def test_zeroconf_prefills_defaults(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow.context = {}
    info = SimpleNamespace(
        host="sk.local",
        hostname=None,
        port=3443,
        type="_signalk-https._tcp.local.",
        addresses=[],
        properties={b"vname": b"ONA", b"vmmsi": b"261006533"},
    )

    result = await flow.async_step_zeroconf(info)

    assert result["type"] == FlowResultType.FORM
    assert flow._zeroconf_defaults[CONF_HOST] == "sk.local"
    assert flow._zeroconf_defaults[CONF_PORT] == 3443
    assert flow._zeroconf_defaults[CONF_SSL] is True
    assert flow.context["title_placeholders"]["name"] == "ONA (261006533)"


async def test_zeroconf_prefills_self_title(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow.context = {}
    info = SimpleNamespace(
        host="sk.local",
        hostname=None,
        port=3000,
        type="_signalk-http._tcp.local.",
        addresses=[],
        properties={b"self": b"urn:mrn:signalk:uuid:c0d79334-4e25-4245-8892-54e8ccc8021d"},
    )

    result = await flow.async_step_zeroconf(info)

    assert result["type"] == FlowResultType.FORM
    assert (
        flow.context["title_placeholders"]["name"] == "Vessel c0d79334-4e25-4245-8892-54e8ccc8021d"
    )


async def test_zeroconf_ssl_fallback_disables_verify(hass, enable_custom_integrations) -> None:
    info = SimpleNamespace(
        host="sk.local",
        hostname=None,
        port=3443,
        type="_signalk-https._tcp.local.",
        addresses=[],
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] == FlowResultType.FORM

    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(
                side_effect=[
                    ssl.SSLError(),
                    _discovery_info(host="sk.local", port=3443, use_ssl=True),
                ]
            ),
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
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "sk.local",
                CONF_PORT: 3443,
                CONF_SSL: True,
                CONF_VERIFY_SSL: False,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "notifications"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], NOTIFICATION_STEP_INPUT
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VERIFY_SSL] is False


def test_zeroconf_host_uses_hostname() -> None:
    from custom_components.signalk_ha.config_flow import _zeroconf_host

    info = SimpleNamespace(host=None, hostname="Sk.Local.", addresses=[])
    assert _zeroconf_host(info) == "sk.local"


def test_zeroconf_host_uses_address() -> None:
    from custom_components.signalk_ha.config_flow import _zeroconf_host

    info = SimpleNamespace(host=None, hostname=None, addresses=[b"\x0a\x00\x00\x01"])
    assert _zeroconf_host(info) == "10.0.0.1"


def test_zeroconf_use_ssl_non_secure() -> None:
    from custom_components.signalk_ha.config_flow import _zeroconf_use_ssl

    assert _zeroconf_use_ssl("_signalk-http._tcp.local.") is False


def test_build_client_id_format() -> None:
    from custom_components.signalk_ha.config_flow import _build_client_id

    with patch("custom_components.signalk_ha.config_flow.secrets.token_hex") as mock_hex:
        mock_hex.return_value = "444e4b8c945ee7b91eb103df"
        assert _build_client_id() == "homeassistant_signalk_ha-444e-4b8c-945e-e7b91eb103df"


async def test_zeroconf_ws_service_aborts(hass, enable_custom_integrations) -> None:
    info = SimpleNamespace(
        host="sk.local",
        hostname=None,
        port=3000,
        type="_signalk-ws._tcp.local.",
        addresses=[],
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "zeroconf_unsupported"


async def test_config_flow_unique_id_prevents_duplicates(hass, enable_custom_integrations) -> None:
    vessel_data = {"name": "ONA", "mmsi": "261006533"}
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
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
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], NOTIFICATION_STEP_INPUT
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
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], NOTIFICATION_STEP_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_flow_access_request_requires_auth(hass, enable_custom_integrations) -> None:
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
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
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

        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "notifications"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], NOTIFICATION_STEP_INPUT
    )

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
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_timeout"


async def test_config_flow_auth_not_supported(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
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


async def test_config_flow_auth_required(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=AuthRequired()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(side_effect=AuthRequired()),
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
    assert result["errors"]["base"] == "auth_required"


async def test_config_flow_access_request_cannot_connect(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=AuthRequired()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
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
    assert result["errors"]["base"] == "cannot_connect"


async def test_config_flow_invalid_response(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=ValueError()),
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
    assert result["errors"]["base"] == "invalid_response"


async def test_config_flow_discovery_failed(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(side_effect=ValueError()),
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
    assert result["errors"]["base"] == "discovery_failed"


async def test_config_flow_discovery_timeout(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
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
    assert result["errors"]["base"] == "cannot_connect"


async def test_config_flow_cannot_connect(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=ssl.SSLError()),
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
    assert result["errors"]["base"] == "cannot_connect"


async def test_config_flow_auth_failed(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=[AuthRequired(), AuthRequired()]),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_failed"


async def test_auth_step_without_pending_data(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    result = await flow.async_step_auth()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "auth_cancelled"


async def test_auth_step_shows_progress_with_pending(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow._pending_data = {CONF_BASE_URL: "http://sk.local:3000/signalk/v1/api/"}
    flow._access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )
    flow._auth_task = hass.async_create_task(asyncio.Event().wait())

    result = await flow.async_step_auth()
    assert result["type"] == FlowResultType.SHOW_PROGRESS

    flow._auth_task.cancel()


async def test_auth_step_progress_uses_access_request_url(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow._pending_data = {CONF_BASE_URL: ""}
    flow._access_request = AccessRequestInfo(
        request_id="req1",
        approval_url="http://sk.local/approve",
        status_url=None,
    )
    wait_event = asyncio.Event()

    async def _wait() -> None:
        await wait_event.wait()

    with patch.object(flow, "_async_poll_and_fetch", new=AsyncMock(side_effect=_wait)):
        result = await flow.async_step_auth(user_input={})

    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["approval_url"] == "http://sk.local/approve"
    flow._auth_task.cancel()


async def test_auth_finish_aborts_without_pending_data(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    result = await flow.async_step_auth_finish()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "auth_cancelled"


async def test_config_flow_auth_step_not_supported(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_not_supported"


async def test_config_flow_auth_rejected(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
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
            new=AsyncMock(side_effect=AccessRequestRejected()),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth_rejected"


async def test_config_flow_auth_invalid_response(hass, enable_custom_integrations) -> None:
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=[AuthRequired(), ValueError()]),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_response"


async def test_config_flow_auth_cannot_connect(hass, enable_custom_integrations) -> None:
    from aiohttp import ClientError

    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    access_request = AccessRequestInfo(
        request_id="req1",
        approval_url=None,
        status_url=None,
    )

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_discovery",
            new=AsyncMock(return_value=_discovery_info()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_fetch_vessel_self",
            new=AsyncMock(side_effect=[AuthRequired(), ClientError()]),
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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


def test_admin_access_url_from_base_url() -> None:
    assert (
        _admin_access_url("http://sk.local:3000/signalk/v1/api/")
        == "http://sk.local:3000/admin/#/security/access/requests"
    )


def test_admin_access_url_invalid() -> None:
    assert _admin_access_url("") is None
    assert _admin_access_url("http://") is None


def test_auth_form_uses_admin_url_when_base_url_present(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow._pending_data = {CONF_BASE_URL: "http://sk.local:3000/signalk/v1/api/"}
    flow._access_request = AccessRequestInfo(
        request_id="req1",
        approval_url="http://sk.local/approve",
        status_url=None,
    )

    result = flow._show_auth_form()
    assert (
        result["description_placeholders"]["approval_url"]
        == "http://sk.local:3000/admin/#/security/access/requests"
    )


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
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "auth"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "token456"


async def test_reauth_missing_entry_aborts(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": "missing"}
    result = await flow.async_step_reauth()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "auth_cancelled"


async def test_reauth_cannot_connect(hass, enable_custom_integrations) -> None:
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

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_reauth_not_supported(hass, enable_custom_integrations) -> None:
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

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(side_effect=AccessRequestUnsupported()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "auth_not_supported"


async def test_reauth_auth_required(hass, enable_custom_integrations) -> None:
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

    with (
        patch(
            "custom_components.signalk_ha.config_flow.async_create_access_request",
            new=AsyncMock(side_effect=AuthRequired()),
        ),
        patch(
            "custom_components.signalk_ha.config_flow.async_get_clientsession",
            return_value=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "auth_required"


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
        {
            CONF_REFRESH_INTERVAL_HOURS: 12,
            CONF_ENABLE_NOTIFICATIONS: True,
            CONF_NOTIFICATION_PATHS: "notifications.navigation.anchor\nnavigation.course.arrival",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REFRESH_INTERVAL_HOURS] == 12
    assert entry.options[CONF_ENABLE_NOTIFICATIONS] is True
    assert entry.options[CONF_GROUPS] == list(DEFAULT_GROUPS)
    assert entry.options[CONF_NOTIFICATION_PATHS] == [
        "notifications.navigation.anchor",
        "notifications.navigation.course.arrival",
    ]


async def test_auth_form_falls_back_to_access_url(hass) -> None:
    from custom_components.signalk_ha.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow._pending_data = {CONF_HOST: "sk.local", CONF_BASE_URL: ""}
    flow._access_request = AccessRequestInfo(
        request_id="req1",
        approval_url="http://sk.local/approve",
        status_url=None,
    )

    result = flow._show_auth_form()
    assert result["description_placeholders"]["approval_url"] == "http://sk.local/approve"
