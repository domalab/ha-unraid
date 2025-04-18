"""Unit tests for Unraid GPU sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.base import UnraidSensorBase
from custom_components.unraid.sensors.metadata import ALL_SENSORS


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample GPU data from unraid_collector."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    coordinator.hostname = "unraid"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"
    
    # Mock data that would be collected by unraid_collector.py
    coordinator.data = {
        "gpu_info": {
            "has_nvidia": True,
            "has_intel": True,
            "has_amd": False,
            "gpu_count": 2,
            "gpu_drivers": "nvidia 535.129.03\ni915 1234\n",
            "nvidia_gpus": [
                {
                    "name": "NVIDIA GeForce RTX 3080",
                    "uuid": "GPU-12345678-1234-5678-1234-567812345678",
                    "temperature": 65,
                    "fan_speed": 45,
                    "utilization": 34,
                    "memory_total": 10240,
                    "memory_used": 3240,
                    "memory_free": 7000,
                    "power_draw": 220,
                    "power_limit": 320,
                    "clock_core": 1950,
                    "clock_memory": 9500
                }
            ],
            "intel_gpus": [
                {
                    "name": "Intel(R) UHD Graphics 630",
                    "device_id": "0x3e92",
                    "driver_version": "i915 1234",
                    "utilization": 15,
                    "frequency": 1150
                }
            ],
            "nvidia_smi_output": "| NVIDIA-SMI 535.129.03             Driver Version: 535.129.03   CUDA Version: 12.2     |\n| GPU  Name                 Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |\n| Fan  Temp  Perf          Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |\n|                                       |                      |               MIG M. |\n|   0  NVIDIA GeForce RTX 3080    Off  | 00000000:01:00.0  On |                  N/A |\n| 45%   65C    P2             220W / 320W |   3240MiB / 10240MiB |     34%      Default |",
            "intel_gpu_top_output": "Intel GPU utilization 15%\nFrequency: 1150 MHz"
        }
    }
    
    return coordinator


class TestGPUSensorBase:
    """Base class for testing GPU sensors."""
    
    class UnraidGPUSensorTest(UnraidSensorBase):
        """Test implementation of a GPU sensor."""
        
        def __init__(self, coordinator, name="Test GPU Sensor", key="test_gpu", 
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
        def gpu_data(self) -> Dict[str, Any]:
            """Get GPU data from coordinator."""
            return self.coordinator.data.get("gpu_info", {})
            
        @property
        def native_value(self):
            """Return sensor value."""
            # This would be overridden in actual implementations
            return True


class TestNvidiaGPUTemperatureSensor(TestGPUSensorBase):
    """Test the Nvidia GPU temperature sensor."""
    
    def test_nvidia_gpu_temperature_sensor(self, mock_coordinator):
        """Test Nvidia GPU temperature sensor with mock data."""
        class NvidiaGPUTemperatureSensor(self.UnraidGPUSensorTest):
            """Test implementation of Nvidia GPU temperature sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="NVIDIA GPU Temperature",
                    key="nvidia_gpu_temperature",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=UnitOfTemperature.CELSIUS,
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return the GPU temperature."""
                if not self.gpu_data.get("has_nvidia", False):
                    return None
                    
                gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                return gpu.get("temperature")
        
        # Create the sensor
        sensor = NvidiaGPUTemperatureSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "NVIDIA GPU Temperature"
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 65
        
        # Test with no Nvidia GPU
        mock_coordinator.data["gpu_info"]["has_nvidia"] = False
        assert sensor.native_value is None
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None


class TestNvidiaGPUUtilizationSensor(TestGPUSensorBase):
    """Test the Nvidia GPU utilization sensor."""
    
    def test_nvidia_gpu_utilization_sensor(self, mock_coordinator):
        """Test Nvidia GPU utilization sensor with mock data."""
        class NvidiaGPUUtilizationSensor(self.UnraidGPUSensorTest):
            """Test implementation of Nvidia GPU utilization sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="NVIDIA GPU Utilization",
                    key="nvidia_gpu_utilization",
                    device_class=SensorDeviceClass.POWER_FACTOR,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=PERCENTAGE,
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return the GPU utilization."""
                if not self.gpu_data.get("has_nvidia", False):
                    return None
                    
                gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                return gpu.get("utilization")
        
        # Create the sensor
        sensor = NvidiaGPUUtilizationSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "NVIDIA GPU Utilization"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 34
        
        # Test with missing utilization data
        mock_coordinator.data["gpu_info"]["nvidia_gpus"][0].pop("utilization")
        assert sensor.native_value is None


class TestNvidiaGPUFanSensor(TestGPUSensorBase):
    """Test the Nvidia GPU fan sensor."""
    
    def test_nvidia_gpu_fan_sensor(self, mock_coordinator):
        """Test Nvidia GPU fan sensor with mock data."""
        class NvidiaGPUFanSensor(self.UnraidGPUSensorTest):
            """Test implementation of Nvidia GPU fan sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="NVIDIA GPU Fan",
                    key="nvidia_gpu_fan",
                    device_class=SensorDeviceClass.POWER_FACTOR,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=PERCENTAGE,
                    icon="mdi:fan"
                )
            
            @property
            def native_value(self):
                """Return the GPU fan speed."""
                if not self.gpu_data.get("has_nvidia", False):
                    return None
                    
                gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                return gpu.get("fan_speed")
                
            @property
            def extra_state_attributes(self):
                """Return extra state attributes."""
                attrs = super().extra_state_attributes or {}
                
                if self.gpu_data.get("has_nvidia", False):
                    gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                    attrs["gpu_name"] = gpu.get("name")
                    
                return attrs
        
        # Create the sensor
        sensor = NvidiaGPUFanSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "NVIDIA GPU Fan"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 45
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["gpu_name"] == "NVIDIA GeForce RTX 3080"


