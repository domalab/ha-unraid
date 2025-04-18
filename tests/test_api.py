"""Unit tests for the Unraid SSH client API."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unraid.api.ssh_client import UnraidSSHClient


@pytest.fixture
def mock_asyncssh():
    """Create a mock for asyncssh module."""
    with patch("custom_components.unraid.api.ssh_client.asyncssh") as mock:
        # Mock connection
        mock_connection = AsyncMock()
        mock.connect = AsyncMock(return_value=mock_connection)
        
        # Mock command result
        mock_result = MagicMock()
        mock_result.stdout = "Test output"
        mock_result.stderr = ""
        mock_result.exit_status = 0
        
        # Set up the connection to return our mock result
        mock_connection.run = AsyncMock(return_value=mock_result)
        
        yield mock, mock_connection, mock_result


class TestUnraidSSHClient:
    """Test the UnraidSSHClient class."""
    
    async def test_connection(self, mock_asyncssh):
        """Test connection to the Unraid server."""
        mock_module, mock_connection, _ = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Test connection
        assert not client.is_connected()
        
        result = await client.connect()
        assert result is True
        assert client.is_connected()
        
        # Verify asyncssh.connect was called with correct args
        mock_module.connect.assert_called_once_with(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22,
            known_hosts=None
        )
        
        # Test disconnection
        await client.disconnect()
        assert not client.is_connected()
        mock_connection.close.assert_called_once()
    
    async def test_connection_error(self, mock_asyncssh):
        """Test connection error handling."""
        mock_module, _, _ = mock_asyncssh
        
        # Simulate connection error
        mock_module.connect.side_effect = Exception("Connection error")
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Test connection failure
        result = await client.connect()
        assert result is False
        assert not client.is_connected()
    
    async def test_run_command(self, mock_asyncssh):
        """Test running a command on the Unraid server."""
        _, mock_connection, mock_result = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Simulate successful connection
        client._connection = mock_connection
        client._connected = True
        
        # Test running a command
        result = await client.run_command("test command")
        
        # Verify the command was run correctly
        mock_connection.run.assert_called_once_with("test command")
        assert result == mock_result
    
    async def test_run_command_not_connected(self, mock_asyncssh):
        """Test running a command when not connected."""
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Test running a command when not connected
        with pytest.raises(RuntimeError, match="Not connected to the Unraid server"):
            await client.run_command("test command")
    
    async def test_get_system_stats(self, mock_asyncssh):
        """Test getting system statistics."""
        _, mock_connection, mock_result = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Simulate successful connection
        client._connection = mock_connection
        client._connected = True
        
        # Configure mock responses for system stats commands
        async def mock_run_command(command):
            result = MagicMock()
            result.exit_status = 0
            
            if "cat /proc/stat" in command:
                result.stdout = "cpu  2255847 2488 499234 22808628 11756 0 14822 0 0 0"
            elif "cat /proc/meminfo" in command:
                result.stdout = """MemTotal:       32768000 kB
