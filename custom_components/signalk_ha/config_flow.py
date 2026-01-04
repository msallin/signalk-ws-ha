from __future__ import annotations

import asyncio
import ssl
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientConnectorError, ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_INSTANCE_ID,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DEFAULT_PORT,
    DEFAULT_REFRESH_INTERVAL_HOURS,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .identity import build_instance_id, resolve_vessel_identity
from .rest import (
    async_fetch_vessel_self,
    normalize_base_url,
    normalize_host_input,
    normalize_ws_url,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            host, port_override, scheme_override = normalize_host_input(host)
            port = port_override or user_input[CONF_PORT]
            use_ssl = user_input[CONF_SSL]
            if scheme_override in ("http", "https"):
                use_ssl = scheme_override == "https"

            base_url = normalize_base_url(host, port, use_ssl)
            ws_url = normalize_ws_url(host, port, use_ssl)

            try:
                vessel_data = await self._async_validate_connection(
                    base_url, user_input[CONF_VERIFY_SSL]
                )
            except (asyncio.TimeoutError, ClientConnectorError, ClientError, OSError, ssl.SSLError):
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_response"
            else:
                identity = resolve_vessel_identity(vessel_data, base_url)
                instance_id = build_instance_id(base_url, identity.vessel_id)
                await self.async_set_unique_id(instance_id)
                self._abort_if_unique_id_configured()

                data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SSL: use_ssl,
                    CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    CONF_BASE_URL: base_url,
                    CONF_WS_URL: ws_url,
                    CONF_VESSEL_ID: identity.vessel_id,
                    CONF_VESSEL_NAME: identity.vessel_name,
                    CONF_INSTANCE_ID: instance_id,
                    CONF_REFRESH_INTERVAL_HOURS: DEFAULT_REFRESH_INTERVAL_HOURS,
                }
                return self.async_create_entry(
                    title=f"Signal K ({identity.vessel_name})", data=data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _async_validate_connection(self, base_url: str, verify_ssl: bool) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        return await async_fetch_vessel_self(session, base_url, verify_ssl)

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
            return self.async_create_entry(
                title="",
                data={CONF_REFRESH_INTERVAL_HOURS: hours},
            )

        current = self._entry.options.get(
            CONF_REFRESH_INTERVAL_HOURS,
            self._entry.data.get(CONF_REFRESH_INTERVAL_HOURS, DEFAULT_REFRESH_INTERVAL_HOURS),
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_REFRESH_INTERVAL_HOURS, default=current): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
