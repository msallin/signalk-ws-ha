# Signal K WebSocket (signalk_ws)

Signal K WebSocket integration for Home Assistant. It connects to a Signal K server, subscribes to delta updates, and exposes paths as sensors with automatic reconnects and diagnostics.

## Quickstart

1. Install via HACS (custom repository if needed).
2. Add the integration from Home Assistant UI.
3. Pick a preset to prefill common paths.
4. Enter host, port, TLS, context, and period.
5. Save and verify sensors update within 30 seconds.

## Configuration notes

- WebSocket endpoint is fixed: `/signalk/v1/stream?subscribe=none`.
- After connect, the integration sends a subscription payload with `format=delta` and `policy=ideal`.
- Each subscription can override `period`, `format`, `policy`, and `minPeriod`.
- Wildcard paths (for example `navigation.*`) create sensors dynamically as matching data arrives.
- If you use a self-signed certificate, disable "Verify TLS certificate".

## Health sensors

The integration exposes health sensors for:

- Connection state
- Last message timestamp
- Reconnect count
- Last error

## Troubleshooting

- Verify the host/port and TLS match your Signal K server.
- Check Home Assistant logs for rate-limited parse errors or reconnect warnings.
- Use the Diagnostics panel for connection state, counters, and last-update timestamps per path.
- If you changed paths or period, reload the integration from the UI.
