"""Test Unraid integration setup."""
import pytest
from unittest.mock import patch, MagicMock

from custom_components.unraid import async_setup_entry
from custom_components.unraid.const import DOMAIN

@pytest.mark.asyncio
async def test_setup_entry(mock_hass, mock_unraid_api):
    """Test setup entry."""
    entry = MagicMock()
    entry.data = {
        "host": "192.168.1.100",
        "username": "root",
        "password": "password",
        "port": 22
    }
    entry.entry_id = "test_entry_id"
    
    # Mock the coordinator
    with patch("custom_components.unraid.UnraidDataUpdateCoordinator") as mock_coordinator:
        coordinator = mock_coordinator.return_value
        coordinator.async_config_entry_first_refresh = MagicMock(return_value=None)
        
        result = await async_setup_entry(mock_hass, entry)
        
        assert result is True
        assert mock_hass.data[DOMAIN][entry.entry_id] is coordinator
