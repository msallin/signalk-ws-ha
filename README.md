# Signal K (signalk_ha)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/msallin/signalk-ha)](https://github.com/msallin/signalk-ha/releases)

This integration links Home Assistant to Signal K, turning vessel data into native entities and automation‑ready notification events. It discovers available data via REST, then keeps entities updated through the Signal K WebSocket delta stream. Multiple instances are supported: each config entry represents one Signal K server and one vessel device in Home Assistant. [Signal K](https://signalk.org) is an open marine data platform and standard for vessel data.

## Installation

### HACS

To add the Signal K integration to your Home Assistant instance, use this My button:  
  
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=msallin&repository=signalk_ha&category=integration)

Ensure you have [HACS installed](https://www.hacs.xyz/docs/use/configuration/basic/) in your Home Assistant instance before clicking the button.

### Manual installation

If you prefer to install manually:

1. Download the latest release ZIP from `https://github.com/msallin/signalk-ha/releases`.
2. Extract the ZIP and copy `custom_components/signalk_ha` into your Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.
4. Go to Settings > Devices & Services > Add Integration > Signal K.

## Configuration

1. Open Settings > Devices & Services > Add Integration > Signal K.
2. Enter host, port, TLS, and certificate verification settings.
3. If the Signal K server requires authentication, Home Assistant creates an access request. Approve it in the Signal K admin UI (Security > Access Requests); Home Assistant continues automatically after approval.
4. The integration fetches vessel data and creates entities (all disabled by default).
5. Enable the entities you want in the entity registry and wait for updates.

### Setup parameters

| Parameter | Description | Default |
| --- | --- | --- |
| Host | Hostname or URL (http/https). If you include a scheme, TLS and port are inferred. | Required |
| Port | Signal K port. | 3000 |
| Use TLS (https/wss) | Enable if your Signal K uses HTTPS/WSS. | Off |
| Verify TLS certificate | Disable for self-signed certificates. | On |

### Options

| Option | Description | Default |
| --- | --- | --- |
| Data groups to include | Which Signal K groups are discovered (navigation, environment, tanks, etc.). | Navigation, Environment, Tanks |
| Discovery refresh interval (hours) | How often REST discovery refreshes entity metadata. | 24 |
| Enable Signal K notification events | Emit `signalk_<vesselname>_notification` events for `notifications.*` (vessel name slugified). | On |
| Notification paths for Event entities | One `notifications.*` path per line to expose as Event entities. Use `notifications.*` to expose all. | None |

## How it works

Signal K is broad and high‑rate, so the integration intentionally separates discovery from live updates. It discovers the full data model, creates entities (disabled by default), and then subscribes only to the enabled entity paths. This limits data churn in Home Assistant and keeps CPU usage low.

### Discovery

Discovery starts with the Signal K server discovery document (`GET /signalk`) to resolve the REST and WebSocket endpoints, then fetches `/signalk/v1/api/vessels/self` to build the entity catalog for the selected data groups.
REST discovery runs on startup and every 24 hours (configurable in Options); missing paths are marked unavailable with `last_seen`, and entities are never deleted automatically.
Discovery is idempotent: re‑runs can add new entities or refresh metadata without breaking existing entity IDs.

### Entity creation

Entities are created from discovered paths and start disabled by default so you can choose what you actually want to update in Home Assistant.
For each path, the integration first consults the Signal K schema metadata, then merges in vessel‑specific metadata from `/vessels/self`. The entity attribute `spec_known` indicates whether the path exists in the Signal K specification.
Units and icons are suggested when metadata is available, and names are made human‑readable; if duplicates exist, names are disambiguated using their path context (e.g., “Navigation Speed Over Ground” vs “Wind Speed Over Ground”).
`navigation.position` is exposed as a Geo Location entity.

### Subscriptions

WebSocket subscriptions use the discovered stream endpoint and resubscribe after reconnects.
Only enabled entity paths are subscribed using `format=delta` and `policy=ideal`, and `notifications.*` is added when notification events are enabled.
Per‑path periods are applied when available so high‑rate signals don’t overwhelm Home Assistant.

### Updates

Incoming deltas update an internal cache and are throttled before writing state to Home Assistant, reducing recorder and UI load.
The churn‑reduction pipeline has multiple layers that work together:

- Server-side throttling: subscriptions send `minPeriod` (max rate) and `period` (keepalive) so the Signal K server reduces bursts before HA sees them.
- Coordinator coalescing: updates are buffered for a short window so many deltas collapse into a single HA state update.
- Entity throttling: each entity enforces `min_update_ms` plus per‑path tolerances so tiny changes do not trigger writes.
- Staleness: if updates stop, entities are marked unavailable after `stale_seconds`.

### Notifications

Signal K notifications (`notifications.*`) are forwarded as Home Assistant events when enabled in Options. The event type is `signalk_<vesselname>_notification` where `<vesselname>` is the vessel name from config (slugified).

- Event: `signalk_<vesselname>_notification` (example: `signalk_ona_notification`)
- Payload includes: `path`, `value`, `state`, `message`, `method`, `timestamp`, `source`, `vessel_id`, `vessel_name`, `entry_id`

Notifications are also exposed as Event entities (domain `event`) so you can build automations in the UI. Each unique notification path creates an Event entity (for example, `notifications.navigation.anchor` becomes an event entity named "Navigation Anchor Notification"). The `event_type` matches the Signal K alarm state (`nominal`, `normal`, `alert`, `warn`, `alarm`, `emergency`) and the attributes include the full Signal K payload fields listed above.

Example automation (anchor alarm):

Signal K publishes anchor alarms under `notifications.navigation.anchor` with states like `warn`, `alarm`, or `emergency`. The following automation creates a persistent notification in Home Assistant when such an alarm is received.

```yaml
alias: Signal K Anchor Alarm
description: ""
mode: single
triggers:
  - event_type: signalk_ona_notification
    event_data:
      path: notifications.navigation.anchor
    trigger: event
conditions:
  - condition: template
    value_template: |
      {{ trigger.event.data.state in ['warn', 'alarm', 'emergency'] }}
actions:
  - action: persistent_notification.create
    metadata: {}
    data:
      message: "{{ trigger.event.data.message }}"
```

### Diagnostic sensors

Diagnostic sensors summarize connection health and message flow (disabled by default).

| Sensor | Description | Default |
| --- | --- | --- |
| Connection State | WebSocket connection state (`connected`, `connecting`, `reconnecting`, `disconnected`). | On |
| Last Error | Last recorded connection or parsing error (if any). | On |
| Reconnect Count | Number of reconnects since startup. | On |
| Last Message | Timestamp of the last received WebSocket message. | On |
| Notification Count | Number of notifications received since startup. | On |
| Last Notification | Timestamp and attributes for the last notification event. | On |
| Message Count | Total messages received since startup. | Off |
| Messages per Hour | Average messages per hour since the first message. | Off |
| Notifications per Hour | Average notifications per hour since the first notification. | Off |

## Troubleshooting

- Verify the REST URL is reachable in a browser or `curl`.
- If you use a self-signed certificate, disable "Verify TLS certificate".
- If authentication is required, approve the access request in Signal K and wait for Home Assistant to continue automatically.
- If approval times out, reopen the config flow to retry the access request.
- Use the Diagnostics panel for connection state, counters, and last update timestamps.
- Reload the integration after connection settings change.

## Removal

1. Disable the integration in Home Assistant.
2. Remove the config entry from the Integrations UI.
3. Revoke the Home Assistant access in the Signal K admin UI (Security > Devices > look for `signalk_ha`).
4. (Optional) Delete any entities you no longer want in the entity registry.
