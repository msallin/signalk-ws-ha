# Signal K (signalk_ha)

## Overview

[Signal K](https://signalk.org) is an open marine data platform and standard for vessel data. This integration for Home Assistant discovers available data via REST and subscribes to live updates over WebSocket deltas, exposing them as high-quality sensors with health and diagnostics included.

## Installation

1. Install via HACS (custom repository if needed).
2. Restart Home Assistant if prompted.

## Configuration

1. Add the integration from the Home Assistant UI.
2. Enter host, port, TLS, and certificate verification settings.
3. If the Signal K server requires authentication, Home Assistant creates an access request. Approve it in the Signal K admin UI (Security -> Access Requests); Home Assistant continues automatically after approval.
4. The integration fetches `/signalk/v1/api/vessels/self` and creates entities (disabled by default).
5. Enable the entities you want in the entity registry and wait for updates.

## How it works

- REST discovery runs on startup and every 24 hours (configurable in Options).
- WebSocket endpoint is fixed: `/signalk/v1/stream?subscribe=none`.
- The integration subscribes only to enabled entity paths using `format=delta` and `policy=ideal`.
- `navigation.position` is exposed as a Geo Location entity.
- Entities are never deleted automatically; missing paths become unavailable with `last_seen`.

## Health sensors

Diagnostic sensors are created for:

- Connection state
- Last message timestamp
- Reconnect count
- Last error

## Troubleshooting

- Verify the REST URL is reachable in a browser or `curl`.
- If you use a self-signed certificate, disable "Verify TLS certificate".
- Use the Diagnostics panel for connection state, counters, and last update timestamps.
- Reload the integration after connection settings change.

## Removal

1. Disable the integration in Home Assistant.
2. Remove the config entry from the Integrations UI.
3. Revoke the Home Assistant access in the Signal K admin UI (Security -> Devices -> look for `signalk_ha`).
4. (Optional) Delete any entities you no longer want in the entity registry.
