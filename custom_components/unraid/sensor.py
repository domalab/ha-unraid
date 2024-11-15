"""Sensor platform for Unraid."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.unit_conversion import (
    PowerConverter,
    EnergyConverter,
)
import logging
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN, UPS_METRICS
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
    
    # Add UPS power sensors if UPS is connected
    if coordinator.has_ups:
        sensors.extend([
            UnraidUPSPowerSensor(coordinator, "current_power"),
            UnraidUPSPowerSensor(coordinator, "energy_consumption"),
            UnraidUPSPowerSensor(coordinator, "load_percentage"),
        ])

    # Add individual disk sensors
    for disk in coordinator.data["system_stats"].get("individual_disks", []):
        if disk["name"].startswith("disk") or disk["name"] == "cache":
            sensors.append(UnraidIndividualDiskSensor(coordinator, disk["name"]))

    # Add network sensors for active interfaces
    if "network_stats" in coordinator.data.get("system_stats", {}):
        network_stats = coordinator.data["system_stats"]["network_stats"]
        for interface, stats in network_stats.items():
            if stats.get("connected", False):
                sensors.extend([
                    UnraidNetworkSensor(coordinator, interface, "inbound"),
                    UnraidNetworkSensor(coordinator, interface, "outbound")
                ])
    
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
        pretty_name = "Cache" if disk_name == "cache" else f"Disk {disk_name.replace('disk', '')}"
        super().__init__(
            coordinator,
            f"disk_{disk_name}_usage",
            f"{pretty_name} Usage",
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

class UnraidUPSPowerSensor(UnraidSensorBase):
    """Enhanced representation of Unraid UPS Power sensor."""

    @staticmethod
    def _get_device_class(sensor_type: str) -> SensorDeviceClass | None:
        """Get the device class based on sensor type."""
        return {
            "current_power": SensorDeviceClass.POWER,
            "energy_consumption": SensorDeviceClass.ENERGY,
            "load_percentage": SensorDeviceClass.POWER_FACTOR,
            "apparent_power": SensorDeviceClass.APPARENT_POWER,
        }.get(sensor_type)

    @staticmethod
    def _get_state_class(sensor_type: str) -> SensorStateClass | None:
        """Get the state class based on sensor type."""
        return {
            "current_power": SensorStateClass.MEASUREMENT,
            "energy_consumption": SensorStateClass.TOTAL_INCREASING,
            "load_percentage": SensorStateClass.MEASUREMENT,
            "apparent_power": SensorStateClass.MEASUREMENT,
        }.get(sensor_type)

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, sensor_type: str) -> None:
        """Initialize the UPS Power sensor."""
        super().__init__(
            coordinator,
            f"ups_power_{sensor_type}",
            f"UPS {sensor_type.replace('_', ' ').title()}",
            "mdi:flash",
            device_class=self._get_device_class(sensor_type),
            state_class=self._get_state_class(sensor_type),
        )
        self._sensor_type = sensor_type
        self._attr_entity_registry_enabled_default = True
        self._last_reset: datetime | None = None
        self._last_value: float | None = None
        self._last_calculation_time: datetime | None = None
        self._accumulated_energy: float = 0.0
        self._error_count = 0
        self._suggested_display_precision = 2

    def _validate_value(self, value: str | None, metric: str) -> float | None:
        """Validate and convert UPS value."""
        if value is None:
            return None

        try:
            # Strip any unit suffixes and convert to float
            numeric_value = float(''.join(c for c in value if c.isdigit() or c in '.-'))
            
            # Check against defined ranges
            if metric in UPS_METRICS:
                if (numeric_value < UPS_METRICS[metric]["min"] or 
                    numeric_value > UPS_METRICS[metric]["max"]):
                    _LOGGER.warning(
                        "Value %f for metric %s outside expected range [%f, %f]",
                        numeric_value,
                        metric,
                        UPS_METRICS[metric]["min"],
                        UPS_METRICS[metric]["max"]
                    )
                    return None
            
            return numeric_value
        except ValueError as err:
            self._error_count += 1
            if self._error_count <= 3:  # Limit log spam
                _LOGGER.error(
                    "Error converting UPS value '%s' for metric '%s': %s",
                    value,
                    metric,
                    err
                )
            return None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor with enhanced error checking."""
        ups_info = self.coordinator.data["system_stats"].get("ups_info", {})
        
        try:
            if self._sensor_type == "current_power":
                # Calculate current power from nominal power and load percentage
                nominal_power = self._validate_value(ups_info.get("NOMPOWER"), "NOMPOWER")
                load_percent = self._validate_value(ups_info.get("LOADPCT"), "LOADPCT")
                
                if nominal_power is None or load_percent is None:
                    return None
                    
                return round((nominal_power * load_percent) / 100.0, 2)
                
            elif self._sensor_type == "energy_consumption":
                # Get current power consumption
                nominal_power = self._validate_value(ups_info.get("NOMPOWER"), "NOMPOWER")
                load_percent = self._validate_value(ups_info.get("LOADPCT"), "LOADPCT")
                
                if nominal_power is None or load_percent is None:
                    return self._accumulated_energy
                
                current_power = (nominal_power * load_percent) / 100.0
                current_time = datetime.now(timezone.utc)
                
                # Initialize last calculation time if not set
                if self._last_calculation_time is None:
                    self._last_calculation_time = current_time
                    return self._accumulated_energy
                
                # Calculate time difference in hours
                time_diff = (current_time - self._last_calculation_time).total_seconds() / 3600
                
                # Calculate energy consumed since last update (power * time in hours = energy in kWh)
                energy_increment = (current_power * time_diff) / 1000
                
                self._accumulated_energy += energy_increment
                self._last_calculation_time = current_time
                
                _LOGGER.debug(
                    "Energy calculation - Power: %.2fW, Time diff: %.4fh, Increment: %.4fkWh, Total: %.4fkWh",
                    current_power,
                    time_diff,
                    energy_increment,
                    self._accumulated_energy
                )
                
                return round(self._accumulated_energy, 3)
                
            elif self._sensor_type == "load_percentage":
                return self._validate_value(ups_info.get("LOADPCT"), "LOADPCT")
                
        except Exception as err:
            self._error_count += 1
            if self._error_count <= 3:
                _LOGGER.error("Error calculating %s: %s", self._sensor_type, err)
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return {
            "current_power": "W",
            "energy_consumption": "kWh",
            "load_percentage": "%",
            "apparent_power": "VA",
        }.get(self._sensor_type)

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset."""
        if self._sensor_type == "energy_consumption":
            return self._last_reset
        return None

    def _reset_energy_counter(self) -> None:
        """Reset the energy counter."""
        self._accumulated_energy = 0.0
        self._last_reset = datetime.now(timezone.utc)
        self._last_calculation_time = None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes with validated values."""
        ups_info = self.coordinator.data["system_stats"].get("ups_info", {})
        attributes = {}
        
        # Add base attributes with validation
        base_metrics = {
            "nominal_power": ("NOMPOWER", "W"),
            "line_voltage": ("LINEV", "V"),
            "last_transfer_reason": ("LASTXFER", None),
        }
        
        for attr_name, (metric, unit) in base_metrics.items():
            value = ups_info.get(metric)
            if unit:
                validated_value = self._validate_value(value, metric)
                if validated_value is not None:
                    attributes[attr_name] = f"{validated_value}{unit}"
            else:
                attributes[attr_name] = value if value else "Unknown"

        # Add sensor-specific attributes
        if self._sensor_type == "current_power":
            power_factor = self._validate_value(ups_info.get("POWERFACTOR"), "POWERFACTOR")
            apparent_power = self._validate_value(ups_info.get("LOADAPNT"), "LOADAPNT")
            
            if power_factor is not None:
                attributes["power_factor"] = power_factor
            if apparent_power is not None:
                attributes["apparent_power"] = f"{apparent_power}VA"

        # Add error tracking
        if self._error_count > 0:
            attributes["error_count"] = self._error_count

        return attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reset error count on successful update."""
        super()._handle_coordinator_update()
        if self.coordinator.last_update_success:
            self._error_count = 0

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

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Parse temperature value from string."""
        try:
            # Remove common temperature markers and convert to float
            cleaned = value.replace('°C', '').replace(' C', '').replace('+', '').strip()
            temp = float(cleaned)
            # Filter out obviously invalid readings
            if -50 <= temp <= 150:  # Reasonable temperature range
                return temp
        except (ValueError, TypeError):
            pass
        return None

    def _get_core_temps(self, sensors_data: dict) -> list[float]:
        """Get all valid core temperatures."""
        core_temps = []
        for sensor_data in sensors_data.values():
            # Check for various CPU temperature patterns
            for key, value in sensor_data.items():
                if isinstance(value, (str, float)):
                    # Common CPU temperature patterns
                    if any(pattern in key.lower() for pattern in [
                        'core', 'cpu temp', 'processor',
                        'package', 'tdie', 'tccd'
                    ]):
                        if temp := self._parse_temperature(str(value)):
                            core_temps.append(temp)
        return core_temps

    @property
    def native_value(self) -> Optional[float]:
        """Return the current CPU temperature."""
        try:
            temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})
            
            # Get all valid core temperatures
            core_temps = self._get_core_temps(sensors_data)
            
            if core_temps:
                # Return average temperature if we have multiple cores
                return round(sum(core_temps) / len(core_temps), 1)
            
            # Fallback: Look for other CPU temperature indicators
            for sensor_data in sensors_data.values():
                for key, value in sensor_data.items():
                    # Look for generic CPU temperature entries
                    if 'CPU' in key and 'Temp' in key:
                        if temp := self._parse_temperature(str(value)):
                            return temp

            return None

        except Exception as err:
            _LOGGER.debug("Error getting CPU temperature: %s", err)
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

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Parse temperature value from string."""
        try:
            cleaned = value.replace('°C', '').replace(' C', '').replace('+', '').strip()
            temp = float(cleaned)
            if -50 <= temp <= 150:  # Reasonable temperature range
                return temp
        except (ValueError, TypeError):
            pass
        return None

    @property
    def native_value(self) -> Optional[float]:
        """Return the current motherboard temperature."""
        try:
            temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            # Common motherboard temperature patterns
            mb_patterns = [
                'mb temp', 'board temp', 'system temp',
                'motherboard', 'systin', 'temp1'
            ]

            for sensor_data in sensors_data.values():
                for key, value in sensor_data.items():
                    if isinstance(value, (str, float)):
                        if any(pattern in key.lower() for pattern in mb_patterns):
                            if temp := self._parse_temperature(str(value)):
                                return temp

            return None

        except Exception as err:
            _LOGGER.debug("Error getting motherboard temperature: %s", err)
            return None

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS
    
class UnraidNetworkSensor(UnraidSensorBase):
    """Representation of Unraid network traffic sensor."""

    def __init__(
        self, 
        coordinator: UnraidDataUpdateCoordinator,
        interface: str,
        direction: str
    ) -> None:
        """Initialize the network sensor."""
        # Format name like "eth0 Inbound" or "eth0 Outbound"
        pretty_name = f"Network {interface} {direction.capitalize()}"
        
        super().__init__(
            coordinator,
            f"network_{interface}_{direction}",
            pretty_name,
            icon="mdi:arrow-down" if direction == "inbound" else "mdi:arrow-up",
            device_class=SensorDeviceClass.DATA_RATE,
            state_class=SensorStateClass.MEASUREMENT,
        )
        self._interface = interface
        self._direction = direction
        self._attr_suggested_display_precision = 2

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        network_stats = self.coordinator.data.get("system_stats", {}).get("network_stats", {})
        return (super().available and 
                self._interface in network_stats and
                network_stats[self._interface].get("connected", False))

    @property
    def native_value(self) -> float:
        """Return the current network speed."""
        try:
            stats = self.coordinator.data.get("system_stats", {}).get("network_stats", {}).get(self._interface, {})
            speed_key = "rx_speed" if self._direction == "inbound" else "tx_speed"
            current_speed = stats.get(speed_key, 0)
            
            # Convert bytes/s to bits/s
            bits_per_second = current_speed * 8
            return round(bits_per_second, 2)
        except Exception as err:
            _LOGGER.error("Error calculating network speed: %s", err)
            return 0

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        value = self.native_value
        if value >= 1000000000:  # Gbps
            return "Gbit/s"
        if value >= 1000000:  # Mbps
            return "Mbit/s"
        if value >= 1000:  # Kbps
            return "kbit/s"
        return "bit/s"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional sensor state attributes."""
        try:
            stats = self.coordinator.data.get("system_stats", {}).get("network_stats", {}).get(self._interface, {})
            
            return {
                "interface_info": stats.get("interface_info", "Unknown"),
                "bytes_per_second": stats.get("rx_speed" if self._direction == "inbound" else "tx_speed", 0),
                "total_bytes": stats.get("rx_bytes" if self._direction == "inbound" else "tx_bytes", 0),
            }
            
        except Exception as err:
            _LOGGER.warning(
                "Error getting attributes for network sensor %s: %s",
                self._interface,
                err
            )
            return {}

    def _scale_value(self) -> tuple[float, str]:
        """Scale the value to the appropriate unit."""
        value = self.native_value
        if value >= 1000000000:  # Gbps
            return (round(value / 1000000000, 2), "Gbit/s")
        if value >= 1000000:  # Mbps
            return (round(value / 1000000, 2), "Mbit/s")
        if value >= 1000:  # Kbps
            return (round(value / 1000, 2), "kbit/s")
        return (round(value, 2), "bit/s")