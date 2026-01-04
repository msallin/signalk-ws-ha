from __future__ import annotations

import asyncio
import ssl
from typing import Any

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
    CONF_FORMAT,
    CONF_HOST,
    CONF_MIN_PERIOD_MS,
    CONF_PATH,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_POLICY,
    CONF_PORT,
    CONF_PRESET,
    CONF_SSL,
    CONF_SUBSCRIPTIONS,
    CONF_VERIFY_SSL,
    CONF_VESSEL_NAME,
    DEFAULT_CONTEXT,
    DEFAULT_FORMAT,
    DEFAULT_MIN_PERIOD_MS,
    DEFAULT_PATHS,
    DEFAULT_PERIOD_MS,
    DEFAULT_POLICY,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_VERIFY_SSL,
    DEFAULT_VESSEL_NAME,
    DOMAIN,
    PRESET_BATTERIES,
    PRESET_CUSTOM,
    PRESET_DEPTH,
    PRESET_NAVIGATION,
    PRESET_PATHS,
    PRESET_TANKS,
    PRESET_WIND,
)
from .subscription import normalize_subscriptions, paths_to_subscriptions

_FORMATS = ["delta", "full"]
_POLICIES = ["instant", "ideal", "fixed"]


def _build_subscription(path: str, data: dict[str, Any]) -> dict[str, Any]:
    period = int(data.get(CONF_PERIOD_MS, DEFAULT_PERIOD_MS))
    fmt = str(data.get(CONF_FORMAT, DEFAULT_FORMAT)).lower()
    policy = str(data.get(CONF_POLICY, DEFAULT_POLICY)).lower()
    min_period = int(data.get(CONF_MIN_PERIOD_MS, DEFAULT_MIN_PERIOD_MS))

    spec: dict[str, Any] = {
        "path": path,
        "period": period,
        "format": fmt,
        "policy": policy,
    }
    if min_period:
        spec["minPeriod"] = min_period
    return spec


