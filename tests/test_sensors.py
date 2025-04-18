"""Unit tests for the Unraid sensor components."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import (
    PERCENTAGE,
    STATE_UNAVAILABLE,
)
from homeassistant.components.sensor import UnitOfTemperature
from homeassistant.core import HomeAssistant

from custom_components.unraid.const import DOMAIN
from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.system_test import (
    UnraidCPUUsageSensor,
    UnraidRAMUsageSensor,
    UnraidCPUTempSensor,
)
from custom_components.unraid.sensors.storage_test import (
    UnraidDiskSensor,
)
from custom_components.unraid.sensors.ups import (
    UnraidUPSSensor,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    coordinator.data = {
        "system_stats": {
            "cpu_model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz",
            "cpu_cores": 12,
            "cpu_usage": 15.2,
            "cpu_temp": 45.0,
            "memory_used": "6.6G",
            "memory_total": "32.0G",
            "memory_usage_percentage": 18.9,
            "uptime": "5 days, 3:42:15",
            "kernel_version": "5.10.28-Unraid",
            "unraid_version": "6.10.3",
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
            },
            {
                "device": "/dev/sdb",
                "size": "4.0T",
                "used": "2.0T",
                "available": "2.0T",
                "use_percentage": "50%",
                "mounted_on": "/mnt/disk2",
                "temp": 35.0,
            }
        ],
        "ups_info": {
            "ups1": {
                "status": "OL",
                "battery_charge": 100.0,
                "input_voltage": 230.0,
                "load_percentage": 42.0,
                "runtime_left": "2h 30m",
            }
        }
    }
    coordinator.async_request_refresh = AsyncMock()
    coordinator.available = True
    return coordinator


class TestUnraidSystemSensors:
    """Test Unraid system sensors."""

    @pytest.mark.asyncio
    async def test_cpu_usage_sensor(self, mock_coordinator):
        """Test CPU usage sensor."""
        sensor = UnraidCPUUsageSensor(mock_coordinator, "cpu_usage")

        assert sensor.unique_id == "unraid_cpu_usage"
        assert sensor.name == "Unraid CPU Usage"
        assert sensor.native_value == 15.2
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.available is True

        # Test unavailable
        mock_coordinator.available = False
        assert sensor.available is False

        # Test missing data
        mock_coordinator.available = True
        del mock_coordinator.data["system_stats"]["cpu_usage"]
        assert sensor.native_value is None

    @pytest.mark.asyncio
    async def test_ram_usage_sensor(self, mock_coordinator):
        """Test RAM usage sensor."""
        sensor = UnraidRAMUsageSensor(mock_coordinator, "memory_usage")

        assert sensor.unique_id == "unraid_memory_usage"
        assert sensor.name == "Unraid Memory Usage"
        assert sensor.native_value == 18.9
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.available is True

        # Test unavailable
        mock_coordinator.available = False
        assert sensor.available is False

        # Test missing data
        mock_coordinator.available = True
        mock_coordinator.data["system_stats"]["memory_usage_percentage"] = None
        assert sensor.native_value is None

    @pytest.mark.asyncio
    async def test_cpu_temp_sensor(self, mock_coordinator):
        """Test CPU temperature sensor."""
        sensor = UnraidCPUTempSensor(mock_coordinator, "cpu_temp")

        assert sensor.unique_id == "unraid_cpu_temp"
        assert sensor.name == "Unraid CPU Temperature"
        assert sensor.native_value == 45.0
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.available is True

        # Test unavailable
        mock_coordinator.available = False
        assert sensor.available is False

        # Test missing data
        mock_coordinator.available = True
        del mock_coordinator.data["system_stats"]["cpu_temp"]
        assert sensor.native_value is None


class TestUnraidDiskSensors:
    """Test Unraid disk sensors."""

    @pytest.mark.asyncio
    async def test_disk_usage_sensor(self, mock_coordinator):
        """Test disk usage sensor."""
        # First disk
        sensor = UnraidDiskSensor(mock_coordinator, "disk1", "/dev/sda")

        assert sensor.unique_id == "unraid_disk1_usage"
        assert sensor.name == "Unraid Disk1 Usage"
        assert sensor.device_info is not None
        assert sensor.native_value == 56
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.available is True

        # Attributes
        assert sensor.extra_state_attributes["device"] == "/dev/sda"
        assert sensor.extra_state_attributes["size"] == "8.0T"
        assert sensor.extra_state_attributes["used"] == "4.5T"
        assert sensor.extra_state_attributes["available"] == "3.5T"
        assert sensor.extra_state_attributes["temp"] == 38.0

        # Second disk
        sensor2 = UnraidDiskSensor(mock_coordinator, "disk2", "/dev/sdb")
        assert sensor2.native_value == 50
        assert sensor2.extra_state_attributes["temp"] == 35.0

        # Test unavailable
        mock_coordinator.available = False
        assert sensor.available is False

        # Test missing disk
        mock_coordinator.available = True
        sensor3 = UnraidDiskSensor(mock_coordinator, "disk3", "/dev/sdc")
        assert sensor3.native_value is None
        assert sensor3.available is True


class TestUnraidUPSSensors:
    """Test Unraid UPS sensors."""

    @pytest.mark.asyncio
    async def test_ups_sensor(self, mock_coordinator):
        """Test UPS sensor."""
        sensor = UnraidUPSSensor(mock_coordinator, "ups1_battery", "battery_charge")

        assert sensor.unique_id == "unraid_ups1_battery"
        assert sensor.name == "Unraid UPS1 Battery"
        assert sensor.native_value == 100.0
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.available is True

        # Test other UPS metrics
        voltage_sensor = UnraidUPSSensor(mock_coordinator, "ups1_voltage", "input_voltage")
        assert voltage_sensor.native_value == 230.0

        load_sensor = UnraidUPSSensor(mock_coordinator, "ups1_load", "load_percentage")
        assert load_sensor.native_value == 42.0

        # Test unavailable
        mock_coordinator.available = False
        assert sensor.available is False

        # Test missing UPS
        mock_coordinator.available = True
        sensor2 = UnraidUPSSensor(mock_coordinator, "ups2_battery", "battery_charge")
        assert sensor2.native_value is None

        # Test missing metric
        sensor3 = UnraidUPSSensor(mock_coordinator, "ups1_unknown", "unknown_metric")
        assert sensor3.native_value is None