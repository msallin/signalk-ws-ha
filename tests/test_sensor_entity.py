from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.signalk_ws.const import (
    CONF_CONTEXT,
    CONF_HOST,
    CONF_PATHS,
    CONF_PERIOD_MS,
    CONF_PORT,
    CONF_SSL,
    DOMAIN,
)
from custom_components.signalk_ws.coordinator import ConnectionState


async def test_coordinator_updates_sensor_state(hass, enable_custom_integrations) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "sk.local",
            CONF_PORT: 3000,
            CONF_SSL: False,
            CONF_CONTEXT: "vessels.self",
            CONF_PERIOD_MS: 1000,
            CONF_PATHS: ["navigation.speedOverGround"],
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.signalk_ws.coordinator.SignalKCoordinator.async_start",
        new=AsyncMock(),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator._set_state(ConnectionState.CONNECTED)
    coordinator.async_set_updated_data({"navigation.speedOverGround": 5.5})
    await hass.async_block_till_done()

    unique_id = f"{DOMAIN}:sk.local:3000:vessels.self:navigation.speedOverGround"
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "5.5"
