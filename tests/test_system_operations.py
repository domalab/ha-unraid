"""Tests for the SystemOperationsMixin class."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.unraid.api.system_operations import SystemOperationsMixin
from custom_components.unraid.api.network_operations import NetworkOperationsMixin


@pytest.fixture
def mock_system_operations():
    """Return a mocked SystemOperationsMixin instance."""
    system_ops = SystemOperationsMixin()
    network_ops = MagicMock(spec=NetworkOperationsMixin)
    network_ops.run_command = AsyncMock()
    system_ops.set_network_ops(network_ops)
    return system_ops


@pytest.mark.asyncio
async def test_get_system_stats(mock_system_operations):
    """Test the get_system_stats method."""
    # Arrange
    mock_network_ops = mock_system_operations._network_ops
    
    # Setup mock responses for the commands
    cpu_info_response = """processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 158
model name	: Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz
stepping	: 10
cpu MHz		: 3700.000
cache size	: 12288 KB"""
    
    uptime_response = "123456.78 98765.43"
    memory_info = "MemTotal: 32941104 kB\nMemFree: 29941104 kB\nMemAvailable: 30941104 kB"
    cpu_temps = "Core 0: +35.0°C"
    loadavg = "0.52 0.58 0.59 2/1234 5678"
    
    mock_network_ops.run_command.side_effect = [
        cpu_info_response,  # cat /proc/cpuinfo
        uptime_response,    # cat /proc/uptime
        memory_info,        # cat /proc/meminfo
        cpu_temps,          # sensors
        loadavg,            # cat /proc/loadavg
    ]
    
    # Act
    result = await mock_system_operations.get_system_stats()
    
    # Assert
    assert mock_network_ops.run_command.call_count == 5
    assert "cpu_model" in result
    assert result["cpu_model"] == "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz"
    assert "uptime" in result
    assert "memory_used" in result
    assert "memory_total" in result
    assert "memory_free" in result
    assert "load_averages" in result


@pytest.mark.asyncio
async def test_get_array_status(mock_system_operations):
    """Test the get_array_status method."""
    # Arrange
    mock_network_ops = mock_system_operations._network_ops
    
    # Setup mock response for array status
    array_status = "Array Started"
    mock_network_ops.run_command.return_value = array_status
    
    # Act
    result = await mock_system_operations.get_array_status()
    
    # Assert
    mock_network_ops.run_command.assert_called_once()
    assert result.state == "started"
    assert result.synced is True
