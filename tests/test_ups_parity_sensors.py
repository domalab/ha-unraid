"""Unit tests for Unraid UPS and parity sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTime

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.ups import (
    UnraidUPSStatusSensor,
    UnraidUPSLoadSensor,
    UnraidUPSChargeSensor,
)
from custom_components.unraid.sensors.parity import (
    UnraidParityStatusSensor,
    UnraidParityProgressSensor,
    UnraidParitySpeedSensor,
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
            "ups_info": {
                "has_ups": True,
                "status": "OL",
                "battery_charge": 100,
                "load_percent": 23,
                "model": "APC Smart-UPS 1500",
                "runtime_estimate": "2 hours 30 minutes",
                "battery_voltage": 27.0,
                "input_voltage": 230.0
            }
        },
        "parity_status": {
            "status": "ACTIVE",
            "progress": 42,
            "speed": "120 MB/s",
            "elapsed": "01:45:30",
            "estimated_finish": "02:15:10",
            "last_check": "2023-04-10 12:00:00",
            "next_check": "2023-04-17 12:00:00",
            "error_count": 0
        }
    }
    
    return coordinator


class TestUnraidUPSStatusSensor:
    """Test the Unraid UPS status sensor."""
    
    def test_ups_status_sensor(self, mock_coordinator):
        """Test UPS status sensor with mock data."""
        # Create the sensor
        sensor = UnraidUPSStatusSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "UPS Status"
        assert sensor.icon == "mdi:power-plug"
        
        # Check sensor value
        assert sensor.native_value == "Online"
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["model"] == "APC Smart-UPS 1500"
        assert attrs["runtime_estimate"] == "2 hours 30 minutes"
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None
        
        # Test with UPS not detected
        mock_coordinator.data = {
            "system_stats": {
                "ups_info": {
                    "has_ups": False
                }
            }
        }
        assert sensor.native_value is None
        
        # Test with different UPS statuses
        status_tests = [
            ("OL", "Online"),
            ("OB", "On Battery"),
            ("LB", "Low Battery"),
            ("FSD", "Forced Shutdown"),
            ("CAL", "Calibrating"),
            ("UNKNOWN", "Unknown")
        ]
        
        for status_code, expected_status in status_tests:
            mock_coordinator.data = {
                "system_stats": {
                    "ups_info": {
                        "has_ups": True,
                        "status": status_code
                    }
                }
            }
            sensor = UnraidUPSStatusSensor(mock_coordinator)
            assert sensor.native_value == expected_status


class TestUnraidUPSLoadSensor:
    """Test the Unraid UPS load sensor."""
    
    def test_ups_load_sensor(self, mock_coordinator):
        """Test UPS load sensor with mock data."""
        # Create the sensor
        sensor = UnraidUPSLoadSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "UPS Load"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 23
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None
        
        # Test with UPS not detected
        mock_coordinator.data = {
            "system_stats": {
                "ups_info": {
                    "has_ups": False
                }
            }
        }
        assert sensor.native_value is None


class TestUnraidUPSChargeSensor:
    """Test the Unraid UPS charge sensor."""
    
    def test_ups_charge_sensor(self, mock_coordinator):
        """Test UPS charge sensor with mock data."""
        # Create the sensor
        sensor = UnraidUPSChargeSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "UPS Battery"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.BATTERY
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 100
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"system_stats": {}}
        assert sensor.native_value is None
        
        # Test with UPS not detected
        mock_coordinator.data = {
            "system_stats": {
                "ups_info": {
                    "has_ups": False
                }
            }
        }
        assert sensor.native_value is None


class TestUnraidParityStatusSensor:
    """Test the Unraid parity status sensor."""
    
    def test_parity_status_sensor(self, mock_coordinator):
        """Test parity status sensor with mock data."""
        # Create the sensor
        sensor = UnraidParityStatusSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Parity Status"
        assert sensor.icon == "mdi:harddisk"
        
        # Check sensor value
        assert sensor.native_value == "ACTIVE"
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["last_check"] == "2023-04-10 12:00:00"
        assert attrs["next_check"] == "2023-04-17 12:00:00"
        assert attrs["error_count"] == 0
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value == "UNKNOWN"
        
        # Test with partial data
        mock_coordinator.data = {"parity_status": {}}
        assert sensor.native_value == "UNKNOWN"
        
        # Test with different parity statuses
        status_tests = [
            ("ACTIVE", "ACTIVE"),
            ("IDLE", "IDLE"),
            ("PAUSED", "PAUSED"),
            ("ERROR", "ERROR")
        ]
        
        for status_code, expected_status in status_tests:
            mock_coordinator.data = {
                "parity_status": {
                    "status": status_code
                }
            }
            sensor = UnraidParityStatusSensor(mock_coordinator)
            assert sensor.native_value == expected_status


class TestUnraidParityProgressSensor:
    """Test the Unraid parity progress sensor."""
    
    def test_parity_progress_sensor(self, mock_coordinator):
        """Test parity progress sensor with mock data."""
        # Create the sensor
        sensor = UnraidParityProgressSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Parity Progress"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.icon == "mdi:progress-check"
        
        # Check sensor value
        assert sensor.native_value == 42
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["elapsed"] == "01:45:30"
        assert attrs["estimated_finish"] == "02:15:10"
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"parity_status": {}}
        assert sensor.native_value is None
        
        # Test with inactive parity check
        mock_coordinator.data = {
            "parity_status": {
                "status": "IDLE",
                "progress": None
            }
        }
        assert sensor.native_value is None


class TestUnraidParitySpeedSensor:
    """Test the Unraid parity speed sensor."""
    
    def test_parity_speed_sensor(self, mock_coordinator):
        """Test parity speed sensor with mock data."""
        # Create the sensor
        sensor = UnraidParitySpeedSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Parity Speed"
        assert sensor.icon == "mdi:speedometer"
        
        # Check sensor value
        assert sensor.native_value == "120 MB/s"
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"parity_status": {}}
        assert sensor.native_value is None
        
        # Test with inactive parity check
        mock_coordinator.data = {
            "parity_status": {
                "status": "IDLE",
                "speed": None
            }
        }
        assert sensor.native_value is None 