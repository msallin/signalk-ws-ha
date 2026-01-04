from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_URL,
    CONF_HOST,
    CONF_PORT,
    CONF_REFRESH_INTERVAL_HOURS,
    CONF_SSL,
    CONF_VERIFY_SSL,
    CONF_VESSEL_ID,
    CONF_VESSEL_NAME,
    CONF_WS_URL,
    DEFAULT_FORMAT,
    DEFAULT_POLICY,
    DEFAULT_REFRESH_INTERVAL_HOURS,
)
from .discovery import DiscoveryResult, MetadataConflict, discover_entities
from .identity import resolve_vessel_identity
from .parser import extract_sources, extract_values
from .rest import async_fetch_vessel_self, normalize_base_url, normalize_ws_url
from .subscription import build_subscribe_payload

_LOGGER = logging.getLogger(__name__)

_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 30.0
_BACKOFF_JITTER = 1.0
_COALESCE_SECONDS = 0.5
_LOG_INTERVAL_SECONDS = 60.0
_STALE_CHECK_SECONDS = 60.0
_INACTIVITY_TIMEOUT = 45.0


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
    verify_ssl: bool
    base_url: str
    ws_url: str
    vessel_id: str
    vessel_name: str


@dataclass
class SignalKStats:
    messages: int = 0
    parse_errors: int = 0
    reconnects: int = 0


class SignalKDiscoveryCoordinator(DataUpdateCoordinator[DiscoveryResult]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession) -> None:
        self._entry = entry
        self._session = session
        self._conflicts: list[MetadataConflict] = []
        self._last_refresh: datetime | None = None

        interval_hours = entry.options.get(
            CONF_REFRESH_INTERVAL_HOURS,
            entry.data.get(CONF_REFRESH_INTERVAL_HOURS, DEFAULT_REFRESH_INTERVAL_HOURS),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"Signal K Discovery {entry.entry_id}",
            update_interval=timedelta(hours=int(interval_hours)),
        )

    @property
    def conflicts(self) -> list[MetadataConflict]:
        return list(self._conflicts)

    @property
    def last_refresh(self) -> dt_util.dt | None:
        return self._last_refresh

    async def _async_update_data(self) -> DiscoveryResult:
        cfg = self._config()
        vessel = await async_fetch_vessel_self(self._session, cfg.base_url, cfg.verify_ssl)
        identity = resolve_vessel_identity(vessel, cfg.base_url)
        if identity.vessel_id and identity.vessel_id != cfg.vessel_id:
            _LOGGER.warning(
                "Signal K vessel identity changed from %s to %s; keeping original",
                cfg.vessel_id,
                identity.vessel_id,
            )
        if identity.vessel_name and identity.vessel_name != cfg.vessel_name:
            self.hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, CONF_VESSEL_NAME: identity.vessel_name}
            )

        result = discover_entities(
            vessel, scopes=("electrical", "environment", "tanks", "navigation")
        )
        self._conflicts = result.conflicts
        self._last_refresh = dt_util.utcnow()
        return result

    def _config(self) -> SignalKConfig:
        data = self._entry.data
        return SignalKConfig(
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            ssl=data[CONF_SSL],
            verify_ssl=data[CONF_VERIFY_SSL],
            base_url=data.get(CONF_BASE_URL)
            or normalize_base_url(data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]),
            ws_url=data.get(CONF_WS_URL)
            or normalize_ws_url(data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]),
            vessel_id=data.get(CONF_VESSEL_ID, ""),
            vessel_name=data.get(CONF_VESSEL_NAME, "Unknown Vessel"),
        )

    async def async_stop(self) -> None:
        await self.async_shutdown()


class SignalKCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: ClientSession,
        discovery: SignalKDiscoveryCoordinator,
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"Signal K {entry.entry_id}")
        self._entry = entry
        self._session = session
        self._discovery = discovery
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._ws = None
        self._flush_handle: asyncio.TimerHandle | None = None
        self._log_times: dict[str, float] = {}
        self._stale_unsub: asyncio.TimerHandle | None = None

        self._state = ConnectionState.DISCONNECTED
        self._last_error: str | None = None
        self._last_message = None
        self._last_update_by_path: dict[str, Any] = {}
        self._last_source_by_path: dict[str, str] = {}
        self._stats = SignalKStats()
        self._data_cache: dict[str, Any] = {}
        self._paths: list[str] = []
        self._periods: dict[str, int] = {}
        self._last_backoff: float = 0.0

        self.data = {}

    @property
    def config(self) -> SignalKConfig:
        data = self._entry.data
        return SignalKConfig(
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            ssl=data[CONF_SSL],
            verify_ssl=data[CONF_VERIFY_SSL],
            base_url=data.get(CONF_BASE_URL)
            or normalize_base_url(data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]),
            ws_url=data.get(CONF_WS_URL)
            or normalize_ws_url(data[CONF_HOST], data[CONF_PORT], data[CONF_SSL]),
            vessel_id=data.get(CONF_VESSEL_ID, ""),
            vessel_name=data.get(CONF_VESSEL_NAME, "Unknown Vessel"),
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

    @property
    def last_source_by_path(self) -> dict[str, str]:
        return dict(self._last_source_by_path)

    @property
    def last_backoff(self) -> float:
        return self._last_backoff

    @property
    def subscribed_paths(self) -> list[str]:
        return list(self._paths)

    async def async_start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = self.hass.async_create_task(self._run())
        self._schedule_stale_checks()

    async def async_stop(self) -> None:
        self._stop_event.set()
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        if self._stale_unsub is not None:
            self._stale_unsub.cancel()
            self._stale_unsub = None

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

    async def async_update_paths(
        self, paths: list[str], periods: dict[str, int] | None = None
    ) -> None:
        cleaned = sorted({path for path in paths if isinstance(path, str)})
        periods = periods or {}
        cleaned_periods = {path: int(periods[path]) for path in cleaned if path in periods}
        if cleaned == self._paths and cleaned_periods == self._periods:
            return
        self._paths = cleaned
        self._periods = cleaned_periods
        if (
            self._ws is not None
            and not self._ws.closed
            and self._state == ConnectionState.CONNECTED
        ):
            await self._send_subscribe(self._ws)

    async def _run(self) -> None:
        backoff = _BACKOFF_MIN
        while not self._stop_event.is_set():
            cfg = self.config
            url = cfg.ws_url
            ssl_context = self._build_ssl_context(cfg)

            self._set_state(ConnectionState.CONNECTING)
            try:
                _LOGGER.info("Connecting to Signal K: %s", url)
                async with self._session.ws_connect(
                    url,
                    heartbeat=30,
                    timeout=ClientTimeout(total=10),
                    ssl=ssl_context,
                ) as ws:
                    self._ws = ws
                    backoff = _BACKOFF_MIN
                    self._last_backoff = 0.0

                    self._set_state(ConnectionState.SUBSCRIBING)
                    await self._send_subscribe(ws)

                    self._set_state(ConnectionState.CONNECTED)

                    while not self._stop_event.is_set():
                        try:
                            msg = await ws.receive(timeout=_INACTIVITY_TIMEOUT)
                        except asyncio.TimeoutError:
                            self._record_error("Inactivity timeout")
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
                _LOGGER.warning("Signal K connection error: %s", ex)
            except asyncio.CancelledError:
                return
            except Exception as ex:  # last resort
                self._record_error(f"Unexpected: {type(ex).__name__}: {ex}")
                _LOGGER.exception("Unexpected error in Signal K loop: %s", ex)
            finally:
                self._ws = None
                if self._state == ConnectionState.CONNECTED:
                    _LOGGER.info("Disconnected from Signal K")

            if self._stop_event.is_set():
                break

            self._stats.reconnects += 1
            self._set_state(ConnectionState.RECONNECTING)

            delay = min(backoff, _BACKOFF_MAX) + random.uniform(0, _BACKOFF_JITTER)
            self._last_backoff = delay
            await asyncio.sleep(delay)
            backoff = min(backoff * 2.0, _BACKOFF_MAX)

        self._set_state(ConnectionState.DISCONNECTED)

    async def _send_subscribe(self, ws) -> None:
        payload = build_subscribe_payload(
            "vessels.self",
            [{"path": path, "period": self._periods.get(path)} for path in self._paths],
            fmt=DEFAULT_FORMAT,
            policy=DEFAULT_POLICY,
        )
        await ws.send_str(json.dumps(payload))
        _LOGGER.info("Sent subscribe for %s paths", len(self._paths))

    def _handle_message(self, text: str, cfg: SignalKConfig) -> None:
        self._stats.messages += 1
        self._last_message = dt_util.utcnow()

        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            self._stats.parse_errors += 1
            self._log_rate_limited(
                logging.WARNING,
                "Signal K message parse error (invalid JSON).",
                key="parse_error",
            )
            return

        contexts = self._expected_contexts(cfg)
        changed = extract_values(obj, contexts)
        sources = extract_sources(obj, contexts)
        source_changed = False
        for path, source in sources.items():
            if self._last_source_by_path.get(path) != source:
                self._last_source_by_path[path] = source
                source_changed = True
        if not changed:
            if source_changed:
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

    def _expected_contexts(self, cfg: SignalKConfig) -> list[str]:
        contexts = ["vessels.self"]
        vessel_id = cfg.vessel_id
        if vessel_id:
            if vessel_id.startswith("vessels."):
                contexts.append(vessel_id)
            else:
                contexts.append(f"vessels.{vessel_id}")
                contexts.append(vessel_id)
        return contexts

    @staticmethod
    def _build_ssl_context(cfg: SignalKConfig) -> ssl.SSLContext | None:
        if not cfg.ssl or cfg.verify_ssl:
            return None
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _schedule_stale_checks(self) -> None:
        if self._stale_unsub is not None:
            return
        self._stale_unsub = self.hass.loop.call_later(_STALE_CHECK_SECONDS, self._stale_tick)

    def _stale_tick(self) -> None:
        self._stale_unsub = None
        self._schedule_flush(immediate=True)
        if not self._stop_event.is_set():
            self._schedule_stale_checks()
