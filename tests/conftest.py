"""Common fixtures for Unraid integration tests."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.unraid.unraid import UnraidAPI
from custom_components.unraid.api.connection_manager import ConnectionManager
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_connection_manager():
    """Return a mocked connection manager."""
    with patch("custom_components.unraid.api.connection_manager.ConnectionManager") as mock:
        connection = MagicMock(spec=ConnectionManager)
        connection.run_command = AsyncMock()
        connection.run_shell_command = AsyncMock()
        connection.is_connected = AsyncMock(return_value=True)
        connection.connect = AsyncMock()
        connection.disconnect = AsyncMock()
        
        mock.return_value = connection
        yield connection


@pytest.fixture
def mock_unraid_api(mock_connection_manager):
    """Return a mocked UnraidAPI object."""
    with patch("custom_components.unraid.unraid.UnraidAPI") as mock:
        api = MagicMock(spec=UnraidAPI)
        api.host = "192.168.1.100"
        api.username = "root"
        api.password = "password"
        api.port = 22
        
        # Set up the various operation mixin methods
        api.get_system_stats = AsyncMock()
        api.get_disks_status = AsyncMock()
        api.get_docker_containers = AsyncMock()
        api.get_vms = AsyncMock()
        api.get_ups_status = AsyncMock()
        api.get_network_status = AsyncMock()
        api.get_user_scripts = AsyncMock()
        
        yield api


@pytest.fixture
def hass():
    """Return a Home Assistant test instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def event_loop():
    """Return an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
