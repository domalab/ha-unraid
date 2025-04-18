"""System sensors for Unraid integration - test compatibility."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .test_base import UnraidTestSensor

_LOGGER = logging.getLogger(__name__)


class UnraidCPUTemperatureSensor(UnraidTestSensor):
    """CPU temperature sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_cpu_temperature"
        self._attr_name = "CPU Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> Optional[float]:
        """Return the CPU temperature."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None
        
        system_stats = self.coordinator.data.get("system_stats", {})
        
        # Check for temperatures in the new format
        temperatures = system_stats.get("temperatures", {})
        
        # First check for Intel CPU (coretemp)
        if "coretemp-isa-0000" in temperatures:
            coretemp = temperatures["coretemp-isa-0000"]
            if "Package id 0" in coretemp and "temp1_input" in coretemp["Package id 0"]:
                return coretemp["Package id 0"]["temp1_input"]
        
        # Then check for AMD CPU (k10temp)
        if "k10temp-pci-00c3" in temperatures:
            k10temp = temperatures["k10temp-pci-00c3"]
            if "Tctl" in k10temp and "temp1_input" in k10temp["Tctl"]:
                return k10temp["Tctl"]["temp1_input"]
        
        return None


class UnraidVersionSensor(UnraidTestSensor):
    """Version sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_version"
        self._attr_name = "Version"
        self._attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> Optional[str]:
        """Return the Unraid version."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None
        
        system_stats = self.coordinator.data.get("system_stats", {})
        return system_stats.get("unraid_version")


class UnraidUptimeSensor(UnraidTestSensor):
    """Uptime sensor for Unraid - test compatibility."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "unraid_uptime"
        self._attr_name = "Uptime"
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> Optional[str]:
        """Return the uptime as a formatted string."""
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return None
        
        system_stats = self.coordinator.data.get("system_stats", {})
        uptime_seconds = system_stats.get("uptime")
        
        if uptime_seconds is None:
            return None
        
        # Convert seconds to a human-readable format
        uptime = timedelta(seconds=uptime_seconds)
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        # Format the string
        parts = []
        if days > 0:
            parts.append(f"{days} {'day' if days == 1 else 'days'}")
        if hours > 0:
            parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
        if minutes > 0:
            parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
        
        return ", ".join(parts) if parts else "0 minutes"
