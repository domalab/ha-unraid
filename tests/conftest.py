"""Test fixtures for Unraid integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_unraid_api():
    """Mock the UnraidAPI class."""
    with patch("custom_components.unraid.unraid.UnraidAPI") as mock_api:
        api = mock_api.return_value
        api.get_system_info = AsyncMock()
        api.get_disk_info = AsyncMock()
        api.get_docker_info = AsyncMock()
        api.get_vm_info = AsyncMock()
        api.get_network_info = AsyncMock()
        api.get_ups_info = AsyncMock()
        api.get_user_scripts = AsyncMock()
        yield api

@pytest.fixture
def mock_hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.data = {}
    return hass
