"""Sensor platform for Unraid."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import logging
from typing import Any, Dict, List, Optional

from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

def format_size(size_in_bytes: float) -> str:
    """Format size to appropriate unit."""
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']
    size = float(size_in_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: List[SensorEntity] = [
        UnraidCPUUsageSensor(coordinator),
        UnraidRAMUsageSensor(coordinator),
        UnraidArrayUsageSensor(coordinator),
        UnraidCacheUsageSensor(coordinator),
        UnraidBootUsageSensor(coordinator),
        UnraidUptimeSensor(coordinator),
        UnraidCPUTemperatureSensor(coordinator),
        UnraidMotherboardTemperatureSensor(coordinator),
        UnraidLogFilesystemSensor(coordinator),
        UnraidDockerVDiskSensor(coordinator),
    ]
    
    # Add UPS sensor only if UPS is connected
    if coordinator.has_ups:
        sensors.append(UnraidUPSSensor(coordinator))

    # Add individual disk sensors
    for disk in coordinator.data["system_stats"].get("individual_disks", []):
        if disk["name"].startswith("disk") or disk["name"] == "cache":
            sensors.append(UnraidIndividualDiskSensor(coordinator, disk["name"]))
    
    async_add_entities(sensors)

class UnraidSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Unraid sensors."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Unraid {name}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information about this Unraid server."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": f"Unraid Server ({self.coordinator.config_entry.data['host']})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.coordinator.data["system_stats"].get(self._key)
    
class UnraidCPUUsageSensor(UnraidSensorBase):
    """Representation of Unraid CPU usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the CPU usage sensor."""
        super().__init__(
            coordinator,
            "cpu_usage",
            "CPU Usage",
            "mdi:cpu-64-bit",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current CPU usage."""
        return self.coordinator.data["system_stats"].get("cpu_usage")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

