"""Unit tests for the Unraid client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from custom_components.unraid.client import UnraidClient
from custom_components.unraid.exceptions import UnraidConnectionError


@pytest.fixture
def mock_data_file():
    """Provide mock data for testing."""
    return {
        "system_stats": {
            "cpu_model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz",
            "cpu_cores": 12,
            "cpu_usage": 15.2,
            "cpu_temp": 45.0,
            "memory_used": "6.6G",
            "memory_total": "32.0G",
            "memory_usage_percentage": 18.9,
        },
        "disks": [
            {
                "device": "/dev/sda",
                "size": "8.0T",
                "used": "4.5T",
                "available": "3.5T",
                "use_percentage": "56%",
                "mounted_on": "/mnt/disk1",
                "temp": 38.0,
            }
        ],
        "docker_containers": [
            {
                "id": "abc123",
                "name": "homeassistant",
                "status": "running",
                "state": "running",
            }
        ],
        "vms": [
            {
                "id": "1",
                "name": "Windows10",
                "state": "running",
                "status": "running",
            }
        ],
        "ups_info": {
            "ups1": {
                "status": "OL",
                "battery_charge": 100.0,
                "input_voltage": 230.0,
            }
        },
        "parity_status": {
            "status": "idle",
            "progress": 0,
        },
        "plugins": [
            {
                "name": "dynamix.system.stats",
                "version": "1.0",
                "status": "enabled",
            }
        ],
        "shares": [
            {
                "name": "appdata",
                "free_space": "100G",
                "total_space": "500G",
            }
        ],
        "users": [
            {
                "name": "admin",
                "description": "Administrator",
            }
        ],
        "alerts": [],
        "array_status": {
            "status": "Started",
            "protection_status": "Normal",
        },
    }


@pytest.fixture
def mock_unraid_data_handler():
    """Create a mock data handler."""
    handler = MagicMock()
    handler.async_load_data = AsyncMock()
    return handler


class TestUnraidClient:
    """Test the Unraid client."""

    @pytest.fixture(autouse=True)
    def setup_client(self, mock_unraid_data_handler, mock_data_file):
        """Set up the Unraid client for testing."""
        self.client = UnraidClient(
            host="192.168.1.100",
            port=22,
            username="root",
            password="password",
            data_path="/tmp",
            use_ssh=True
        )

        # Patch the data handler
        with patch("custom_components.unraid.client.UnraidDataHandler",
                  return_value=mock_unraid_data_handler):
            self.client._init_data_handler()

        # Mock data handler returns our mock data
        mock_unraid_data_handler.async_load_data.return_value = mock_data_file

        # Store for tests to use
        self.mock_data_handler = mock_unraid_data_handler
        self.mock_data = mock_data_file

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.host == "192.168.1.100"
        assert self.client.port == 22
        assert self.client.username == "root"
        assert self.client.password == "password"
        assert self.client.data_path == "/tmp"
        assert self.client.use_ssh is True
        assert self.client._data_handler is not None

    @pytest.mark.asyncio
    async def test_async_get_system_stats(self):
        """Test getting system stats."""
        result = await self.client.async_get_system_stats()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["system_stats"]
        assert result["cpu_model"] == "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz"
        assert result["cpu_usage"] == 15.2

    @pytest.mark.asyncio
    async def test_async_get_disk_info(self):
        """Test getting disk info."""
        result = await self.client.async_get_disk_info()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["disks"]
        assert result[0]["device"] == "/dev/sda"
        assert result[0]["size"] == "8.0T"

    @pytest.mark.asyncio
    async def test_async_get_docker_containers(self):
        """Test getting docker containers."""
        result = await self.client.async_get_docker_containers()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["docker_containers"]
        assert result[0]["name"] == "homeassistant"
        assert result[0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_async_get_vms(self):
        """Test getting VMs."""
        result = await self.client.async_get_vms()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["vms"]
        assert result[0]["name"] == "Windows10"
        assert result[0]["state"] == "running"

    @pytest.mark.asyncio
    async def test_async_get_ups_info(self):
        """Test getting UPS info."""
        result = await self.client.async_get_ups_info()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["ups_info"]
        assert result["ups1"]["status"] == "OL"
        assert result["ups1"]["battery_charge"] == 100.0

    @pytest.mark.asyncio
    async def test_async_get_parity_status(self):
        """Test getting parity status."""
        result = await self.client.async_get_parity_status()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["parity_status"]
        assert result["status"] == "idle"
        assert result["progress"] == 0

    @pytest.mark.asyncio
    async def test_async_get_plugins(self):
        """Test getting plugins."""
        result = await self.client.async_get_plugins()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["plugins"]
        assert result[0]["name"] == "dynamix.system.stats"
        assert result[0]["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_async_get_shares(self):
        """Test getting shares."""
        result = await self.client.async_get_shares()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["shares"]
        assert result[0]["name"] == "appdata"
        assert result[0]["free_space"] == "100G"

    @pytest.mark.asyncio
    async def test_async_get_users(self):
        """Test getting users."""
        result = await self.client.async_get_users()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["users"]
        assert result[0]["name"] == "admin"
        assert result[0]["description"] == "Administrator"

    @pytest.mark.asyncio
    async def test_async_get_alerts(self):
        """Test getting alerts."""
        result = await self.client.async_get_alerts()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["alerts"]
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_async_get_array_status(self):
        """Test getting array status."""
        result = await self.client.async_get_array_status()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

        # Verify result
        assert result == self.mock_data["array_status"]
        assert result["status"] == "Started"
        assert result["protection_status"] == "Normal"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test handling of connection errors."""
        # Make the data handler raise an exception
        self.mock_data_handler.async_load_data.side_effect = Exception("Connection error")

        # Test that the client properly wraps the exception
        with pytest.raises(UnraidConnectionError):
            await self.client.async_get_system_stats()

        # Verify data handler was called
        self.mock_data_handler.async_load_data.assert_called_once()

    @patch("custom_components.unraid.client.UnraidDataHandler")
    @pytest.mark.asyncio
    async def test_ssh_connection(self, mock_data_handler_class):
        """Test SSH connection parameters."""
        # Create a client with SSH
        client = UnraidClient(
            host="192.168.1.100",
            port=22,
            username="root",
            password="password",
            data_path="/tmp",
            use_ssh=True
        )

        # Initialize the data handler
        client._init_data_handler()

        # Verify the data handler was created with SSH params
        mock_data_handler_class.assert_called_once_with(
            host="192.168.1.100",
            port=22,
            username="root",
            password="password",
            data_path="/tmp",
            use_ssh=True
        )

    @patch("custom_components.unraid.client.UnraidDataHandler")
    @pytest.mark.asyncio
    async def test_local_connection(self, mock_data_handler_class):
        """Test local connection parameters."""
        # Create a client without SSH
        client = UnraidClient(
            host="192.168.1.100",
            port=22,
            username="root",
            password="password",
            data_path="/tmp",
            use_ssh=False
        )

        # Initialize the data handler
        client._init_data_handler()

        # Verify the data handler was created with local params
        mock_data_handler_class.assert_called_once_with(
            host="192.168.1.100",
            port=22,
            username="root",
            password="password",
            data_path="/tmp",
            use_ssh=False
        )