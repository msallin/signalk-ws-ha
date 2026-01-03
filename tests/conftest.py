import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def event_loop_policy():
    pytest_socket.enable_socket()
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        policy = asyncio.WindowsSelectorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        return policy
    return asyncio.get_event_loop_policy()


@pytest.fixture(autouse=True)
def _mock_aiohttp_session():
    with (
        patch(
            "custom_components.signalk_ws.coordinator.async_get_clientsession",
            return_value=Mock(),
        ),
        patch(
            "custom_components.signalk_ws.coordinator.SignalKCoordinator.async_start",
            new=AsyncMock(),
        ),
    ):
        yield
