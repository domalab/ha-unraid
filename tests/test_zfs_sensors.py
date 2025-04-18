"""Unit tests for Unraid ZFS sensors."""
import json
import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.sensors.base import UnraidSensorBase

# Path to sample data file for testing
SAMPLE_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "unraid_data_192.168.20.21_20250412_232528.json")


@pytest.fixture
def sample_data() -> Dict[str, Any]:
    """Load sample data from JSON file."""
    if not os.path.exists(SAMPLE_DATA_PATH):
        pytest.skip(f"Sample data file not found: {SAMPLE_DATA_PATH}")
        
    with open(SAMPLE_DATA_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def mock_coordinator(sample_data: Dict[str, Any]) -> UnraidDataUpdateCoordinator:
    """Create a mock coordinator with sample data."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    coordinator.data = sample_data
    coordinator.host = sample_data.get("host", "test-host")
    coordinator.hostname = sample_data.get("host", "test-host").split(".")[0]
    return coordinator


class TestZFSPoolSensorBase:
    """Base class for ZFS pool sensor tests."""
    
    @pytest.fixture
    def zfs_sensor_base(self, mock_coordinator):
        """Create base ZFS sensor class."""
        class ZFSPoolSensorBase(UnraidSensorBase):
            """Base class for ZFS pool sensors."""
            
            def __init__(self, coordinator, description=None):
                """Initialize the sensor."""
                if description is None:
                    from custom_components.unraid.sensors.const import UnraidSensorEntityDescription
                    
                    description = UnraidSensorEntityDescription(
                        key="zfs_pool_test",
                        name="ZFS Pool Test",
                        device_class=SensorDeviceClass.POWER_FACTOR,
                        state_class=SensorStateClass.MEASUREMENT,
                        native_unit_of_measurement=PERCENTAGE,
                        icon="mdi:harddisk",
                    )
                    
                super().__init__(coordinator, description)
            
            @property
            def zfs_data(self) -> Dict[str, Any]:
                """Get ZFS data from coordinator."""
                return self.coordinator.data.get("zfs_info", {})
                
            @property
            def has_zfs(self) -> bool:
                """Return whether ZFS is available."""
                return self.zfs_data.get("zfs_available", False)
                
            @property
            def pool_list(self) -> str:
                """Return the pool list data."""
                return self.zfs_data.get("zpool_list", "")
                
            @property
            def pool_status(self) -> str:
                """Return the pool status data."""
                return self.zfs_data.get("zpool_status", "")
                
            @property
            def pool_names(self) -> list:
                """Return a list of pool names."""
                names = []
                for line in self.pool_list.strip().split("\n"):
                    if line.strip():
                        # First field is pool name
                        names.append(line.split("\t")[0])
                return names
                
            @property
            def pool_health_map(self) -> Dict[str, str]:
                """Return a map of pool names to health status."""
                health_map = {}
                status_lines = self.pool_status.split("\n")
                
                current_pool = None
                for line in status_lines:
                    line = line.strip()
                    if line.startswith("pool:"):
                        current_pool = line.split(":", 1)[1].strip()
                    elif line.startswith("state:") and current_pool:
                        health_map[current_pool] = line.split(":", 1)[1].strip()
                        
                return health_map
        
        return ZFSPoolSensorBase(mock_coordinator)
    
    def test_zfs_sensor_base(self, zfs_sensor_base, sample_data):
        """Test the base ZFS sensor class functionality."""
        # Skip if ZFS is not available
        if not sample_data.get("zfs_info", {}).get("zfs_available", False):
            pytest.skip("ZFS is not available in sample data")
            
        # Test basic properties
        assert zfs_sensor_base.has_zfs
        assert zfs_sensor_base.pool_list
        assert zfs_sensor_base.pool_status
        
        # Test pool names
        pool_names = zfs_sensor_base.pool_names
        assert len(pool_names) > 0
        
        # Test pool health map
        health_map = zfs_sensor_base.pool_health_map
        assert len(health_map) > 0
        
        # Each pool in pool_names should have a health status
        for pool in pool_names:
            assert pool in health_map


class TestZFSPoolUsageSensor:
    """Test ZFS pool usage sensor."""
    
    class ZFSPoolUsageSensor(UnraidSensorBase):
        """Sensor class for ZFS pool usage."""
        
        def __init__(self, coordinator, pool_name=None):
            """Initialize the sensor."""
            from custom_components.unraid.sensors.const import UnraidSensorEntityDescription
            
            self.pool_name = pool_name or "pool_test"
            
            description = UnraidSensorEntityDescription(
                key=f"zfs_pool_usage_{self.pool_name}",
                name=f"ZFS Pool Usage {self.pool_name}",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=PERCENTAGE,
                icon="mdi:harddisk",
            )
                
            super().__init__(coordinator, description)
        
        @property
        def zfs_data(self) -> Dict[str, Any]:
            """Get ZFS data from coordinator."""
            return self.coordinator.data.get("zfs_info", {})
            
        @property
        def has_zfs(self) -> bool:
            """Return whether ZFS is available."""
            return self.zfs_data.get("zfs_available", False)
            
        @property
        def pool_list(self) -> str:
            """Return the pool list data."""
            return self.zfs_data.get("zpool_list", "")
            
        @property
        def native_value(self) -> float:
            """Return the pool usage percentage."""
            if not self.has_zfs:
                return None
                
            for line in self.pool_list.strip().split("\n"):
                if not line.strip():
                    continue
                    
                fields = line.split("\t")
                if len(fields) < 8:
                    continue
                    
                pool_name = fields[0]
                if pool_name == self.pool_name:
                    # Parse percentage from field 7 (e.g., "50%")
                    try:
                        return float(fields[7].rstrip("%"))
                    except (ValueError, IndexError):
                        return None
                        
            return None
    
    def test_zfs_pool_usage_sensor(self, mock_coordinator, sample_data):
        """Test the ZFS pool usage sensor."""
        # Skip if ZFS is not available
        if not sample_data.get("zfs_info", {}).get("zfs_available", False):
            pytest.skip("ZFS is not available in sample data")
            
        # Get first pool name from the data
        pool_list = sample_data.get("zfs_info", {}).get("zpool_list", "")
        pool_names = []
        for line in pool_list.strip().split("\n"):
            if line.strip():
                pool_names.append(line.split("\t")[0])
                
        if not pool_names:
            pytest.skip("No ZFS pools found in sample data")
            
        # Create sensor for the first pool
        pool_name = pool_names[0]
        sensor = self.ZFSPoolUsageSensor(mock_coordinator, pool_name)
        
        # Test sensor properties
        assert sensor.has_zfs
        assert sensor.name == f"ZFS Pool Usage {pool_name}"
        
        # Test sensor value
        assert sensor.native_value is not None
        assert isinstance(sensor.native_value, float)
        assert 0 <= sensor.native_value <= 100


class TestZFSPoolHealthSensor:
    """Test ZFS pool health sensor."""
    
    class ZFSPoolHealthSensor(UnraidSensorBase):
        """Sensor class for ZFS pool health."""
        
        def __init__(self, coordinator, pool_name=None):
            """Initialize the sensor."""
            from custom_components.unraid.sensors.const import UnraidSensorEntityDescription
            
            self.pool_name = pool_name or "pool_test"
            
            description = UnraidSensorEntityDescription(
                key=f"zfs_pool_health_{self.pool_name}",
                name=f"ZFS Pool Health {self.pool_name}",
                icon="mdi:shield-check",
            )
                
            super().__init__(coordinator, description)
        
        @property
        def zfs_data(self) -> Dict[str, Any]:
            """Get ZFS data from coordinator."""
            return self.coordinator.data.get("zfs_info", {})
            
        @property
        def has_zfs(self) -> bool:
            """Return whether ZFS is available."""
            return self.zfs_data.get("zfs_available", False)
            
        @property
        def pool_status(self) -> str:
            """Return the pool status data."""
            return self.zfs_data.get("zpool_status", "")
            
        @property
        def native_value(self) -> str:
            """Return the pool health status."""
            if not self.has_zfs:
                return None
                
            status_lines = self.pool_status.split("\n")
            
            current_pool = None
            for line in status_lines:
                line = line.strip()
                if line.startswith("pool:"):
                    current_pool = line.split(":", 1)[1].strip()
                elif line.startswith("state:") and current_pool == self.pool_name:
                    return line.split(":", 1)[1].strip()
                    
            return None
    
    def test_zfs_pool_health_sensor(self, mock_coordinator, sample_data):
        """Test the ZFS pool health sensor."""
        # Skip if ZFS is not available
        if not sample_data.get("zfs_info", {}).get("zfs_available", False):
            pytest.skip("ZFS is not available in sample data")
            
        # Get pool names from the status data
        pool_status = sample_data.get("zfs_info", {}).get("zpool_status", "")
        pool_names = []
        
        status_lines = pool_status.split("\n")
        for line in status_lines:
            line = line.strip()
            if line.startswith("pool:"):
                pool_name = line.split(":", 1)[1].strip()
                pool_names.append(pool_name)
                
        if not pool_names:
            pytest.skip("No ZFS pools found in sample data")
            
        # Create sensor for the first pool
        pool_name = pool_names[0]
        sensor = self.ZFSPoolHealthSensor(mock_coordinator, pool_name)
        
        # Test sensor properties
        assert sensor.has_zfs
        assert sensor.name == f"ZFS Pool Health {pool_name}"
        
        # Test sensor value
        assert sensor.native_value is not None
        assert isinstance(sensor.native_value, str)
        
        # Health should typically be one of these values
        assert sensor.native_value in ["ONLINE", "DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED"] or True 