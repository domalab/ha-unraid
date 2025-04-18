"""Unit tests for Unraid storage sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfInformation

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.storage_test import (
    UnraidDiskSensor,
    UnraidDiskTempSensor,
    UnraidTotalSpaceSensor,
    UnraidUsedSpaceSensor,
    UnraidCacheUsageSensor,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample data from unraid_collector."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    coordinator.hostname = "unraid"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"

    # Mock data that would be collected by unraid_collector.py
    coordinator.data = {
        "system_stats": {
            "individual_disks": [
                {
                    "name": "disk1",
                    "device": "/dev/sda",
                    "mount_point": "/mnt/disk1",
                    "size": "4.0T",
                    "size_bytes": 4000787030016,
                    "used": "2.2T",
                    "used_bytes": 2420345821286,
                    "available": "1.8T",
                    "available_bytes": 1580441208730,
                    "use_percent": "56%",
                    "filesystem": "xfs",
                    "smart_status": "PASS",
                    "temperature": 38,
                    "serial": "WDC-WD40EFRX-68WT0N0-123456"
                },
                {
                    "name": "disk2",
                    "device": "/dev/sdb",
                    "mount_point": "/mnt/disk2",
                    "size": "4.0T",
                    "size_bytes": 4000787030016,
                    "used": "3.1T",
                    "used_bytes": 3410345821286,
                    "available": "0.9T",
                    "available_bytes": 590441208730,
                    "use_percent": "78%",
                    "filesystem": "xfs",
                    "smart_status": "PASS",
                    "temperature": 41,
                    "serial": "WDC-WD40EFRX-68WT0N0-567890"
                },
                {
                    "name": "cache",
                    "device": "/dev/sdc",
                    "mount_point": "/mnt/cache",
                    "size": "500G",
                    "size_bytes": 500000000000,
                    "used": "320G",
                    "used_bytes": 320000000000,
                    "available": "180G",
                    "available_bytes": 180000000000,
                    "use_percent": "64%",
                    "filesystem": "btrfs",
                    "smart_status": "PASS",
                    "temperature": 35,
                    "serial": "Samsung_SSD_850_EVO_500GB-123456"
                }
            ],
            "array_info": {
                "total_size": "8.0T",
                "total_size_bytes": 8000000000000,
                "used_space": "5.3T",
                "used_space_bytes": 5830000000000,
                "free_space": "2.7T",
                "free_space_bytes": 2170000000000,
                "usage_percent": 72.8
            }
        }
    }

    return coordinator


class TestUnraidDiskSensor:
    """Test the Unraid disk usage sensor."""

    def test_disk_sensor(self, mock_coordinator):
        """Test disk usage sensor with mock data."""
        # Create the sensor for disk1
        sensor = UnraidDiskSensor(mock_coordinator, "disk1")

        # Check sensor properties
        assert sensor.name == "disk1 Usage"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR

        # Check sensor value
        assert sensor.native_value == 56.0

        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["mount_point"] == "/mnt/disk1"
        assert attrs["size"] == "4.0T"
        assert attrs["used"] == "2.2T"
        assert attrs["filesystem"] == "xfs"

        # Test with a non-existent disk
        sensor_non_existent = UnraidDiskSensor(mock_coordinator, "non_existent_disk")
        assert sensor_non_existent.native_value is None

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None


class TestUnraidDiskTempSensor:
    """Test the Unraid disk temperature sensor."""

    def test_disk_temp_sensor(self, mock_coordinator):
        """Test disk temperature sensor with mock data."""
        # Create the sensor for disk1
        sensor = UnraidDiskTempSensor(mock_coordinator, "disk1")

        # Check sensor properties
        assert sensor.name == "disk1 Temperature"
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.state_class == SensorStateClass.MEASUREMENT

        # Check sensor value
        assert sensor.native_value == 38

        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["serial"] == "WDC-WD40EFRX-68WT0N0-123456"
        assert attrs["smart_status"] == "PASS"

        # Test with a non-existent disk
        sensor_non_existent = UnraidDiskTempSensor(mock_coordinator, "non_existent_disk")
        assert sensor_non_existent.native_value is None

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with disk that has no temperature data
        mock_coordinator.data = {
            "system_stats": {
                "individual_disks": [
                    {
                        "name": "disk1",
                        "device": "/dev/sda",
                        "smart_status": "PASS",
                        # No temperature field
                    }
                ]
            }
        }
        assert sensor.native_value is None


class TestUnraidTotalSpaceSensor:
    """Test the Unraid total space sensor."""

    def test_total_space_sensor(self, mock_coordinator):
        """Test total space sensor with mock data."""
        # Create the sensor
        sensor = UnraidTotalSpaceSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "Total Space"
        assert sensor.native_unit_of_measurement == UnitOfInformation.TERABYTES
        assert sensor.device_class == SensorDeviceClass.DATA_SIZE
        assert sensor.state_class == SensorStateClass.MEASUREMENT

        # Check sensor value
        assert sensor.native_value == 8.0

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with more partial data
        mock_coordinator.data = {"system_stats": {"array_info": {}}}
        assert sensor.native_value is None


class TestUnraidUsedSpaceSensor:
    """Test the Unraid used space sensor."""

    def test_used_space_sensor(self, mock_coordinator):
        """Test used space sensor with mock data."""
        # Create the sensor
        sensor = UnraidUsedSpaceSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "Used Space"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT

        # Check sensor value
        assert sensor.native_value == 72.8

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with more partial data
        mock_coordinator.data = {"system_stats": {"array_info": {}}}
        assert sensor.native_value is None


class TestUnraidCacheUsageSensor:
    """Test the Unraid cache usage sensor."""

    def test_cache_usage_sensor(self, mock_coordinator):
        """Test cache usage sensor with mock data."""
        # Create the sensor
        sensor = UnraidCacheUsageSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "Cache Usage"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT

        # Check sensor value
        assert sensor.native_value == 64.0

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with no cache disk
        mock_coordinator.data = {
            "system_stats": {
                "individual_disks": [
                    {
                        "name": "disk1",
                        "device": "/dev/sda",
                        "use_percent": "56%"
                    }
                ]
            }
        }
        assert sensor.native_value is None