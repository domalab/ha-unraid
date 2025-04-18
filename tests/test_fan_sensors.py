"""Unit tests for Unraid fan sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, REVOLUTIONS_PER_MINUTE

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.base import UnraidSensorBase
from custom_components.unraid.sensors.metadata import ALL_SENSORS


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample fan data from unraid_collector."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    coordinator.hostname = "unraid"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"
    
    # Mock data that would be collected by unraid_collector.py
    coordinator.data = {
        "system_stats": {
            "fan_info": {
                "ipmi_fans": """CPU1 Fan       | 1100 RPM        | ok
CPU2 Fan       | 1050 RPM        | ok
SYS1 Fan       | 800 RPM         | ok
SYS2 Fan       | 820 RPM         | ok
PSU1 Fan       | 0 RPM           | ok""",
                "hwmon_fans": """fan1_input: 1120
fan2_input: 1060
fan3_input: 810
fan4_input: 825
fan5_input: 0""",
                "fan_control_config": """# Dynamix fan control configuration
FAN_LOW=35
FAN_HIGH=60
FANCTL=ipmi
IPMI_TEMP=CPU
IPMI_FAN=CPU
""",
                "fan_speeds": [
                    {
                        "name": "CPU1 Fan",
                        "rpm": 1100,
                        "status": "ok",
                        "type": "cpu",
                        "controllable": True
                    },
                    {
                        "name": "CPU2 Fan",
                        "rpm": 1050,
                        "status": "ok",
                        "type": "cpu",
                        "controllable": True
                    },
                    {
                        "name": "SYS1 Fan",
                        "rpm": 800,
                        "status": "ok",
                        "type": "system",
                        "controllable": False
                    },
                    {
                        "name": "SYS2 Fan",
                        "rpm": 820,
                        "status": "ok",
                        "type": "system",
                        "controllable": False
                    },
                    {
                        "name": "PSU1 Fan",
                        "rpm": 0,
                        "status": "ok",
                        "type": "psu",
                        "controllable": False
                    }
                ],
                "fan_control_active": True,
                "fan_control_type": "ipmi",
                "fan_threshold_low": 35,
                "fan_threshold_high": 60,
            }
        }
    }
    
    return coordinator


class TestFanSensorBase:
    """Base class for testing fan sensors."""
    
    class UnraidFanSensorTest(UnraidSensorBase):
        """Test implementation of a fan sensor."""
        
        def __init__(self, coordinator, name="Test Fan Sensor", key="test_fan", 
                    device_class=None, state_class=None, unit=None, icon=None):
            """Initialize the test sensor."""
            from custom_components.unraid.sensors.const import UnraidSensorEntityDescription
            
            description = UnraidSensorEntityDescription(
                key=key,
                name=name,
                device_class=device_class,
                state_class=state_class,
                native_unit_of_measurement=unit,
                icon=icon
            )
            
            super().__init__(coordinator, description)
        
        @property
        def fan_data(self) -> Dict[str, Any]:
            """Get fan data from coordinator."""
            return self.coordinator.data.get("system_stats", {}).get("fan_info", {})
            
        @property
        def native_value(self):
            """Return sensor value."""
            # This would be overridden in actual implementations
            return True


class TestFanSpeedSensor(TestFanSensorBase):
    """Test the fan speed sensor."""
    
    def test_fan_speed_sensor(self, mock_coordinator):
        """Test fan speed sensor with mock data."""
        class FanSpeedSensor(self.UnraidFanSensorTest):
            """Test implementation of fan speed sensor."""
            
            def __init__(self, coordinator, fan_index=0):
                """Initialize the sensor."""
                self.fan_index = fan_index
                
                fan_speeds = coordinator.data.get("system_stats", {}).get("fan_info", {}).get("fan_speeds", [])
                fan_name = fan_speeds[fan_index]["name"] if fan_index < len(fan_speeds) else f"Fan {fan_index}"
                
                super().__init__(
                    coordinator=coordinator,
                    name=f"{fan_name} Speed",
                    key=f"fan_speed_{fan_index}",
                    device_class=None,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=REVOLUTIONS_PER_MINUTE,
                    icon="mdi:fan"
                )
            
            @property
            def native_value(self):
                """Return the fan speed."""
                fan_speeds = self.fan_data.get("fan_speeds", [])
                
                if not fan_speeds or self.fan_index >= len(fan_speeds):
                    return None
                    
                return fan_speeds[self.fan_index].get("rpm")
                
            @property
            def extra_state_attributes(self):
                """Return extra state attributes."""
                attrs = super().extra_state_attributes or {}
                
                fan_speeds = self.fan_data.get("fan_speeds", [])
                
                if fan_speeds and self.fan_index < len(fan_speeds):
                    fan = fan_speeds[self.fan_index]
                    attrs["name"] = fan.get("name")
                    attrs["status"] = fan.get("status")
                    attrs["type"] = fan.get("type") 
                    attrs["controllable"] = fan.get("controllable", False)
                    
                return attrs
        
        # Create the sensor for the first CPU fan
        sensor = FanSpeedSensor(mock_coordinator, 0)
        
        # Check sensor properties
        assert sensor.name == "CPU1 Fan Speed"
        assert sensor.native_unit_of_measurement == REVOLUTIONS_PER_MINUTE
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        assert sensor.icon == "mdi:fan"
        
        # Check sensor value
        assert sensor.native_value == 1100
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["name"] == "CPU1 Fan"
        assert attrs["status"] == "ok"
        assert attrs["type"] == "cpu"
        assert attrs["controllable"] is True
        
        # Test with a different fan (system fan)
        sensor = FanSpeedSensor(mock_coordinator, 2)
        assert sensor.name == "SYS1 Fan Speed"
        assert sensor.native_value == 800
        attrs = sensor.extra_state_attributes
        assert attrs["type"] == "system"
        assert attrs["controllable"] is False
        
        # Test with non-existent fan
        sensor = FanSpeedSensor(mock_coordinator, 10)
        assert sensor.native_value is None
        
        # Test with no data
        mock_coordinator.data = {}
        sensor = FanSpeedSensor(mock_coordinator, 0)
        assert sensor.native_value is None


class TestFanStatusSensor(TestFanSensorBase):
    """Test the fan status sensor."""
    
    def test_fan_status_sensor(self, mock_coordinator):
        """Test fan status sensor with mock data."""
        class FanStatusSensor(self.UnraidFanSensorTest):
            """Test implementation of fan status sensor."""
            
            def __init__(self, coordinator, fan_index=0):
                """Initialize the sensor."""
                self.fan_index = fan_index
                
                fan_speeds = coordinator.data.get("system_stats", {}).get("fan_info", {}).get("fan_speeds", [])
                fan_name = fan_speeds[fan_index]["name"] if fan_index < len(fan_speeds) else f"Fan {fan_index}"
                
                super().__init__(
                    coordinator=coordinator,
                    name=f"{fan_name} Status",
                    key=f"fan_status_{fan_index}",
                    icon="mdi:fan-alert"
                )
            
            @property
            def native_value(self):
                """Return the fan status."""
                fan_speeds = self.fan_data.get("fan_speeds", [])
                
                if not fan_speeds or self.fan_index >= len(fan_speeds):
                    return None
                    
                return fan_speeds[self.fan_index].get("status")
            
            @property
            def icon(self):
                """Return the icon based on fan status."""
                status = self.native_value
                
                if status == "ok":
                    return "mdi:fan"
                else:
                    return "mdi:fan-alert"
        
        # Create the sensor for the first CPU fan
        sensor = FanStatusSensor(mock_coordinator, 0)
        
        # Check sensor properties
        assert sensor.name == "CPU1 Fan Status"
        
        # Check sensor value
        assert sensor.native_value == "ok"
        
        # Check icon
        assert sensor.icon == "mdi:fan"
        
        # Test with modified fan status
        mock_coordinator.data["system_stats"]["fan_info"]["fan_speeds"][0]["status"] = "critical"
        assert sensor.native_value == "critical"
        assert sensor.icon == "mdi:fan-alert"


class TestFanControlConfigSensor(TestFanSensorBase):
    """Test the fan control configuration sensor."""
    
    def test_fan_control_config_sensor(self, mock_coordinator):
        """Test fan control configuration sensor with mock data."""
        class FanControlSensor(self.UnraidFanSensorTest):
            """Test implementation of fan control sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="Fan Control",
                    key="fan_control",
                    icon="mdi:fan-auto"
                )
            
            @property
            def native_value(self):
                """Return the fan control type."""
                return self.fan_data.get("fan_control_type")
                
            @property
            def extra_state_attributes(self):
                """Return extra state attributes."""
                attrs = super().extra_state_attributes or {}
                
                attrs["active"] = self.fan_data.get("fan_control_active", False)
                attrs["low_threshold"] = self.fan_data.get("fan_threshold_low")
                attrs["high_threshold"] = self.fan_data.get("fan_threshold_high")
                
                return attrs
        
        # Create the sensor
        sensor = FanControlSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Fan Control"
        assert sensor.icon == "mdi:fan-auto"
        
        # Check sensor value
        assert sensor.native_value == "ipmi"
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["active"] is True
        assert attrs["low_threshold"] == 35
        assert attrs["high_threshold"] == 60
        
        # Test with no fan control
        mock_coordinator.data["system_stats"]["fan_info"]["fan_control_active"] = False
        assert sensor.extra_state_attributes["active"] is False
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None 