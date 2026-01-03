# AGENTS.md

## Mission

Build a production-grade Home Assistant custom integration (HACS) that ingests Signal K data via WebSocket deltas and exposes it as HA sensors with minimal user effort.

Non-negotiables:

- Correct Signal K WebSocket subscription protocol handling (handshake, subscribe, message framing).
- Self-healing networking (robust reconnect, backoff, lifecycle safety, clean unload).
- Diagnostics that make failures obvious and fixable without "IT time".
- Configuration that is easy for sailors: defaults, presets, copy/paste friendly paths, and clear validation.
- One connection per config entry shared by all sensors.

Sailors do not want to debug. Reliability beats features.

## Context: what is already drafted

A minimal skeleton integration named "signalk_ws" was drafted with:

- hacs.json
- custom_components/signalk_ws/
  - manifest.json (config_flow true, iot_class local_push)
  - const.py (defaults: host/port/ssl/context/period_ms, default paths list)
  - __init__.py (setup entry, coordinator start/stop, forward to sensor platform)
  - config_flow.py (basic setup + options for period and paths)
  - coordinator.py (aiohttp WebSocket client, subscribe=none, send subscribe payload, parse deltas to cache, async_set_updated_data)
  - sensor.py (dynamic sensors created from configured paths)
  - strings/translations minimal stubs

Core technical choices:

- WebSocket endpoint: /signalk/v1/stream?subscribe=none
- After connect, send subscription payload:
  {
    "context": "vessels.self",
    "subscribe": [
      { "path": "...", "period": 1000, "format": "delta", "policy": "ideal" }
    ]
  }
- Parse delta frames:
  { "context": "...", "updates": [ { "values": [ { "path": "...", "value": ... } ] } ] }
- Maintain latest-value cache per path, push updates via DataUpdateCoordinator.async_set_updated_data.

This skeleton is functional but not yet production-grade.

## Critical protocol constraints

Do not treat Signal K WS as "data will flow automatically".
With subscribe=none, you must send a correct subscription message after connect, and you must re-subscribe after every reconnect.

Edge cases to handle:

- Initial "hello" and other non-delta frames. Ignore safely.
- Delta frames with multiple updates and multiple values.
- Values can be scalar, object (position), array, or null.
- Context may be absent or may differ if user subscribes broadly.
- Reconnect must re-subscribe. Subscription is not persistent across sessions.
- Do not block the WS receive loop. Avoid CPU spikes and state-write floods.

## What must be implemented or improved

### A) Refactor for testability (first)

Create pure functions (no HA, no aiohttp) so they can be unit-tested deterministically.

Add:

- custom_components/signalk_ws/parser.py
  - extract_values(delta_obj: dict, expected_context: str | None) -> dict[str, Any]
  - parse_delta_text(text: str, expected_context: str | None) -> dict[str, Any] (loads JSON then calls extract)
- custom_components/signalk_ws/subscription.py
  - build_subscribe_payload(context: str, paths: list[str], period_ms: int) -> dict

Update coordinator to call these functions.

### B) Reliability and self-healing connection loop

Implement an explicit connection state machine and robust reconnect logic:

- DISCONNECTED
- CONNECTING
- SUBSCRIBING
- CONNECTED
- RECONNECTING

Requirements:

- Exponential backoff with jitter, bounded (e.g., 1s -> 30s).
- Heartbeat / timeouts configured.
- Re-subscribe after reconnect.
- Clean stop/unload: cancel task, close ws, no orphan tasks.
- Rate-limit noisy logs (parse errors, unknown frames).

### C) UX: Config flow and options flow

Config fields:

- host (required)
- port (default 3000)
- TLS toggle (ws/wss)
- context (default vessels.self)
- period_ms (default 1000)
- paths (multiline, one per line, ignore blank and comment lines)

Usability improvements:

- Presets selector that fills the paths box:
  - Navigation basics (SOG/COG/position)
  - Wind
  - Depth
  - Batteries
  - Tanks (optional)