def _entry_subscriptions(entry: config_entries.ConfigEntry) -> list[dict[str, Any]]:
    opts = entry.options
    data = entry.data
    if CONF_SUBSCRIPTIONS in opts:
        subscriptions = opts.get(CONF_SUBSCRIPTIONS)
    elif CONF_SUBSCRIPTIONS in data:
        subscriptions = data.get(CONF_SUBSCRIPTIONS)
    else:
        subscriptions = None
    period_ms = opts.get(CONF_PERIOD_MS, data.get(CONF_PERIOD_MS, DEFAULT_PERIOD_MS))
    if subscriptions is not None:
        return normalize_subscriptions(subscriptions, default_period_ms=period_ms)

    paths = opts.get(CONF_PATHS, data.get(CONF_PATHS, DEFAULT_PATHS))
    return paths_to_subscriptions(paths, period_ms=period_ms)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._preset: str = PRESET_CUSTOM
        self._config_data: dict[str, Any] = {}
        self._subscriptions: list[dict[str, Any]] = []
        self._pending_preset_paths: list[str] = []

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
                user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            )
            if error:
                errors["base"] = error
            else:
                self._config_data = {
                    CONF_HOST: host,
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SSL: user_input[CONF_SSL],
                    CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    CONF_CONTEXT: context,
                    CONF_VESSEL_NAME: user_input[CONF_VESSEL_NAME].strip(),
                }
                self._pending_preset_paths = list(PRESET_PATHS.get(self._preset, DEFAULT_PATHS))
                return await self.async_step_subscription()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
                vol.Optional(CONF_CONTEXT, default=DEFAULT_CONTEXT): cv.string,
                vol.Required(CONF_VESSEL_NAME, default=DEFAULT_VESSEL_NAME): cv.string,
            }
        )
        return self.async_show_form(step_id="config", data_schema=schema, errors=errors)

    async def async_step_subscription(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        preset_path = self._pending_preset_paths[0] if self._pending_preset_paths else ""
        from_preset = bool(preset_path)

        if user_input is not None:
            path = user_input.get(CONF_PATH, "").strip()
            include = user_input.get("include", True)

            if include and path:
                self._subscriptions.append(_build_subscription(path, user_input))

            if self._pending_preset_paths:
                self._pending_preset_paths.pop(0)

            if self._pending_preset_paths:
                return await self.async_step_subscription()

            if user_input.get("add_another"):
                return await self.async_step_subscription()

            if not self._subscriptions:
                errors["base"] = "no_subscriptions"
            else:
                data = dict(self._config_data)
                data[CONF_SUBSCRIPTIONS] = normalize_subscriptions(self._subscriptions)
                return self.async_create_entry(
                    title=f"Signal K ({self._config_data[CONF_HOST]})",
                    data=data,
                )

        selector_schema: dict[Any, Any] = {
            vol.Required(CONF_PATH, default=preset_path): cv.string,
            vol.Optional(CONF_PERIOD_MS, default=DEFAULT_PERIOD_MS): vol.Coerce(int),
            vol.Optional(CONF_FORMAT, default=DEFAULT_FORMAT): SelectSelector(
                SelectSelectorConfig(options=_FORMATS, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_POLICY, default=DEFAULT_POLICY): SelectSelector(
                SelectSelectorConfig(options=_POLICIES, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_MIN_PERIOD_MS, default=DEFAULT_MIN_PERIOD_MS): vol.Coerce(int),
            vol.Optional("add_another", default=not from_preset): cv.boolean,
        }
        if from_preset:
            selector_schema[vol.Optional("include", default=True)] = cv.boolean

        schema = vol.Schema(selector_schema)
        return self.async_show_form(step_id="subscription", data_schema=schema, errors=errors)

    async def _async_validate_connection(
        self, host: str, port: int, use_ssl: bool, verify_ssl: bool
    ) -> str | None:
        session = async_get_clientsession(self.hass)
        scheme = "wss" if use_ssl else "ws"
        url = f"{scheme}://{host}:{port}/signalk/v1/stream?subscribe=none"
        ssl_context = None
        if use_ssl and not verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            async with async_timeout.timeout(8):
                async with session.ws_connect(url, heartbeat=30, ssl=ssl_context) as ws:
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
        self._options: dict[str, Any] = {}
        self._subscriptions: list[dict[str, Any]] = []

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        current_verify_ssl = self._entry.options.get(
            CONF_VERIFY_SSL, self._entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        )
        current_vessel_name = self._entry.options.get(
            CONF_VESSEL_NAME, self._entry.data.get(CONF_VESSEL_NAME, DEFAULT_VESSEL_NAME)
        )
        if user_input is not None:
            verify_ssl = user_input.get(CONF_VERIFY_SSL, current_verify_ssl)
            vessel_name = user_input.get(CONF_VESSEL_NAME, current_vessel_name).strip()
            if user_input.get("edit_subscriptions"):
                self._options = dict(self._entry.options)
                self._options[CONF_VERIFY_SSL] = verify_ssl
                self._options[CONF_VESSEL_NAME] = vessel_name
                self._subscriptions = []
                return await self.async_step_subscription()

            options = dict(self._entry.options)
            options[CONF_VERIFY_SSL] = verify_ssl
            options[CONF_VESSEL_NAME] = vessel_name
            options.setdefault(CONF_SUBSCRIPTIONS, _entry_subscriptions(self._entry))
            return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Optional(CONF_VERIFY_SSL, default=current_verify_ssl): cv.boolean,
                vol.Optional(CONF_VESSEL_NAME, default=current_vessel_name): cv.string,
                vol.Optional("edit_subscriptions", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_subscription(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            path = user_input.get(CONF_PATH, "").strip()
            if path:
                self._subscriptions.append(_build_subscription(path, user_input))

            if user_input.get("add_another"):
                return await self.async_step_subscription()

            if not self._subscriptions:
                errors["base"] = "no_subscriptions"
            else:
                options = dict(self._options)
                options[CONF_SUBSCRIPTIONS] = normalize_subscriptions(self._subscriptions)
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(CONF_PATH): cv.string,
                vol.Optional(CONF_PERIOD_MS, default=DEFAULT_PERIOD_MS): vol.Coerce(int),
                vol.Optional(CONF_FORMAT, default=DEFAULT_FORMAT): SelectSelector(
                    SelectSelectorConfig(options=_FORMATS, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_POLICY, default=DEFAULT_POLICY): SelectSelector(
                    SelectSelectorConfig(options=_POLICIES, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(CONF_MIN_PERIOD_MS, default=DEFAULT_MIN_PERIOD_MS): vol.Coerce(int),
                vol.Optional("add_another", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="subscription", data_schema=schema, errors=errors)
