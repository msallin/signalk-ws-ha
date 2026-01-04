from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ha.const import DOMAIN
from custom_components.signalk_ha.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_urls(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    cfg = SimpleNamespace(
        base_url="http://sk.local:3000/signalk/v1/api/",
        ws_url="ws://sk.local:3000/signalk/v1/stream?subscribe=none",
        vessel_id="mmsi:261006533",
        vessel_name="ONA",
    )
    coordinator = SimpleNamespace(
        config=cfg,
        connection_state="connected",
        last_error=None,
        counters={"messages": 0, "parse_errors": 0, "reconnects": 0},
        reconnect_count=0,
        last_message=None,
        last_update_by_path={},
        last_backoff=0.0,
        subscribed_paths=[],
    )
    discovery = SimpleNamespace(conflicts=[], last_refresh=None)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "discovery": discovery,
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config"]["rest_url"] == "<redacted>"
    assert diagnostics["config"]["ws_url"] == "<redacted>"
