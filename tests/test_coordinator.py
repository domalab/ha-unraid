"""Unit tests for the Unraid coordinator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.client import UnraidClient


@pytest.fixture
def mock_unraid_client():
    """Create a mock Unraid client."""
    client = MagicMock(spec=UnraidClient)
    client.async_get_system_stats = AsyncMock(return_value={
        "cpu_model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz",
        "cpu_cores": 12,
        "cpu_usage": 15.2,
        "cpu_temp": 45.0,
        "memory_used": "6.6G",
        "memory_total": "32.0G",
        "memory_usage_percentage": 18.9,
    })
    client.async_get_disk_info = AsyncMock(return_value=[
        {
            "device": "/dev/sda",
            "size": "8.0T",
            "used": "4.5T",
            "available": "3.5T",
            "use_percentage": "56%",
            "mounted_on": "/mnt/disk1",
            "temp": 38.0,
        }
    ])
    client.async_get_docker_containers = AsyncMock(return_value=[
        {
            "id": "abc123",
            "name": "homeassistant",
            "image": "homeassistant/home-assistant:latest",
            "status": "running",
            "state": "running",
            "created": "2023-01-01 12:00:00",
        }
    ])
    client.async_get_vms = AsyncMock(return_value=[
        {
            "id": "1",
            "name": "Windows10",
            "state": "running",
            "status": "running",
            "memory": "8G",
            "vcpus": 4,
        }
    ])
    client.async_get_ups_info = AsyncMock(return_value={
        "ups1": {
            "status": "OL",
            "battery_charge": 100.0,
            "input_voltage": 230.0,
        }
    })
    client.async_get_parity_status = AsyncMock(return_value={
        "status": "idle",
        "progress": 0,
        "speed": 0,
        "position": 0,
        "size": 0,
        "estimated_finish": "",
    })
    client.async_get_plugins = AsyncMock(return_value=[
        {
            "name": "dynamix.system.stats",
            "version": "1.0",
            "status": "enabled",
        }
    ])
    client.async_get_shares = AsyncMock(return_value=[
        {
            "name": "appdata",
            "free_space": "100G",
            "total_space": "500G",
        }
    ])
    client.async_get_users = AsyncMock(return_value=[
        {
            "name": "admin",
            "description": "Administrator",
        }
    ])
    client.async_get_alerts = AsyncMock(return_value=[])
    client.async_get_array_status = AsyncMock(return_value={
        "status": "Started",
        "protection_status": "Normal",
    })
    return client


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


class TestUnraidDataUpdateCoordinator:
    """Test the Unraid data update coordinator."""

    async def test_coordinator_init(self, mock_hass, mock_unraid_client):
        """Test coordinator initialization."""
        coordinator = UnraidDataUpdateCoordinator(
            mock_hass,
            client=mock_unraid_client,
            name="unraid",
            update_interval=30
        )
        
        assert coordinator.name == "unraid"
        assert coordinator.client == mock_unraid_client
        assert coordinator.update_interval.total_seconds() == 30
        assert coordinator.data is None

    @patch("custom_components.unraid.coordinator.SCAN_INTERVAL", 60)
    async def test_coordinator_default_update_interval(self, mock_hass, mock_unraid_client):
        """Test coordinator with default update interval."""
        coordinator = UnraidDataUpdateCoordinator(
            mock_hass,
            client=mock_unraid_client,
            name="unraid"
        )
        
        assert coordinator.update_interval.total_seconds() == 60

    async def test_coordinator_update(self, mock_hass, mock_unraid_client):
        """Test coordinator update method."""
        coordinator = UnraidDataUpdateCoordinator(
            mock_hass,
            client=mock_unraid_client,
            name="unraid"
        )
        
        await coordinator.async_refresh()
        
        # Check that data is populated
        assert coordinator.data is not None
        assert "system_stats" in coordinator.data
        assert "disks" in coordinator.data
        assert "docker_containers" in coordinator.data
        assert "vms" in coordinator.data
        assert "ups_info" in coordinator.data
        assert "parity_status" in coordinator.data
        assert "plugins" in coordinator.data
        assert "shares" in coordinator.data
        assert "users" in coordinator.data
        assert "alerts" in coordinator.data
        assert "array_status" in coordinator.data
        
        # Check specific data values
        assert coordinator.data["system_stats"]["cpu_usage"] == 15.2
        assert coordinator.data["disks"][0]["device"] == "/dev/sda"
        assert coordinator.data["docker_containers"][0]["name"] == "homeassistant"
        assert coordinator.data["vms"][0]["name"] == "Windows10"

    async def test_coordinator_client_error(self, mock_hass, mock_unraid_client):
        """Test coordinator handling of client errors."""
        # Make the client raise an exception
        mock_unraid_client.async_get_system_stats.side_effect = Exception("Connection error")
        
        coordinator = UnraidDataUpdateCoordinator(
            mock_hass,
            client=mock_unraid_client,
            name="unraid"
        )
        
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
            
        # Check that the client was called
        mock_unraid_client.async_get_system_stats.assert_called_once()

    async def test_partial_data_collection(self, mock_hass, mock_unraid_client):
        """Test coordinator with partial data."""
        # Make some endpoints fail but allow others to succeed
        mock_unraid_client.async_get_docker_containers.side_effect = Exception("Docker API error")
        mock_unraid_client.async_get_vms.side_effect = Exception("VM API error")
        
        coordinator = UnraidDataUpdateCoordinator(
            mock_hass,
            client=mock_unraid_client,
            name="unraid"
        )
        
        await coordinator.async_refresh()
        
        # Check that available data is populated
        assert coordinator.data is not None
        assert "system_stats" in coordinator.data
        assert "disks" in coordinator.data
        
        # Check that failed data is empty but the keys exist
        assert coordinator.data["docker_containers"] == []
        assert coordinator.data["vms"] == []
