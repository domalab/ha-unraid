"""Tests for the Unraid binary sensor platform."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.unraid.binary_sensor import (
    async_setup_entry,
    UnraidBinarySensorBase,
    UnraidArrayDiskSensor,
    UnraidPoolDiskSensor,
    UnraidParityDiskSensor,
    UnraidParityCheckSensor,
    UnraidUPSBinarySensor,
    _get_parity_info,
)
from custom_components.unraid.const import DOMAIN
from custom_components.unraid.diagnostics.const import SENSOR_DESCRIPTIONS


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with sample data from unraid_collector."""
    coordinator = MagicMock()
    coordinator.hostname = "unraid"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"
    
    # Mock the complete data structure that would be collected by unraid_collector.py
    coordinator.data = {
        "system_stats": {
            "cpu_usage": 15.2,
            "memory_usage": {
                "total": 32853524,
                "free": 26673728,
                "used": 6179796,
                "percentage": 18.9
            },
            "ups_info": {
                "has_ups": True,
                "status": "OL",
                "battery_charge": 100,
                "load_percent": 23,
                "model": "APC Smart-UPS 1500"
            },
            "individual_disks": [
                {
                    "name": "disk1",
                    "device": "/dev/sda",
                    "mount_point": "/mnt/disk1",
                    "size": "4.0T",
                    "used": "2.2T",
                    "available": "1.8T",
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
                    "used": "3.1T",
                    "available": "0.9T",
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
                    "used": "320G",
                    "available": "180G",
                    "use_percent": "64%",
                    "filesystem": "btrfs",
                    "smart_status": "PASS",
                    "temperature": 35,
                    "serial": "Samsung_SSD_850_EVO_500GB-123456"
                }
            ]
        },
        "parity_status": {
            "status": "ACTIVE",
            "progress": 42,
            "speed": "120 MB/s",
            "elapsed": "01:45:30",
            "estimated_finish": "02:15:10"
        },
        "parity_info": {
            "diskNumber.0": "0",
            "diskName.0": "parity",
            "diskSize.0": "4000787030016",
            "diskState.0": "DISK_OK",
            "diskId.0": "WDC_WD40EFRX-68WT0N0_WD-WCC7K3RTD5JK",
            "rdevNumber.0": "8:0",
            "rdevStatus.0": "DISK_OK",
            "rdevName.0": "/dev/sda",
            "rdevOffset.0": "0",
            "rdevSize.0": "4000787030016",
            "rdevId.0": "WDC_WD40EFRX-68WT0N0_WD-WCC7K3RTD5JK"
        }
    }
    
    # Mock the API
    coordinator.api = MagicMock()
    result = MagicMock()
    result.stdout = """diskNumber.0=0
diskName.0=parity
diskSize.0=4000787030016
diskState.0=DISK_OK
diskId.0=WDC_WD40EFRX-68WT0N0_WD-WCC7K3RTD5JK
rdevNumber.0=8:0
rdevStatus.0=DISK_OK
rdevName.0=/dev/sda
rdevOffset.0=0
rdevSize.0=4000787030016
rdevId.0=WDC_WD40EFRX-68WT0N0_WD-WCC7K3RTD5JK"""
    result.exit_status = 0
    coordinator.api.execute_command = AsyncMock(return_value=result)
    
    coordinator.async_request_refresh = AsyncMock()
    coordinator.last_update_success = True
    return coordinator


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry(hass: HomeAssistant, mock_coordinator):
    """Test setting up the binary sensor platform."""
    hass.data = {DOMAIN: {"test_entry_id": mock_coordinator}}
    
    # Create a mock entry and callback
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    
    # Track added entities
    added_entities = []
    async_add_entities = lambda entities: added_entities.extend(entities)
    
    # Call the setup entry function
    await async_setup_entry(hass, entry, async_add_entities)
    
    # Check that entities were added
    assert len(added_entities) > 0
    
    # Check for different types of sensors
    base_sensors = [e for e in added_entities if type(e) is UnraidBinarySensorBase]
    ups_sensors = [e for e in added_entities if isinstance(e, UnraidUPSBinarySensor)]
    array_disk_sensors = [e for e in added_entities if isinstance(e, UnraidArrayDiskSensor)]
    pool_disk_sensors = [e for e in added_entities if isinstance(e, UnraidPoolDiskSensor)]
    parity_sensors = [e for e in added_entities if isinstance(e, UnraidParityDiskSensor) or isinstance(e, UnraidParityCheckSensor)]
    
    # We should have some base sensors from SENSOR_DESCRIPTIONS
    assert len(base_sensors) == len(SENSOR_DESCRIPTIONS)
    
    # We should have UPS sensor since it's in our mock data
    assert len(ups_sensors) == 1
    
    # We should have array disk sensors
    assert len(array_disk_sensors) > 0
    
    # We should have a pool (cache) disk sensor
    assert len(pool_disk_sensors) > 0
    
    # We should have parity sensors
    assert len(parity_sensors) > 0


@pytest.mark.asyncio
async def test_get_parity_info(mock_coordinator):
    """Test retrieving parity information."""
    # Call the function to get parity information
    parity_info = await _get_parity_info(mock_coordinator)
    
    # Check that parity info is returned correctly
    assert parity_info is not None
    assert parity_info["diskName.0"] == "parity"
    assert parity_info["rdevName.0"] == "/dev/sda"
    assert parity_info["diskState.0"] == "DISK_OK"


@pytest.mark.asyncio
async def test_get_parity_info_error(mock_coordinator):
    """Test error handling when retrieving parity information."""
    # Simulate command error
    mock_coordinator.api.execute_command.side_effect = Exception("Test error")
    
    # Call the function to get parity information
    parity_info = await _get_parity_info(mock_coordinator)
    
    # Should return None on error
    assert parity_info is None