- Best-effort connectivity check during setup (optional but recommended):
  - attempt WS connect and show actionable form errors (TLS mismatch, refused, timeout)
- Options flow must allow changing period and paths without deleting the integration.

### D) Entity model + metadata

- All sensors attached to one HA device ("Signal K Server <host>").
- Availability reflects connection status.
- Add at least one health entity (recommended):
  - sensor.signalk_ws_connection_state
  - sensor.signalk_ws_last_message
  - sensor.signalk_ws_reconnect_count
  - sensor.signalk_ws_last_error (short string)

Units strategy:

- Baseline: expose raw values.
- Optionally: provide common conversions (radians->degrees, m/s->knots) behind config toggles or separate sensors.
- If you set device_class/state_class, do it only for well-known paths and document it.

### E) Diagnostics and supportability (must-have)

Implement:

- diagnostics.py (HA diagnostics endpoint) that returns:
  - config (redacted)
  - connection state
  - last_error (sanitized)
  - counters (messages, parse_errors, reconnects)
  - last update timestamps per configured path
- Optional persistent notifications for repeated failures (e.g., 10 consecutive reconnect attempts).
- Clear logs, rate-limited, with guidance.

Acceptance: user can troubleshoot from HA UI without ssh.

### F) Quality gates and CI

- ruff (lint) + black (format) + mypy (optional)
- GitHub Actions: run tests and lint on PR/push.

## Unit tests: mandatory and what to test against

This must ship with unit tests that lock down core behavior.

### 1) Delta parsing tests (pure function)

Add tests for:

- invalid JSON -> empty dict
- non-delta frames (no updates) -> empty dict
- single update/single value
- multiple updates/multiple values
- value types:
  - float/int/bool/str
  - object (position)
  - null
- missing fields:
  - no updates
  - values not list
  - missing path/value
- context handling:
  - expected_context mismatch -> ignored (or explicit policy, but test it)

File: tests/test_parser.py

### 2) Subscription payload construction tests (pure function)

Test:

- trims whitespace
- ignores blank lines
- ignores comment lines starting with "#"
- period is int
- payload structure correct and stable

File: tests/test_subscription.py

### 3) Config text parsing tests (pure function)

If you have text_to_paths helpers:

- ignore blanks
- strip whitespace
- ignore comments

File: tests/test_config_helpers.py

### 4) Config flow tests (HA harness)

Test:

- creates entry successfully
- unique_id prevents duplicate entries for same host/port/context
- options flow updates stored options

File: tests/test_config_flow.py

### 5) Entity behavior tests (light HA harness)

Without real WS:

- coordinator pushes data -> sensor native_value reflects it
- availability toggles based on coordinator state (once implemented)

File: tests/test_sensor_entity.py

### Optional advanced: WS reconnect behavior

If you implement a mock WS server, test:

- exception triggers reconnect state and backoff scheduling
- reconnect triggers re-subscribe

Do not block release on this if it causes flakiness, but aim to add it.

## Recommended test stack

- pytest
- pytest-asyncio
- pytest-homeassistant-custom-component (HA fixtures)
- coverage reporting in CI

Structure:

- tests/
- pyproject.toml with pytest config
- requirements-dev.txt (or uv/poetry config) listing test deps

## Repository layout (target)

signalk-ws-ha/

- hacs.json
- README.md
- pyproject.toml
- custom_components/
  - signalk_ws/
    - __init__.py
    - const.py
    - parser.py
    - subscription.py
    - coordinator.py
    - config_flow.py
    - sensor.py
    - diagnostics.py
    - manifest.json
    - strings.json
    - translations/en.json
- tests/
  - test_parser.py
  - test_subscription.py
  - test_config_flow.py
  - test_sensor_entity.py

## Definition of done

- Install via HACS, add via UI, sensors update within 30 seconds.
- If Signal K restarts or WiFi drops, integration recovers without user action.
- HA UI shows health status and last-update timestamps.
- Diagnostics are sufficient to debug without shell access.
- Unit tests cover parsing, subscription building, and config flow.
- Logs are actionable and rate-limited.
