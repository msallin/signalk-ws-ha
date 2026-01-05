# Signal K (signalk_ha)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/msallin/signalk-ha)](https://github.com/msallin/signalk-ha/releases)

This Home Assistant integration discovers and subscribes to a Signal K server, exposing its data as Home Assistant entities and notifications as events. [Signal K](https://signalk.org) is an open marine data platform and standard for vessel data. It first discovers available data via REST and subscribes to updates using WebSocket. Furthermore, it exposes all vessel notifications as Home Assistant events to be used in automations.

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
4. The integration fetches `/signalk/v1/api/vessels/self` and creates entities (all disabled by default).
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
| Discovery refresh interval (hours) | How often REST discovery refreshes entity metadata. | 24 |
| Enable Signal K notification events | Emit `signalk_ha_notification` events for `notifications.*`. | On |

## How it works

- REST discovery runs on startup and every 24 hours (configurable in Options).
- WebSocket endpoint is fixed: `/signalk/v1/stream?subscribe=none`.
- The integration subscribes only to enabled entity paths using `format=delta` and `policy=ideal`.
- `navigation.position` is exposed as a Geo Location entity.
- Entities are never deleted automatically; missing paths become unavailable with `last_seen`.

### Notifications

Signal K notifications (`notifications.*`) are forwarded as Home Assistant events when enabled in Options.

- Event: `signalk_ha_notification`
- Payload includes: `path`, `value`, `state`, `message`, `method`, `timestamp`, `source`, `vessel_id`, `vessel_name`, `entry_id`

Example automation (anchor alarm):

Signal K publishes anchor alarms under `notifications.navigation.anchor` with states like `warn`, `alarm`, or `emergency`. The following automation creates a persistent notification in Home Assistant when such an alarm is received.

```yaml
alias: Signal K Anchor Alarm
description: ""
mode: single
triggers:
  - event_type: signalk_ha_notification
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