def test_array_disk_sensor(mock_coordinator):
    """Test an array disk binary sensor."""
    # Create the sensor
    sensor = UnraidArrayDiskSensor(
        coordinator=mock_coordinator,
        disk_name="disk1"
    )
    
    # Check sensor properties
    assert sensor.name == "disk1"
    assert sensor.unique_id.endswith("_disk1_health")
    
    # Should be healthy since smart_status is "PASS"
    assert sensor.is_on is False  # False means OK (no problem)
    
    # Check extra state attributes
    attrs = sensor.extra_state_attributes
    assert attrs["mount_point"] == "/mnt/disk1"
    assert attrs["size"] == "4.0T"
    assert attrs["used"] == "2.2T"
    assert attrs["temperature"] == 38
    assert attrs["smart_status"] == "PASS"


def test_array_disk_sensor_unhealthy(mock_coordinator):
    """Test an array disk binary sensor with unhealthy status."""
    # Create a copy of the data and modify one disk to be unhealthy
    mock_coordinator_unhealthy = MagicMock()
    mock_coordinator_unhealthy.data = {
        "system_stats": {
            "individual_disks": [
                {
                    "name": "disk1",
                    "device": "/dev/sda",
                    "mount_point": "/mnt/disk1",
                    "size": "4.0T",
                    "used": "2.2T",
                    "available": "1.8T",
                    "use_percent": "56%",
                    "filesystem": "xfs",
                    "smart_status": "WARN",  # Warning status
                    "temperature": 52,  # High temperature
                    "serial": "WDC-WD40EFRX-68WT0N0-123456"
                }
            ]
        }
    }
    
    # Create the sensor with unhealthy data
    sensor = UnraidArrayDiskSensor(
        coordinator=mock_coordinator_unhealthy,
        disk_name="disk1"
    )
    
    # Should indicate a problem
    assert sensor.is_on is True  # True means problem detected


def test_pool_disk_sensor(mock_coordinator):
    """Test a pool disk binary sensor."""
    # Create the sensor
    sensor = UnraidPoolDiskSensor(
        coordinator=mock_coordinator,
        disk_name="cache"
    )
    
    # Check sensor properties
    assert sensor.name == "cache"
    assert sensor.unique_id.endswith("_cache_health")
    
    # Should be healthy since smart_status is "PASS"
    assert sensor.is_on is False  # False means OK (no problem)
    
    # Check extra state attributes
    attrs = sensor.extra_state_attributes
    assert attrs["mount_point"] == "/mnt/cache"
    assert attrs["size"] == "500G"
    assert attrs["filesystem"] == "btrfs"
    assert attrs["temperature"] == 35


def test_parity_disk_sensor(mock_coordinator):
    """Test a parity disk binary sensor."""
    # Create the sensor
    sensor = UnraidParityDiskSensor(
        coordinator=mock_coordinator, 
        parity_info=mock_coordinator.data["parity_info"]
    )
    
    # Check sensor properties
    assert "parity" in sensor.name.lower()
    
    # Should be healthy since disk state is "DISK_OK"
    assert sensor.is_on is False  # False means OK (no problem)
    
    # Check extra state attributes
    attrs = sensor.extra_state_attributes
    assert attrs["device"] == "/dev/sda"
    assert attrs["state"] == "DISK_OK"
    assert attrs["disk_id"] == "WDC_WD40EFRX-68WT0N0_WD-WCC7K3RTD5JK"


def test_parity_check_sensor(mock_coordinator):
    """Test the parity check binary sensor."""
    # Create the sensor
    sensor = UnraidParityCheckSensor(coordinator=mock_coordinator)
    
    # Check sensor properties
    assert "parity check" in sensor.name.lower()
    
    # Should be ON since parity check is ACTIVE
    assert sensor.is_on is True
    
    # Check extra state attributes
    attrs = sensor.extra_state_attributes
    assert attrs["progress"] == 42
    assert attrs["speed"] == "120 MB/s"
    assert attrs["elapsed"] == "01:45:30"
    assert attrs["estimated_finish"] == "02:15:10"


def test_ups_binary_sensor(mock_coordinator):
    """Test the UPS binary sensor."""
    # Create the sensor
    sensor = UnraidUPSBinarySensor(coordinator=mock_coordinator)
    
    # Check sensor properties
    assert "ups" in sensor.name.lower()
    
    # Should be healthy since UPS is on line power (OL)
    assert sensor.is_on is False  # False means OK (no problem)
    
    # Check extra state attributes
    attrs = sensor.extra_state_attributes
    assert attrs["status"] == "OL"
    assert attrs["battery_charge"] == 100
    assert attrs["load_percent"] == 23
    assert attrs["model"] == "APC Smart-UPS 1500"


def test_ups_binary_sensor_on_battery(mock_coordinator):
    """Test the UPS binary sensor when on battery power."""
    # Create a copy with UPS on battery
    mock_coordinator_battery = MagicMock()
    mock_coordinator_battery.data = {
        "system_stats": {
            "ups_info": {
                "has_ups": True,
                "status": "OB",  # On Battery
                "battery_charge": 85,
                "load_percent": 23,
                "model": "APC Smart-UPS 1500"
            }
        }
    }
    
    # Create the sensor
    sensor = UnraidUPSBinarySensor(coordinator=mock_coordinator_battery)
    
    # Should indicate a problem when on battery power
    assert sensor.is_on is True  # True means problem detected
    
    # Check icon changes when on battery
    assert sensor.icon == "mdi:power-plug-off" 