MemFree:        18911952 kB
MemAvailable:   26123680 kB"""
            elif "uptime" in command:
                result.stdout = "15:30:15 up 5 days, 3:42:15, 1 user, load average: 0.52, 0.58, 0.59"
            elif "uname -r" in command:
                result.stdout = "5.10.28-Unraid"
            elif "cat /etc/unraid-version" in command:
                result.stdout = "6.10.3"
            elif "sensors" in command:
                result.stdout = "Package id 0: +45.0°C (high = +80.0°C, crit = +100.0°C)"
            
            return result
        
        # Set the mock side effect
        mock_connection.run.side_effect = mock_run_command
        
        # Test getting system stats
        stats = await client.get_system_stats()
        
        # Verify the stats are correct
        assert "cpu_model" in stats
        assert "cpu_cores" in stats
        assert "cpu_usage" in stats
        assert "memory_used" in stats
        assert "memory_total" in stats
        assert "memory_usage_percentage" in stats
        assert "uptime" in stats
        assert "kernel_version" in stats
        assert "unraid_version" in stats
        assert stats["kernel_version"] == "5.10.28-Unraid"
        assert stats["unraid_version"] == "6.10.3"
        assert stats["uptime"] == "5 days, 3:42:15"
        assert stats["cpu_temp"] == 45.0
    
    async def test_get_disk_info(self, mock_asyncssh):
        """Test getting disk information."""
        _, mock_connection, _ = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Simulate successful connection
        client._connection = mock_connection
        client._connected = True
        
        # Configure mock responses for disk info commands
        async def mock_run_command(command):
            result = MagicMock()
            result.exit_status = 0
            
            if "df -h" in command:
                result.stdout = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda        8.0T  4.5T  3.5T  56% /mnt/disk1
/dev/sdb        4.0T  2.0T  2.0T  50% /mnt/disk2"""
            elif "smartctl" in command:
                if "sda" in command:
                    result.stdout = "194 Temperature_Celsius     0x0022   038   051   000    Old_age   Always       -       38 (0 18 0 0 0)"
                elif "sdb" in command:
                    result.stdout = "194 Temperature_Celsius     0x0022   035   051   000    Old_age   Always       -       35 (0 18 0 0 0)"
            
            return result
        
        # Set the mock side effect
        mock_connection.run.side_effect = mock_run_command
        
        # Test getting disk info
        disks = await client.get_disk_info()
        
        # Verify the disk info is correct
        assert len(disks) == 2
        assert disks[0]["device"] == "/dev/sda"
        assert disks[0]["size"] == "8.0T"
        assert disks[0]["used"] == "4.5T"
        assert disks[0]["available"] == "3.5T"
        assert disks[0]["use_percentage"] == "56%"
        assert disks[0]["mounted_on"] == "/mnt/disk1"
        assert disks[0]["temp"] == 38.0
        
        assert disks[1]["device"] == "/dev/sdb"
        assert disks[1]["size"] == "4.0T"
        assert disks[1]["used"] == "2.0T"
        assert disks[1]["available"] == "2.0T"
        assert disks[1]["use_percentage"] == "50%"
        assert disks[1]["mounted_on"] == "/mnt/disk2"
        assert disks[1]["temp"] == 35.0
    
    async def test_get_docker_containers(self, mock_asyncssh):
        """Test getting Docker container information."""
        _, mock_connection, _ = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Simulate successful connection
        client._connection = mock_connection
        client._connected = True
        
        # Configure mock responses for Docker commands
        async def mock_run_command(command):
            result = MagicMock()
            result.exit_status = 0
            
            if "docker ps" in command:
                result.stdout = """CONTAINER ID   IMAGE                        STATUS          NAMES
abc123def456   linuxserver/plex                running         plex
789ghi101112   homeassistant/home-assistant   running         homeassistant"""
            
            return result
        
        # Set the mock side effect
        mock_connection.run.side_effect = mock_run_command
        
        # Test getting Docker containers
        containers = await client.get_docker_containers()
        
        # Verify the container info is correct
        assert len(containers) == 2
        assert containers[0]["container_id"] == "abc123def456"
        assert containers[0]["name"] == "plex"
        assert containers[0]["image"] == "linuxserver/plex"
        assert containers[0]["status"] == "running"
        assert containers[0]["state"] == "running"
        
        assert containers[1]["container_id"] == "789ghi101112"
        assert containers[1]["name"] == "homeassistant"
        assert containers[1]["image"] == "homeassistant/home-assistant"
        assert containers[1]["status"] == "running"
        assert containers[1]["state"] == "running"
    
    async def test_get_vms(self, mock_asyncssh):
        """Test getting VM information."""
        _, mock_connection, _ = mock_asyncssh
        
        client = UnraidSSHClient(
            host="192.168.1.100",
            username="root",
            password="password",
            port=22
        )
        
        # Simulate successful connection
        client._connection = mock_connection
        client._connected = True
        
        # Configure mock responses for VM commands
        async def mock_run_command(command):
            result = MagicMock()
            result.exit_status = 0
            
            if "virsh list" in command:
                result.stdout = """Id   Name          State
--------------------------------
1    Windows10     running
-    Ubuntu20.04   shut off"""
            
            return result
        
        # Set the mock side effect
        mock_connection.run.side_effect = mock_run_command
        
        # Test getting VMs
        vms = await client.get_vms()
        
        # Verify the VM info is correct
        assert len(vms) == 2
        assert vms[0]["id"] == "1"
        assert vms[0]["name"] == "Windows10"
        assert vms[0]["state"] == "running"
        
        assert vms[1]["id"] == "-"
        assert vms[1]["name"] == "Ubuntu20.04"
        assert vms[1]["state"] == "shut off" 