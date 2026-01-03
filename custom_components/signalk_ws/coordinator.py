from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiohttp import ClientError, ClientTimeout, WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONTEXT,
    CONF_HOST,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_PORT,
    CONF_SSL,
)
from .parser import extract_values
from .subscription import build_subscribe_payload

_LOGGER = logging.getLogger(__name__)

_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 30.0
_BACKOFF_JITTER = 1.0
_COALESCE_SECONDS = 0.5
_LOG_INTERVAL_SECONDS = 60.0


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    SUBSCRIBING = "subscribing"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass(frozen=True)
class SignalKConfig:
    host: str
    port: int
    ssl: bool
    context: str
    period_ms: int
    paths: list[str]


@dataclass
class SignalKStats:
    messages: int = 0
    parse_errors: int = 0
    reconnects: int = 0


class SignalKCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"Signal K WS {entry.entry_id}")

        self._entry = entry
        self._session = async_get_clientsession(hass)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._ws = None
        self._flush_handle: asyncio.TimerHandle | None = None
        self._log_times: dict[str, float] = {}

        self._state = ConnectionState.DISCONNECTED
        self._last_error: str | None = None
        self._last_message = None
        self._last_update_by_path: dict[str, Any] = {}
        self._stats = SignalKStats()
        self._data_cache: dict[str, Any] = {}

        self.data = {}

    @property
    def config(self) -> SignalKConfig:
        data = self._entry.data
        opts = self._entry.options

        paths = opts.get(CONF_PATHS, data.get(CONF_PATHS, []))
        period_ms = opts.get(CONF_PERIOD_MS, data.get(CONF_PERIOD_MS, 1000))

        return SignalKConfig(
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            ssl=data[CONF_SSL],
            context=data[CONF_CONTEXT],
            period_ms=int(period_ms),
            paths=list(paths),
        )

    @property
    def connection_state(self) -> str:
        return self._state.value

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def last_message(self):
        return self._last_message

    @property
    def reconnect_count(self) -> int:
        return self._stats.reconnects

    @property
    def counters(self) -> dict[str, int]:
        return {
            "messages": self._stats.messages,
            "parse_errors": self._stats.parse_errors,
            "reconnects": self._stats.reconnects,
        }

    @property
    def last_update_by_path(self) -> dict[str, Any]:
        return dict(self._last_update_by_path)

    async def async_start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = self.hass.async_create_task(self._run())

    async def async_stop(self) -> None:
        self._stop_event.set()
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._set_state(ConnectionState.DISCONNECTED)

    async def _run(self) -> None:
        backoff = _BACKOFF_MIN
        while not self._stop_event.is_set():
            cfg = self.config
            scheme = "wss" if cfg.ssl else "ws"
            url = f"{scheme}://{cfg.host}:{cfg.port}/signalk/v1/stream?subscribe=none"

            self._set_state(ConnectionState.CONNECTING)
            try:
                _LOGGER.debug("Connecting to Signal K WS: %s", url)
                async with self._session.ws_connect(
                    url,
                    heartbeat=30,
                    timeout=ClientTimeout(total=10),
                ) as ws:
                    self._ws = ws
                    backoff = _BACKOFF_MIN

                    self._set_state(ConnectionState.SUBSCRIBING)
                    await self._send_subscribe(ws, cfg)

                    self._set_state(ConnectionState.CONNECTED)

                    async for msg in ws:
                        if self._stop_event.is_set():
                            break

                        if msg.type == WSMsgType.TEXT:
                            self._handle_message(msg.data, cfg)
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSE, WSMsgType.CLOSING):
                            break
                        elif msg.type == WSMsgType.ERROR:
                            err = ws.exception()
                            if err:
                                self._record_error(f"WebSocket error: {err}")
                            break

            except (asyncio.TimeoutError, ClientError, OSError) as ex:
                self._record_error(f"{type(ex).__name__}: {ex}")
                _LOGGER.warning("Signal K WS connection error: %s", ex)
            except asyncio.CancelledError:
                return
            except Exception as ex:  # last resort
                self._record_error(f"Unexpected: {type(ex).__name__}: {ex}")
                _LOGGER.exception("Unexpected error in Signal K WS loop: %s", ex)
            finally:
                self._ws = None

            if self._stop_event.is_set():
                break

            self._stats.reconnects += 1
            self._set_state(ConnectionState.RECONNECTING)

            delay = min(backoff, _BACKOFF_MAX) + random.uniform(0, _BACKOFF_JITTER)
            await asyncio.sleep(delay)
            backoff = min(backoff * 2.0, _BACKOFF_MAX)

        self._set_state(ConnectionState.DISCONNECTED)

    async def _send_subscribe(self, ws, cfg: SignalKConfig) -> None:
        payload = build_subscribe_payload(cfg.context, cfg.paths, cfg.period_ms)
        await ws.send_str(json.dumps(payload))
        _LOGGER.debug("Sent subscribe: %s", payload)

    def _handle_message(self, text: str, cfg: SignalKConfig) -> None:
        self._stats.messages += 1
        self._last_message = dt_util.utcnow()

        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            self._stats.parse_errors += 1
            self._log_rate_limited(
                logging.WARNING,
                "Signal K WS message parse error (invalid JSON).",
                key="parse_error",
            )
            return

        changed = extract_values(obj, cfg.context)
        if not changed:
            self._schedule_flush()
            return

        now = dt_util.utcnow()
        for path in changed:
            self._last_update_by_path[path] = now

        self._data_cache.update(changed)
        self._schedule_flush()

    def _schedule_flush(self, immediate: bool = False) -> None:
        if immediate:
            if self._flush_handle is not None:
                self._flush_handle.cancel()
                self._flush_handle = None
            self.async_set_updated_data(dict(self._data_cache))
            return

        if self._flush_handle is not None:
            return

        self._flush_handle = self.hass.loop.call_later(_COALESCE_SECONDS, self._flush_updates)

    def _flush_updates(self) -> None:
        self._flush_handle = None
        self.async_set_updated_data(dict(self._data_cache))

    def _set_state(self, state: ConnectionState) -> None:
        if self._state == state:
            return
        self._state = state
        if state == ConnectionState.CONNECTED:
            self._last_error = None
        self._schedule_flush(immediate=True)

    def _record_error(self, message: str) -> None:
        self._last_error = message[:200]
        self._schedule_flush(immediate=True)

    def _log_rate_limited(self, level: int, message: str, *, key: str) -> None:
        now = time.monotonic()
        last = self._log_times.get(key, 0.0)
        if now - last < _LOG_INTERVAL_SECONDS:
            return
        self._log_times[key] = now
        _LOGGER.log(level, message)
