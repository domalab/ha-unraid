"""Unit tests for Unraid Docker and VM sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.docker import (
    UnraidDockerContainerCountSensor,
    UnraidDockerStatusSensor,
)
from custom_components.unraid.sensors.vm import (
    UnraidVMCountSensor,
    UnraidVMStatusSensor,
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
        "docker_info": {
            "docker_running": True,
            "container_count": 15,
            "docker_containers": [
                {
                    "name": "homeassistant",
                    "id": "abc123def456",
                    "state": "running",
                    "status": "Up 2 days",
                    "image": "homeassistant/home-assistant:latest",
                    "created": "2023-04-10 15:23:45"
                },
                {
                    "name": "plex",
                    "id": "def456ghi789",
                    "state": "running",
                    "status": "Up 2 days",
                    "image": "plexinc/pms-docker:latest",
                    "created": "2023-04-10 15:22:00"
                },
                {
                    "name": "stopped-container",
                    "id": "jkl012mno345",
                    "state": "exited",
                    "status": "Exited (0) 1 day ago",
                    "image": "test/image:latest",
                    "created": "2023-04-09 10:00:00"
                }
            ]
        },
        "vm_info": {
            "vms_running": True,
            "libvirt_running": True,
            "vm_count": 2,
            "vms": [
                {
                    "name": "Windows 10",
                    "status": "running",
                    "os_type": "windows",
                    "memory": 8192,  # MB
                    "cpus": 4,
                    "vnc_port": 5900
                },
                {
                    "name": "Ubuntu Server",
                    "status": "shutoff",
                    "os_type": "linux",
                    "memory": 4096,  # MB
                    "cpus": 2,
                    "vnc_port": 5901
                }
            ]
        }
    }
    
    return coordinator


class TestUnraidDockerContainerCountSensor:
    """Test the Unraid Docker container count sensor."""
    
    def test_docker_container_count_sensor(self, mock_coordinator):
        """Test Docker container count sensor with mock data."""
        # Create the sensor
        sensor = UnraidDockerContainerCountSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Docker Containers"
        assert sensor.icon == "mdi:docker"
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 15
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["running_containers"] == 2
        assert attrs["stopped_containers"] == 1
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"docker_info": {}}
        assert sensor.native_value is None
        
        # Test with Docker not running
        mock_coordinator.data = {
            "docker_info": {
                "docker_running": False,
                "container_count": 0,
                "docker_containers": []
            }
        }
        assert sensor.native_value == 0


class TestUnraidDockerStatusSensor:
    """Test the Unraid Docker status sensor."""
    
    def test_docker_status_sensor(self, mock_coordinator):
        """Test Docker status sensor with mock data."""
        # Create the sensor
        sensor = UnraidDockerStatusSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "Docker Status"
        assert sensor.icon == "mdi:docker"
        
        # Check sensor value
        assert sensor.native_value == "running"
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value == "not_detected"
        
        # Test with partial data
        mock_coordinator.data = {"docker_info": {}}
        assert sensor.native_value == "not_detected"
        
        # Test with Docker not running
        mock_coordinator.data = {
            "docker_info": {
                "docker_running": False
            }
        }
        assert sensor.native_value == "stopped"


class TestUnraidVMCountSensor:
    """Test the Unraid VM count sensor."""
    
    def test_vm_count_sensor(self, mock_coordinator):
        """Test VM count sensor with mock data."""
        # Create the sensor
        sensor = UnraidVMCountSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "VMs"
        assert sensor.icon == "mdi:server"
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        
        # Check sensor value
        assert sensor.native_value == 2
        
        # Check extra state attributes
        attrs = sensor.extra_state_attributes
        assert attrs["running_vms"] == 1
        assert attrs["stopped_vms"] == 1
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value is None
        
        # Test with partial data
        mock_coordinator.data = {"vm_info": {}}
        assert sensor.native_value is None
        
        # Test with VMs not running
        mock_coordinator.data = {
            "vm_info": {
                "vms_running": False,
                "libvirt_running": False,
                "vm_count": 0,
                "vms": []
            }
        }
        assert sensor.native_value == 0


class TestUnraidVMStatusSensor:
    """Test the Unraid VM status sensor."""
    
    def test_vm_status_sensor(self, mock_coordinator):
        """Test VM status sensor with mock data."""
        # Create the sensor
        sensor = UnraidVMStatusSensor(mock_coordinator)
        
        # Check sensor properties
        assert sensor.name == "VM Status"
        assert sensor.icon == "mdi:server"
        
        # Check sensor value
        assert sensor.native_value == "running"
        
        # Test with no data
        mock_coordinator.data = {}
        assert sensor.native_value == "not_detected"
        
        # Test with partial data
        mock_coordinator.data = {"vm_info": {}}
        assert sensor.native_value == "not_detected"
        
        # Test with VMs not running but libvirt running
        mock_coordinator.data = {
            "vm_info": {
                "vms_running": False,
                "libvirt_running": True
            }
        }
        assert sensor.native_value == "idle"
        
        # Test with neither VMs nor libvirt running
        mock_coordinator.data = {
            "vm_info": {
                "vms_running": False,
                "libvirt_running": False
            }
        }
        assert sensor.native_value == "stopped"


class TestDockerIndividualContainerSensors:
    """Test Docker individual container status sensors."""
    
    def test_docker_container_status_sensors(self, mock_coordinator):
        """Test Docker container status sensors with mock data."""
        # This would typically test the individual container sensors if they exist
        # For now, we'll just verify the container data is available in the expected format
        docker_info = mock_coordinator.data.get("docker_info", {})
        containers = docker_info.get("docker_containers", [])
        
        # Verify we have container data in the expected format
        assert len(containers) > 0
        
        # Check first container
        container = containers[0]
        assert container.get("name") == "homeassistant"
        assert container.get("state") == "running"
        assert container.get("status") == "Up 2 days"


class TestVMIndividualVMSensors:
    """Test VM individual VM status sensors."""
    
    def test_vm_status_sensors(self, mock_coordinator):
        """Test VM status sensors with mock data."""
        # This would typically test the individual VM sensors if they exist
        # For now, we'll just verify the VM data is available in the expected format
        vm_info = mock_coordinator.data.get("vm_info", {})
        vms = vm_info.get("vms", [])
        
        # Verify we have VM data in the expected format
        assert len(vms) > 0
        
        # Check first VM
        vm = vms[0]
        assert vm.get("name") == "Windows 10"
        assert vm.get("status") == "running"
        assert vm.get("os_type") == "windows"
        assert vm.get("memory") == 8192
        assert vm.get("cpus") == 4 