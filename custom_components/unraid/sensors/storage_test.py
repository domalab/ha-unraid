"""Storage sensors for Unraid integration - test compatibility."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfInformation

from .test_base import UnraidTestSensor

_LOGGER = logging.getLogger(__name__)


class UnraidDiskSensor(UnraidTestSensor):
    """Disk sensor for Unraid - test compatibility."""

    def __init__(self, coordinator, disk_name: str, device_path: str = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._disk_name = disk_name
        self._device_path = device_path
        self._attr_unique_id = f"unraid_{disk_name}_usage"
        self._attr_name = f"{disk_name} Usage"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:harddisk"
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {("unraid", self._disk_name)},
            "name": f"Unraid {self._disk_name.capitalize()}",
            "manufacturer": "Unraid",
            "model": "Disk",
        }

    @property
    def native_value(self) -> Optional[float]:
        """Return the disk usage percentage."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None

        for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == self._disk_name:
                use_percent = disk.get("use_percent", "0%")
                # Remove the % sign and convert to float
                return float(use_percent.rstrip("%"))

        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}

        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return attrs

        for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == self._disk_name:
                attrs["device"] = disk.get("device")
                attrs["size"] = disk.get("size")
                attrs["used"] = disk.get("used")
                attrs["available"] = disk.get("available")
                attrs["mount_point"] = disk.get("mount_point")
                attrs["filesystem"] = disk.get("filesystem")
                attrs["temperature"] = disk.get("temperature")
                attrs["serial"] = disk.get("serial")
                attrs["smart_status"] = disk.get("smart_status")
                return attrs

        return attrs


class UnraidDiskTempSensor(UnraidTestSensor):
    """Disk temperature sensor for Unraid - test compatibility."""

    def __init__(self, coordinator, disk_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._disk_name = disk_name
        self._attr_unique_id = f"unraid_{disk_name}_temp"
        self._attr_name = f"{disk_name} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> Optional[int]:
        """Return the disk temperature."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None

        for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == self._disk_name:
                return disk.get("temperature")

        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}

        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return attrs

        for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == self._disk_name:
                attrs["serial"] = disk.get("serial")
                attrs["smart_status"] = disk.get("smart_status")
                return attrs

        return attrs


class UnraidTotalSpaceSensor(UnraidTestSensor):
    """Total space sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_total_space"
        self._attr_name = "Total Space"
        self._attr_native_unit_of_measurement = UnitOfInformation.TERABYTES
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:harddisk"
        self._attr_device_class = SensorDeviceClass.DATA_SIZE

    @property
    def native_value(self) -> Optional[float]:
        """Return the total space in TB."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None

        array_info = self.coordinator.data.get("system_stats", {}).get("array_info", {})
        if not array_info or "total_size" not in array_info:
            return None

        # Extract the number from the string (e.g., "8.0T")
        total_size = array_info.get("total_size", "0T")
        if isinstance(total_size, str) and total_size.endswith("T"):
            return float(total_size.rstrip("T"))

        # If we have bytes, convert to TB
        total_bytes = array_info.get("total_size_bytes", 0)
        if total_bytes:
            return round(total_bytes / 1099511627776, 1)  # Convert bytes to TB

        return None


class UnraidUsedSpaceSensor(UnraidTestSensor):
    """Used space sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_used_space"
        self._attr_name = "Used Space"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:harddisk"
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR

    @property
    def native_value(self) -> Optional[float]:
        """Return the used space percentage."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None

        array_info = self.coordinator.data.get("system_stats", {}).get("array_info", {})
        if not array_info:
            return None

        return array_info.get("usage_percent")


class UnraidCacheUsageSensor(UnraidTestSensor):
    """Cache usage sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_cache_usage"
        self._attr_name = "Cache Usage"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:harddisk"
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR

    @property
    def native_value(self) -> Optional[float]:
        """Return the cache usage percentage."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None

        for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == "cache":
                use_percent = disk.get("use_percent", "0%")
                # Remove the % sign and convert to float
                return float(use_percent.rstrip("%"))

        return None
