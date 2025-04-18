"""Tests for the UnraidAPI class."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.unraid.unraid import UnraidAPI
from custom_components.unraid.api.connection_manager import ConnectionManager


async def test_unraid_api_initialization():
    """Test that the UnraidAPI initializes correctly."""
    # Arrange
    host = "192.168.1.100"
    username = "root"
    password = "password"
    port = 22
    
    # Act
    api = UnraidAPI(host, username, password, port)
    
    # Assert
    assert api.host == host
    assert api.username == username
    assert api.password == password
    assert api.port == port


@pytest.mark.asyncio
async def test_unraid_api_connection(mock_connection_manager):
    """Test that the UnraidAPI can connect and disconnect."""
    # Arrange
    with patch("custom_components.unraid.unraid.ConnectionManager", return_value=mock_connection_manager):
        api = UnraidAPI("192.168.1.100", "root", "password", 22)
    
    # Act & Assert - Test connection
    await api.connect()
    mock_connection_manager.connect.assert_called_once()
    
    # Act & Assert - Test disconnection
    await api.disconnect()
    mock_connection_manager.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_unraid_api_is_connected(mock_connection_manager):
    """Test the is_connected method."""
    # Arrange
    with patch("custom_components.unraid.unraid.ConnectionManager", return_value=mock_connection_manager):
        api = UnraidAPI("192.168.1.100", "root", "password", 22)
    
    # Mock the is_connected method to return True
    mock_connection_manager.is_connected.return_value = True
    
    # Act & Assert
    is_connected = await api.is_connected()
    assert is_connected is True
    mock_connection_manager.is_connected.assert_called_once()