class TestNvidiaGPUMemorySensor(TestGPUSensorBase):
    """Test the Nvidia GPU memory sensor."""
    
    def test_nvidia_gpu_memory_sensor(self, mock_coordinator):
        """Test Nvidia GPU memory sensor with mock data."""
        class NvidiaGPUMemorySensor(self.UnraidGPUSensorTest):
            """Test implementation of Nvidia GPU memory sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="NVIDIA GPU Memory",
                    key="nvidia_gpu_memory",
                    device_class=SensorDeviceClass.POWER_FACTOR,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=PERCENTAGE,
                    icon="mdi:memory"
                )
            
            @property
            def native_value(self):
                """Return the GPU memory usage percentage."""
                if not self.gpu_data.get("has_nvidia", False):
                    return None
                    
                gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                total = gpu.get("memory_total", 0)
                used = gpu.get("memory_used", 0)
                
                if total == 0:
                    return None
                    
                return round((used / total) * 100, 1)
                
            @property
            def extra_state_attributes(self):
                """Return extra state attributes."""
                attrs = super().extra_state_attributes or {}
                
                if self.gpu_data.get("has_nvidia", False):
                    gpu = self.gpu_data.get("nvidia_gpus", [{}])[0]
                    attrs["memory_total"] = f"{gpu.get('memory_total', 0)} MB"
                    attrs["memory_used"] = f"{gpu.get('memory_used', 0)} MB"
                    attrs["memory_free"] = f"{gpu.get('memory_free', 0)} MB"
                    
                return attrs
        
        # Create the sensor
        sensor = NvidiaGPUMemorySensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "NVIDIA GPU Memory"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 31.6  # (3240 / 10240) * 100 = 31.64...
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["memory_total"] == "10240 MB"
        assert attrs["memory_used"] == "3240 MB"
        assert attrs["memory_free"] == "7000 MB"


class TestIntelGPUUtilizationSensor(TestGPUSensorBase):
    """Test the Intel GPU utilization sensor."""
    
    def test_intel_gpu_utilization_sensor(self, mock_coordinator):
        """Test Intel GPU utilization sensor with mock data."""
        class IntelGPUUtilizationSensor(self.UnraidGPUSensorTest):
            """Test implementation of Intel GPU utilization sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="Intel GPU Utilization",
                    key="intel_gpu_utilization",
                    device_class=SensorDeviceClass.POWER_FACTOR,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=PERCENTAGE,
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return the GPU utilization."""
                if not self.gpu_data.get("has_intel", False):
                    return None
                    
                gpu = self.gpu_data.get("intel_gpus", [{}])[0]
                return gpu.get("utilization")
                
            @property
            def extra_state_attributes(self):
                """Return extra state attributes."""
                attrs = super().extra_state_attributes or {}
                
                if self.gpu_data.get("has_intel", False):
                    gpu = self.gpu_data.get("intel_gpus", [{}])[0]
                    attrs["name"] = gpu.get("name")
                    attrs["frequency"] = f"{gpu.get('frequency', 0)} MHz"
                    attrs["driver"] = gpu.get("driver_version")
                    
                return attrs
        
        # Create the sensor
        sensor = IntelGPUUtilizationSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Intel GPU Utilization"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.device_class == SensorDeviceClass.POWER_FACTOR
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 15
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["name"] == "Intel(R) UHD Graphics 630"
        assert attrs["frequency"] == "1150 MHz"
        assert attrs["driver"] == "i915 1234"
        
        # Test with no Intel GPU
        mock_coordinator.data["gpu_info"]["has_intel"] = False
        assert sensor.native_value is None
        
        # Reset for other tests
        mock_coordinator.data["gpu_info"]["has_intel"] = True


class TestGPUPresenceSensor(TestGPUSensorBase):
    """Test the GPU presence sensors."""
    
    def test_nvidia_presence_sensor(self, mock_coordinator):
        """Test Nvidia presence sensor with mock data."""
        class NvidiaPresenceSensor(self.UnraidGPUSensorTest):
            """Test implementation of Nvidia presence sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="NVIDIA GPU Present",
                    key="nvidia_gpu_present",
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return whether Nvidia GPU is present."""
                return self.gpu_data.get("has_nvidia", False)
        
        # Create the sensor
        sensor = NvidiaPresenceSensor(mock_coordinator)
        
        # Check sensor value
        assert sensor.native_value is True
        
        # Test with no Nvidia GPU
        mock_coordinator.data["gpu_info"]["has_nvidia"] = False
        assert sensor.native_value is False
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is False
    
    def test_intel_presence_sensor(self, mock_coordinator):
        """Test Intel presence sensor with mock data."""
        class IntelPresenceSensor(self.UnraidGPUSensorTest):
            """Test implementation of Intel presence sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="Intel GPU Present",
                    key="intel_gpu_present",
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return whether Intel GPU is present."""
                return self.gpu_data.get("has_intel", False)
        
        # Create the sensor
        sensor = IntelPresenceSensor(mock_coordinator)
        
        # Check sensor value
        assert sensor.native_value is True
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is False
    
    def test_amd_presence_sensor(self, mock_coordinator):
        """Test AMD presence sensor with mock data."""
        class AMDPresenceSensor(self.UnraidGPUSensorTest):
            """Test implementation of AMD presence sensor."""
            
            def __init__(self, coordinator):
                """Initialize the sensor."""
                super().__init__(
                    coordinator=coordinator,
                    name="AMD GPU Present",
                    key="amd_gpu_present",
                    icon="mdi:gpu"
                )
            
            @property
            def native_value(self):
                """Return whether AMD GPU is present."""
                return self.gpu_data.get("has_amd", False)
        
        # Create the sensor
        sensor = AMDPresenceSensor(mock_coordinator)
        
        # Check sensor value
        assert sensor.native_value is False
        
        # Test with AMD GPU
        mock_coordinator.data["gpu_info"]["has_amd"] = True
        assert sensor.native_value is True 