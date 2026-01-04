# Signal K (signalk_ha)

Signal K integration for Home Assistant. It discovers available data via REST and subscribes to live updates over WebSocket deltas.

## Quickstart

1. Install via HACS (custom repository if needed).
2. Add the integration from the Home Assistant UI.
3. Enter host, port, TLS, and certificate verification settings.
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
