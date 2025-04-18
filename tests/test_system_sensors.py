"""Unit tests for Unraid system sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.system_test import (
    UnraidCPUUsageSensor,
    UnraidRAMUsageSensor,
)
from custom_components.unraid.sensors.system_test_extra import (
    UnraidCPUTemperatureSensor,
    UnraidVersionSensor,
    UnraidUptimeSensor,
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
            "cpu_usage": 15.2,
            "cpu_info_raw": "Architecture:                    x86_64\nCPU op-mode(s):                  32-bit, 64-bit\nByte Order:                      Little Endian\nAddress sizes:                   39 bits physical, 48 bits virtual\nCPU(s):                          12\nOn-line CPU(s) list:             0-11\nThread(s) per core:              2\nCore(s) per socket:              6\nSocket(s):                       1\nNUMA node(s):                    1\nVendor ID:                       GenuineIntel\nCPU family:                      6\nModel:                           158\nModel name:                      Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz\nStepping:                        10\nCPU MHz:                         4655.733\nCPU max MHz:                     4700.0000\nCPU min MHz:                     800.0000\nBogoMIPS:                        7392.00\nVirtualization:                  VT-x\nL1d cache:                       192 KiB\nL1i cache:                       192 KiB\nL2 cache:                        1.5 MiB\nL3 cache:                        12 MiB\nNUMA node0 CPU(s):               0-11",
            "cpu_model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz",
            "cpu_cores": 12,
            "memory_usage": {
                "total": 32853524,
                "free": 26673728,
                "used": 6179796,
                "percentage": 18.9
            },
            "uptime": 1234567.89,  # seconds
            "kernel_version": "5.15.90-Unraid",
            "unraid_version": "6.12.0-rc2",
            "temperatures": {
                "coretemp-isa-0000": {
                    "Adapter": "ISA adapter",
                    "Package id 0": {
                        "temp1_input": 45.0
                    },
                    "Core 0": {
                        "temp2_input": 42.0
                    },
                    "Core 1": {
                        "temp3_input": 44.0
                    }
                }
            }
        }
    }

    return coordinator


class TestUnraidCPUUsageSensor:
    """Test the Unraid CPU usage sensor."""

    def test_cpu_usage_sensor(self, mock_coordinator):
        """Test CPU usage sensor with mock data."""
        # Create the sensor
        sensor = UnraidCPUUsageSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "CPU Usage"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR

        # Check sensor value
        assert sensor.native_value == 15.2

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None


class TestUnraidRAMUsageSensor:
    """Test the Unraid RAM usage sensor."""

    def test_ram_usage_sensor(self, mock_coordinator):
        """Test RAM usage sensor with mock data."""
        # Set test mode
        mock_coordinator._test_mode = True
        # Create the sensor
        sensor = UnraidRAMUsageSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "RAM Usage"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR

        # Check sensor value
        assert sensor.native_value == 18.9

        # Test with no data
        mock_coordinator._test_mode = False
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with more partial data
        mock_coordinator.data = {"system_stats": {"memory_usage": {}}}
        assert sensor.native_value is None


class TestUnraidCPUTemperatureSensor:
    """Test the Unraid CPU temperature sensor."""

    def test_cpu_temperature_sensor(self, mock_coordinator):
        """Test CPU temperature sensor with mock data."""
        # Create the sensor
        sensor = UnraidCPUTemperatureSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "CPU Temperature"
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.state_class == SensorStateClass.MEASUREMENT

        # Check sensor value (should be the package temperature)
        assert sensor.native_value == 45.0

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with alternate temperature structure
        mock_coordinator.data = {
            "system_stats": {
                "temperatures": {
                    "k10temp-pci-00c3": {
                        "Tctl": {
                            "temp1_input": 38.5
                        }
                    }
                }
            }
        }
        assert sensor.native_value == 38.5


class TestUnraidVersionSensor:
    """Test the Unraid version sensor."""

    def test_version_sensor(self, mock_coordinator):
        """Test version sensor with mock data."""
        # Create the sensor
        sensor = UnraidVersionSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "Version"
        assert sensor.icon == "mdi:information-outline"

        # Check sensor value
        assert sensor.native_value == "6.12.0-rc2"

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None


class TestUnraidUptimeSensor:
    """Test the Unraid uptime sensor."""

    def test_uptime_sensor(self, mock_coordinator):
        """Test uptime sensor with mock data."""
        # Create the sensor
        sensor = UnraidUptimeSensor(mock_coordinator)

        # Check sensor properties
        assert sensor.name == "Uptime"
        assert sensor.icon == "mdi:clock-outline"

        # Check sensor value - should format the seconds into a human-readable string
        assert "days" in sensor.native_value
        assert "hours" in sensor.native_value

        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None

        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None

        # Test with different uptime values
        mock_coordinator.data = {"system_stats": {"uptime": 86400}}  # 1 day
        assert "1 day" in sensor.native_value

        mock_coordinator.data = {"system_stats": {"uptime": 3600}}  # 1 hour
        assert "1 hour" in sensor.native_value

        mock_coordinator.data = {"system_stats": {"uptime": 60}}  # 1 minute
        assert "1 minute" in sensor.native_value