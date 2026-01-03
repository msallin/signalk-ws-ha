from __future__ import annotations

import asyncio
import ssl

import async_timeout
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientConnectorError, ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .const import (
    CONF_CONTEXT,
    CONF_HOST,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_PORT,
    CONF_PRESET,
    CONF_SSL,
    DEFAULT_CONTEXT,
    DEFAULT_PATHS,
    DEFAULT_PERIOD_MS,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DOMAIN,
    PRESET_BATTERIES,
    PRESET_CUSTOM,
    PRESET_DEPTH,
    PRESET_NAVIGATION,
    PRESET_PATHS,
    PRESET_TANKS,
    PRESET_WIND,
)
from .subscription import sanitize_paths


def _paths_to_text(paths: list[str]) -> str:
    return "\n".join(paths)


def _text_to_paths(text: str) -> list[str]:
    return sanitize_paths((text or "").splitlines())


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._preset: str = PRESET_CUSTOM

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            self._preset = user_input[CONF_PRESET]
            return await self.async_step_config()

        schema = vol.Schema(
            {
                vol.Required(CONF_PRESET, default=PRESET_NAVIGATION): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": PRESET_NAVIGATION, "label": "Navigation basics"},
                            {"value": PRESET_WIND, "label": "Wind"},
                            {"value": PRESET_DEPTH, "label": "Depth"},
                            {"value": PRESET_BATTERIES, "label": "Batteries"},
                            {"value": PRESET_TANKS, "label": "Tanks"},
                            {"value": PRESET_CUSTOM, "label": "Custom"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_config(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            context = user_input[CONF_CONTEXT].strip()
            await self.async_set_unique_id(f"{DOMAIN}:{host}:{user_input[CONF_PORT]}:{context}")
            self._abort_if_unique_id_configured()

            error = await self._async_validate_connection(
                host,
                user_input[CONF_PORT],
                user_input[CONF_SSL],
            )
            if error:
                errors["base"] = error
            else:
                data = {
                    CONF_HOST: host,
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SSL: user_input[CONF_SSL],
                    CONF_CONTEXT: context,
                    CONF_PERIOD_MS: user_input[CONF_PERIOD_MS],
                    CONF_PATHS: _text_to_paths(user_input[CONF_PATHS]),
                }
                return self.async_create_entry(title=f"Signal K ({host})", data=data)

        preset_paths = PRESET_PATHS.get(self._preset, DEFAULT_PATHS)
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
                vol.Optional(CONF_CONTEXT, default=DEFAULT_CONTEXT): cv.string,
                vol.Optional(CONF_PERIOD_MS, default=DEFAULT_PERIOD_MS): vol.Coerce(int),
                vol.Optional(CONF_PATHS, default=_paths_to_text(preset_paths)): cv.string,
            }
        )
        return self.async_show_form(step_id="config", data_schema=schema, errors=errors)

    async def _async_validate_connection(self, host: str, port: int, use_ssl: bool) -> str | None:
        session = async_get_clientsession(self.hass)
        scheme = "wss" if use_ssl else "ws"
        url = f"{scheme}://{host}:{port}/signalk/v1/stream?subscribe=none"

        try:
            async with async_timeout.timeout(8):
                async with session.ws_connect(url, heartbeat=30) as ws:
                    await ws.close()
        except (asyncio.TimeoutError, ClientConnectorError, ClientError, OSError, ssl.SSLError):
            return "cannot_connect"
        return None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_PERIOD_MS: user_input[CONF_PERIOD_MS],
                    CONF_PATHS: _text_to_paths(user_input[CONF_PATHS]),
                },
            )

        current_paths = self._entry.options.get(
            CONF_PATHS, self._entry.data.get(CONF_PATHS, DEFAULT_PATHS)
        )
        current_period = self._entry.options.get(
            CONF_PERIOD_MS, self._entry.data.get(CONF_PERIOD_MS, DEFAULT_PERIOD_MS)
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_PERIOD_MS, default=current_period): vol.Coerce(int),
                vol.Optional(CONF_PATHS, default=_paths_to_text(current_paths)): cv.string,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