class UnraidRAMUsageSensor(UnraidSensorBase):
    """Representation of Unraid RAM usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the RAM usage sensor."""
        super().__init__(
            coordinator,
            "memory_usage",
            "RAM Usage",
            "mdi:memory",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current RAM usage percentage."""
        percentage = self.coordinator.data["system_stats"].get("memory_usage", {}).get("percentage")
        if percentage is not None:
            return round(percentage, 1)  # Round to one decimal place
        return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

class UnraidArrayUsageSensor(UnraidSensorBase):
    """Representation of Unraid Array usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Array usage sensor."""
        super().__init__(
            coordinator,
            "array_usage",
            "Array Usage",
            "mdi:harddisk",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current Array usage percentage."""
        percentage = self.coordinator.data["system_stats"].get("array_usage", {}).get("percentage")
        return round(percentage, 1) if percentage is not None else None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        array_usage = self.coordinator.data["system_stats"].get("array_usage", {})
        return {
            "total_size": format_size(array_usage.get("total", 0)),
            "used_space": format_size(array_usage.get("used", 0)),
            "free_space": format_size(array_usage.get("free", 0)),
        }
    
class UnraidIndividualDiskSensor(UnraidSensorBase):
    """Representation of an individual Unraid disk usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, disk_name: str) -> None:
        """Initialize the individual disk sensor."""
        super().__init__(
            coordinator,
            f"disk_{disk_name}_usage",
            f"Disk {disk_name} Usage",
            "mdi:harddisk",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )
        self._disk_name = disk_name

    @property
    def native_value(self) -> Optional[float]:
        """Return the current disk usage percentage."""
        for disk in self.coordinator.data["system_stats"].get("individual_disks", []):
            if disk["name"] == self._disk_name:
                return disk["percentage"]
        return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        attributes = {}
        for disk in self.coordinator.data["system_stats"].get("individual_disks", []):
            if disk["name"] == self._disk_name:
                attributes = {
                    "total_size": format_size(disk["total"]),
                    "used_space": format_size(disk["used"]),
                    "free_space": format_size(disk["free"]),
                    "mount_point": disk["mount_point"],
                }
                break
        
        return attributes

class UnraidLogFilesystemSensor(UnraidSensorBase):
    """Representation of Unraid Log Filesystem usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Log Filesystem usage sensor."""
        super().__init__(
            coordinator,
            "log_filesystem",
            "Log Filesystem Usage",
            "mdi:file-document",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current Log Filesystem usage percentage."""
        log_fs = self.coordinator.data["system_stats"].get("log_filesystem", {})
        return log_fs.get("percentage")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        log_fs = self.coordinator.data["system_stats"].get("log_filesystem", {})
        return {
            "total_size": format_size(log_fs.get("total", 0)),
            "used_space": format_size(log_fs.get("used", 0)),
            "free_space": format_size(log_fs.get("free", 0)),
        }

class UnraidDockerVDiskSensor(UnraidSensorBase):
    """Representation of Unraid Docker vDisk usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Docker vDisk usage sensor."""
        super().__init__(
            coordinator,
            "docker_vdisk",
            "Docker vDisk Usage",
            "mdi:docker",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current Docker vDisk usage percentage."""
        docker_vdisk = self.coordinator.data["system_stats"].get("docker_vdisk", {})
        return docker_vdisk.get("percentage")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        docker_vdisk = self.coordinator.data["system_stats"].get("docker_vdisk", {})
        return {
            "total_size": format_size(docker_vdisk.get("total", 0)),
            "used_space": format_size(docker_vdisk.get("used", 0)),
            "free_space": format_size(docker_vdisk.get("free", 0)),
        }
    
class UnraidCacheUsageSensor(UnraidSensorBase):
    """Representation of Unraid Cache usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Cache usage sensor."""
        super().__init__(
            coordinator,
            "cache_usage",
            "Cache Usage",
            "mdi:harddisk",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current Cache usage percentage."""
        percentage = self.coordinator.data["system_stats"].get("cache_usage", {}).get("percentage")
        return round(percentage, 1) if percentage is not None else None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        cache_usage = self.coordinator.data["system_stats"].get("cache_usage", {})
        return {
            "total_size": format_size(cache_usage.get("total", 0)),
            "used_space": format_size(cache_usage.get("used", 0)),
            "free_space": format_size(cache_usage.get("free", 0)),
        }

class UnraidBootUsageSensor(UnraidSensorBase):
    """Representation of Unraid Boot device usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Boot usage sensor."""
        super().__init__(
            coordinator,
            "boot_usage",
            "Boot Usage",
            "mdi:usb-flash-drive",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current Boot device usage percentage."""
        return self.coordinator.data["system_stats"].get("boot_usage", {}).get("percentage")

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        boot_usage = self.coordinator.data["system_stats"].get("boot_usage", {})
        return {
            "total_size": format_size(boot_usage.get("total", 0)),
            "used_space": format_size(boot_usage.get("used", 0)),
            "free_space": format_size(boot_usage.get("free", 0)),
        }

class UnraidUptimeSensor(UnraidSensorBase):
    """Representation of Unraid Uptime sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the Uptime sensor."""
        super().__init__(
            coordinator,
            "uptime",
            "Uptime",
            "mdi:clock-outline",
        )

    @property
    def native_value(self) -> str:
        """Return the formatted uptime as the main value."""
        uptime_seconds = self.coordinator.data["system_stats"].get("uptime", 0)
        days, remainder = divmod(int(uptime_seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        uptime_seconds = self.coordinator.data["system_stats"].get("uptime", 0)
        days, remainder = divmod(int(uptime_seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "timestamp": dt_util.utcnow() - timedelta(seconds=uptime_seconds)
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and "uptime" in self.coordinator.data["system_stats"]

class UnraidUPSSensor(UnraidSensorBase):
    """Representation of Unraid UPS sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the UPS sensor."""
        super().__init__(
            coordinator,
            "ups_status",
            "UPS Status",
            "mdi:battery-medium",
        )
    
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and "ups_info" in self.coordinator.data
    
    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        ups_info = self.coordinator.data["system_stats"].get("ups_info", {})
        return ups_info.get("STATUS", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        ups_info = self.coordinator.data["system_stats"].get("ups_info", {})
        return {
            "model": ups_info.get("MODEL", "Unknown"),
            "ups_load": ups_info.get("LOADPCT", "Unknown"),
            "battery_charge": ups_info.get("BCHARGE", "Unknown"),
            "runtime_left": ups_info.get("TIMELEFT", "Unknown"),
            "nominal_power": ups_info.get("NOMPOWER", "Unknown"),
            "line_voltage": ups_info.get("LINEV", "Unknown"),
            "battery_voltage": ups_info.get("BATTV", "Unknown"),
        }

class UnraidCPUTemperatureSensor(UnraidSensorBase):
    """Representation of Unraid CPU temperature sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the CPU temperature sensor."""
        super().__init__(
            coordinator,
            "cpu_temperature",
            "CPU Temperature",
            "mdi:thermometer",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current CPU temperature."""
        temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
        sensors_data = temp_data.get("sensors", {})
        for sensor, data in sensors_data.items():
            if "Core 0" in data:
                return float(data["Core 0"].replace('°C', '').replace(' C', '').replace('+', ''))
        return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

class UnraidMotherboardTemperatureSensor(UnraidSensorBase):
    """Representation of Unraid motherboard temperature sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the motherboard temperature sensor."""
        super().__init__(
            coordinator,
            "motherboard_temperature",
            "Motherboard Temperature",
            "mdi:thermometer",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current motherboard temperature."""
        temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
        sensors_data = temp_data.get("sensors", {})
        for sensor, data in sensors_data.items():
            if "MB Temp" in data:
                return float(data["MB Temp"].replace('°C', '').replace(' C', '').replace('+', ''))
        return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS