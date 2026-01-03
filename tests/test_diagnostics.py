from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ws.const import DOMAIN
from custom_components.signalk_ws.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_host(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    cfg = SimpleNamespace(
        host="sk.local",
        port=3000,
        ssl=False,
        verify_ssl=True,
        context="vessels.self",
        period_ms=1000,
        paths=["navigation.speedOverGround"],
    )
    coordinator = SimpleNamespace(
        config=cfg,
        connection_state="connected",
        last_error=None,
        counters={"messages": 0, "parse_errors": 0, "reconnects": 0},
        reconnect_count=0,
        last_message=None,
        last_update_by_path={},
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config"]["host"] == "<redacted>"
