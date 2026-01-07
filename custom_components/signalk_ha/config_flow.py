from __future__ import annotations

import asyncio
import ssl
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientConnectorError, ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import (
    AccessRequestInfo,
    AccessRequestRejected,
    AccessRequestUnsupported,
    AuthRequired,
    async_create_access_request,
    async_poll_access_request,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_GROUPS,
    CONF_HOST,
    CONF_INSTANCE_ID,
    CONF_NOTIFICATION_PATHS,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SERVER_ID,
    CONF_SERVER_VERSION,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DEFAULT_ENABLE_NOTIFICATIONS,
    DEFAULT_GROUPS,
    DEFAULT_NOTIFICATION_PATHS,
    DEFAULT_PORT,
    DEFAULT_REFRESH_INTERVAL_HOURS,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .identity import build_instance_id, resolve_vessel_identity
from .notifications import normalize_notification_paths, paths_to_text
from .rest import (
    DiscoveryInfo,
    async_fetch_discovery,
    async_fetch_vessel_self,
    normalize_base_url,
    normalize_host_input,
    normalize_server_url,
    normalize_ws_url,
)
from .schema import SCHEMA_GROUPS


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._pending_data: dict[str, Any] | None = None
        self._access_request: AccessRequestInfo | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._auth_task: asyncio.Task[tuple[str, dict[str, Any]]] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            host, port_override, scheme_override = normalize_host_input(host)
            port = port_override or user_input[CONF_PORT]
            use_ssl = user_input[CONF_SSL]
            if scheme_override in ("http", "https"):
                use_ssl = scheme_override == "https"

            server_url = normalize_server_url(host, port, use_ssl)

            try:
                discovery = await self._async_discover_server(
                    server_url, user_input[CONF_VERIFY_SSL]
                )
            except (asyncio.TimeoutError, ClientConnectorError, ClientError, OSError, ssl.SSLError):
                errors["base"] = "cannot_connect"
            except AuthRequired:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "discovery_failed"
            else:
                base_url = discovery.base_url
                ws_url = discovery.ws_url
                try:
                    vessel_data = await self._async_validate_connection(
                        base_url, user_input[CONF_VERIFY_SSL]
                    )
                except AuthRequired:
                    try:
                        access_request = await self._async_start_access_request(
                            base_url,
                            user_input[CONF_VERIFY_SSL],
                            host=host,
                            port=port,
                        )
                    except AccessRequestUnsupported:
                        errors["base"] = "auth_not_supported"
                    except AuthRequired:
                        errors["base"] = "auth_required"
                    except (asyncio.TimeoutError, ClientConnectorError, ClientError, OSError):
                        errors["base"] = "cannot_connect"
                    else:
                        groups = _normalize_groups(user_input.get(CONF_GROUPS))
                        self._pending_data = {
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_SSL: use_ssl,
                            CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                            CONF_BASE_URL: base_url,
                            CONF_WS_URL: ws_url,
                            CONF_SERVER_ID: discovery.server_id,
                            CONF_SERVER_VERSION: discovery.server_version,
                            CONF_GROUPS: groups,
                        }
                        self._access_request = access_request
                        self._auth_task = None
                        return await self.async_step_auth()
                except (
                    asyncio.TimeoutError,
                    ClientConnectorError,
                    ClientError,
                    OSError,
                    ssl.SSLError,
                ):
                    errors["base"] = "cannot_connect"
                except ValueError:
                    errors["base"] = "invalid_response"
                else:
                    groups = _normalize_groups(user_input.get(CONF_GROUPS))
                    return await self._async_finish_setup(
                        host=host,
                        port=port,
                        use_ssl=use_ssl,
                        verify_ssl=user_input[CONF_VERIFY_SSL],
                        base_url=base_url,
                        ws_url=ws_url,
                        vessel_data=vessel_data,
                        access_token=None,
                        groups=groups,
                        server_id=discovery.server_id,
                        server_version=discovery.server_version,
                    )

        group_options = _group_options()
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
                vol.Optional(CONF_GROUPS, default=list(DEFAULT_GROUPS)): cv.multi_select(
                    group_options
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _async_discover_server(
        self, server_url: str, verify_ssl: bool
    ) -> DiscoveryInfo:
        session = async_get_clientsession(self.hass)
        return await async_fetch_discovery(session, server_url, verify_ssl)

    async def _async_validate_connection(self, base_url: str, verify_ssl: bool) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        return await async_fetch_vessel_self(session, base_url, verify_ssl)

    async def async_step_auth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._pending_data or not self._access_request:
            return self.async_abort(reason="auth_cancelled")

        if user_input is not None:
            self._auth_task = None

        if not self._auth_task:
            self._auth_task = self.hass.async_create_task(
                self._async_poll_and_fetch(), eager_start=False
            )

        if not self._auth_task.done():
            approval_url = None
            if self._pending_data:
                approval_url = _admin_access_url(self._pending_data[CONF_BASE_URL])
            if not approval_url and self._access_request:
                approval_url = self._access_request.approval_url

            return self.async_show_progress(
                step_id="auth",
                progress_action="auth",
                description_placeholders={"approval_url": approval_url or ""},
                progress_task=self._auth_task,
            )

        return self.async_show_progress_done(next_step_id="auth_finish")

    async def async_step_auth_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._pending_data or not self._access_request or not self._auth_task:
            return self.async_abort(reason="auth_cancelled")

        errors: dict[str, str] = {}
        try:
            token, vessel_data = await self._auth_task
        except AccessRequestRejected:
            errors["base"] = "auth_rejected"
        except AccessRequestUnsupported:
            errors["base"] = "auth_not_supported"
        except asyncio.TimeoutError:
            errors["base"] = "auth_timeout"
        except AuthRequired:
            errors["base"] = "auth_failed"
        except (ClientConnectorError, ClientError, OSError, ssl.SSLError):
            errors["base"] = "cannot_connect"
        except ValueError:
            errors["base"] = "invalid_response"
        else:
            self._auth_task = None
            return await self._async_finish_setup(
                host=self._pending_data[CONF_HOST],
                port=self._pending_data[CONF_PORT],
                use_ssl=self._pending_data[CONF_SSL],
                verify_ssl=self._pending_data[CONF_VERIFY_SSL],
                base_url=self._pending_data[CONF_BASE_URL],
                ws_url=self._pending_data[CONF_WS_URL],
                vessel_data=vessel_data,
                access_token=token,
                groups=_normalize_groups(self._pending_data.get(CONF_GROUPS)),
                server_id=self._pending_data.get(CONF_SERVER_ID),
                server_version=self._pending_data.get(CONF_SERVER_VERSION),
            )

        self._auth_task = None
        return self._show_auth_form(errors=errors)

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry_id = self.context.get("entry_id")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return self.async_abort(reason="auth_cancelled")
        self._reauth_entry = entry

        data = entry.data
        base_url = data.get(CONF_BASE_URL) or normalize_base_url(
            data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]
        )
        ws_url = data.get(CONF_WS_URL) or normalize_ws_url(
            data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]
        )

        try:
            access_request = await self._async_start_access_request(
                base_url,
                data[CONF_VERIFY_SSL],
                host=data[CONF_HOST],
                port=data[CONF_PORT],
            )
        except AccessRequestUnsupported:
            return self.async_abort(reason="auth_not_supported")
        except AuthRequired:
            return self.async_abort(reason="auth_required")
        except (asyncio.TimeoutError, ClientConnectorError, ClientError, OSError):
            return self.async_abort(reason="cannot_connect")

        self._pending_data = {
            CONF_HOST: data[CONF_HOST],
            CONF_PORT: data[CONF_PORT],
            CONF_SSL: data[CONF_SSL],
            CONF_VERIFY_SSL: data[CONF_VERIFY_SSL],
            CONF_BASE_URL: base_url,
            CONF_WS_URL: ws_url,
            CONF_GROUPS: data.get(CONF_GROUPS),
            CONF_SERVER_ID: data.get(CONF_SERVER_ID),
            CONF_SERVER_VERSION: data.get(CONF_SERVER_VERSION),
        }
        self._access_request = access_request
        self._auth_task = None
        return await self.async_step_auth()

    async def _async_start_access_request(
        self, base_url: str, verify_ssl: bool, *, host: str, port: int
    ) -> AccessRequestInfo:
        session = async_get_clientsession(self.hass)
        client_id = f"{DOMAIN}:{host}:{port}"
        return await async_create_access_request(
            session,
            base_url,
            verify_ssl,
            client_id=client_id,
        )

    async def _async_finish_setup(
        self,
        *,
        host: str,
        port: int,
        use_ssl: bool,
        verify_ssl: bool,
        base_url: str,
        ws_url: str,
        vessel_data: dict[str, Any],
        access_token: str | None,
        groups: list[str],
        server_id: str | None,
        server_version: str | None,
    ) -> FlowResult:
        identity = resolve_vessel_identity(vessel_data, base_url)
        instance_id = build_instance_id(base_url, identity.vessel_id)
        if self._reauth_entry is None:
            await self.async_set_unique_id(instance_id)
            self._abort_if_unique_id_configured()

        data = {
            **(self._reauth_entry.data if self._reauth_entry is not None else {}),
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_SSL: use_ssl,
            CONF_VERIFY_SSL: verify_ssl,
            CONF_BASE_URL: base_url,
            CONF_WS_URL: ws_url,
            CONF_VESSEL_ID: identity.vessel_id,
            CONF_VESSEL_NAME: identity.vessel_name,
            CONF_INSTANCE_ID: instance_id,
            CONF_SERVER_ID: server_id or "",
            CONF_SERVER_VERSION: server_version or "",
            CONF_REFRESH_INTERVAL_HOURS: DEFAULT_REFRESH_INTERVAL_HOURS,
            CONF_GROUPS: groups,
        }
        if access_token:
            data[CONF_ACCESS_TOKEN] = access_token
        else:
            data.pop(CONF_ACCESS_TOKEN, None)

        if self._reauth_entry is not None:
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title=f"Signal K ({identity.vessel_name})", data=data)

    async def _async_poll_and_fetch(self) -> tuple[str, dict[str, Any]]:
        assert self._pending_data is not None
        assert self._access_request is not None
        session = async_get_clientsession(self.hass)
        token = await async_poll_access_request(
            session,
            self._pending_data[CONF_BASE_URL],
            self._pending_data[CONF_VERIFY_SSL],
            self._access_request,
        )
        vessel_data = await async_fetch_vessel_self(
            session,
            self._pending_data[CONF_BASE_URL],
            self._pending_data[CONF_VERIFY_SSL],
            token=token,
        )
        return token, vessel_data

    def _show_auth_form(self, errors: dict[str, str] | None = None) -> FlowResult:
        approval_url = None
        if self._pending_data:
            approval_url = _admin_access_url(self._pending_data[CONF_BASE_URL])
        if not approval_url and self._access_request:
            approval_url = self._access_request.approval_url

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({}),
            errors=errors or {},
            description_placeholders={"approval_url": approval_url or ""},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            hours = int(user_input[CONF_REFRESH_INTERVAL_HOURS])
            notifications_enabled = bool(user_input[CONF_ENABLE_NOTIFICATIONS])
            groups = _normalize_groups(user_input.get(CONF_GROUPS))
            notification_paths = normalize_notification_paths(
                user_input.get(CONF_NOTIFICATION_PATHS)
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_REFRESH_INTERVAL_HOURS: hours,
                    CONF_ENABLE_NOTIFICATIONS: notifications_enabled,
                    CONF_NOTIFICATION_PATHS: notification_paths,
                    CONF_GROUPS: groups,
                },
            )

        current = self._entry.options.get(
            CONF_REFRESH_INTERVAL_HOURS,
            self._entry.data.get(CONF_REFRESH_INTERVAL_HOURS, DEFAULT_REFRESH_INTERVAL_HOURS),
        )
        current_groups = _normalize_groups(
            self._entry.options.get(CONF_GROUPS, self._entry.data.get(CONF_GROUPS))
        )
        current_notifications = self._entry.options.get(
            CONF_ENABLE_NOTIFICATIONS, DEFAULT_ENABLE_NOTIFICATIONS
        )
        current_notification_paths = paths_to_text(
            self._entry.options.get(CONF_NOTIFICATION_PATHS, DEFAULT_NOTIFICATION_PATHS)
        )
        group_options = _group_options()
        schema = vol.Schema(
            {
                vol.Optional(CONF_REFRESH_INTERVAL_HOURS, default=current): vol.Coerce(int),
                vol.Optional(CONF_ENABLE_NOTIFICATIONS, default=current_notifications): cv.boolean,
                vol.Optional(
                    CONF_NOTIFICATION_PATHS, default=current_notification_paths
                ): cv.string,
                vol.Optional(CONF_GROUPS, default=current_groups): cv.multi_select(group_options),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _admin_access_url(base_url: str) -> str | None:
    if not base_url:
        return None
    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "/admin/", "", "/security/access/requests"))


def _group_options() -> dict[str, str]:
    return {group: group.replace("_", " ").title() for group in SCHEMA_GROUPS}


def _normalize_groups(groups: Any | None) -> list[str]:
    if not groups:
        return list(DEFAULT_GROUPS)
    selected = [group for group in groups if isinstance(group, str)]
    allowed = set(SCHEMA_GROUPS)
    filtered = [group for group in selected if group in allowed]
    return filtered or list(DEFAULT_GROUPS)
