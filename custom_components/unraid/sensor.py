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
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_conversion import (
    PowerConverter,
    EnergyConverter,
)
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from homeassistant.util import dt as dt_util
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPower,
    UnitOfFrequency,
    PERCENTAGE,
)

from .const import DOMAIN, UPS_METRICS
from .coordinator import UnraidDataUpdateCoordinator
from .helpers import get_pool_info, format_bytes

_LOGGER = logging.getLogger(__name__)

UNIT_WATTS = UnitOfPower.WATT
UNIT_HERTZ = UnitOfFrequency.HERTZ
UNIT_CELSIUS = UnitOfTemperature.CELSIUS

def format_size(size_in_bytes: Optional[int]) -> str:
    """Format size to appropriate unit with None handling."""
    if size_in_bytes is None:
        return "0 B"
        
    try:
        size = float(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    except (TypeError, ValueError):
        return "0 B"

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""
    value_fn: Callable[[dict[str, Any]], Any] = field(default=lambda x: None)

class UnraidSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Unraid sensors."""

    entity_description: UnraidSensorEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidSensorEntityDescription,
    ) -> None:
        """Initialize the sensor.
        
        Args:
            coordinator: The data update coordinator
            description: Entity description containing key and name
        """
        super().__init__(coordinator)
        self.entity_description = description
        
        hostname = coordinator.hostname.capitalize()
        
        # Clean the key of any existing hostname instances
        clean_key = description.key
        hostname_variations = [hostname.lower(), hostname.capitalize(), hostname.upper()]
        
        for variation in hostname_variations:
            clean_key = clean_key.replace(f"{variation}_", "")
        
        # Validate the cleaned key
        if not clean_key:
            _LOGGER.error("Invalid empty key after cleaning hostname")
            clean_key = description.key
        
        # Construct unique_id with guaranteed single hostname instance
        self._attr_unique_id = f"unraid_server_{hostname}_{clean_key}"
        
        # Keep the name simple and human-readable
        self._attr_name = f"{hostname} {description.name}"
        
        # Consistent device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"Unraid Server ({hostname})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except Exception as err:
            _LOGGER.debug(
                "Error getting state for %s: %s",
                self.entity_description.key,
                err
            )
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create sensors
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

    # Add pool sensors
    pool_info = get_pool_info(coordinator.data.get("system_stats", {}))
    for pool_name in pool_info:
        sensors.append(UnraidPoolSensor(coordinator, pool_name))

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
    
class UnraidCPUUsageSensor(UnraidSensorBase):
    """Representation of Unraid CPU usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="cpu_usage",
                name="CPU Usage",
                icon="mdi:cpu-64-bit",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: data["system_stats"].get("cpu_usage")
            ),
        )

class UnraidRAMUsageSensor(UnraidSensorBase):
    """Representation of Unraid RAM usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="ram_usage",
                name="RAM Usage",
                icon="mdi:memory",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: round(data["system_stats"].get("memory_usage", {}).get("percentage", 0), 1)
            ),
        )

class UnraidArrayUsageSensor(UnraidSensorBase):
    """Representation of Unraid Array usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="array_usage",
                name="Array Usage",
                icon="mdi:harddisk",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: round(data["system_stats"].get("array_usage", {}).get("percentage", 0), 1)
            ),
        )
        self._attr_suggested_display_precision = 1

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        array_usage = self.coordinator.data["system_stats"].get("array_usage", {})
        return {
            "total_size": format_bytes(array_usage.get("total", 0)),
            "used_space": format_bytes(array_usage.get("used", 0)),
            "free_space": format_bytes(array_usage.get("free", 0)),
        }

class UnraidPoolSensor(UnraidSensorBase):
    """Representation of an Unraid storage pool sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, pool_name: str) -> None:
        pretty_name = pool_name.title().replace('_', ' ')
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"pool_{pool_name}_usage",
                name=f"{pretty_name} Pool Usage",
                icon="mdi:folder-multiple",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: round(
                    get_pool_info(data.get("system_stats", {}))
                    .get(pool_name, {})
                    .get("usage_percent", 0), 1
                )
            ),
        )
        self._pool_name = pool_name
        self._attr_suggested_display_precision = 1

    @property
    def icon(self) -> str:
        """Return the icon based on pool type."""
        if "cache" in self._pool_name.lower():
            return "mdi:flash"
        elif "nvme" in self._pool_name.lower():
            return "mdi:solid-state-drive"
        return "mdi:folder-multiple"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional pool attributes."""
        pool_info = get_pool_info(self.coordinator.data.get("system_stats", {}))
        if self._pool_name not in pool_info:
            return {}

        info = pool_info[self._pool_name]
        attrs = {
            "filesystem": info["filesystem"],
            "total_size": format_bytes(info["total_size"]),
            "used_space": format_bytes(info["used_size"]),
            "free_space": format_bytes(info["free_size"]),
            "mount_point": info["mount_point"],
            "usage_percentage": f"{info['usage_percent']:.1f}%",
        }

        # Add device information
        for i, device in enumerate(info["devices"], 1):
            attrs[f"device_{i}"] = device

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        pool_info = get_pool_info(self.coordinator.data.get("system_stats", {}))
        return self._pool_name in pool_info

class UnraidIndividualDiskSensor(UnraidSensorBase):
    """Representation of an individual Unraid disk usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, disk_name: str) -> None:
        pretty_name = "Cache" if disk_name == "cache" else f"Disk {disk_name.replace('disk', '')}"
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"disk_{disk_name}_usage",
                name=f"{pretty_name} Usage",
                icon="mdi:harddisk",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: next(
                    (disk["percentage"] for disk in data["system_stats"].get("individual_disks", [])
                    if disk["name"] == disk_name),
                    None
                )
            ),
        )
        self._disk_name = disk_name
        self._attr_suggested_display_precision = 1
        self._device = self._get_disk_device()

    def _get_disk_device(self) -> Optional[str]:
        """Get the device name from the current disk mapping."""
        disk_mapping = self.coordinator.data.get("system_stats", {}).get("disk_mapping", {})
        return disk_mapping.get(self._disk_name)

    @property
    def extra_state_attributes(self) -> Dict[str, str]:
        """Return the state attributes."""
        for disk in self.coordinator.data["system_stats"].get("individual_disks", []):
            if disk["name"] == self._disk_name:
                self._device = self._get_disk_device()
                
                attrs = {
                    "total_size": format_size(disk["total"]),
                    "used_space": format_size(disk["used"]),
                    "free_space": format_size(disk["free"]),
                    "mount_point": disk["mount_point"],
                    "current_usage": f"{disk['percentage']}%"
                }

                if self._device:
                    attrs["device"] = self._device
                
                disk_info = self.coordinator.data["system_stats"].get("disk_info", {})
                if self._device in disk_info:
                    info = disk_info[self._device]
                    attrs.update({
                        "model": info.get("model", "Unknown"),
                        "status": info.get("status", "Unknown"),
                        "health": info.get("health", "Unknown"),
                    })
                    if "temperature" in info:
                        attrs["temperature"] = f"{info['temperature']}°C"

                return attrs
        return {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return any(
            disk["name"] == self._disk_name 
            for disk in self.coordinator.data["system_stats"].get("individual_disks", [])
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update device mapping on each update
        self._device = self._get_disk_device()
        super()._handle_coordinator_update()

class UnraidLogFilesystemSensor(UnraidSensorBase):
    """Representation of Unraid Log Filesystem usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="log_filesystem",
                name="Log Filesystem Usage",
                icon="mdi:file-document",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: data["system_stats"].get("log_filesystem", {}).get("percentage")
            ),
        )

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
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="docker_vdisk",
                name="Docker vDisk Usage",
                icon="mdi:docker",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: data["system_stats"].get("docker_vdisk", {}).get("percentage")
            ),
        )

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
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="cache_usage",
                name="Cache Usage",
                icon="mdi:flash",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: round(data["system_stats"].get("cache_usage", {}).get("percentage", 0), 1)
            ),
        )

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
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="boot_usage",
                name="Boot Usage",
                icon="mdi:usb-flash-drive",
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="%",
                value_fn=lambda data: data["system_stats"].get("boot_usage", {}).get("percentage")
            ),
        )

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
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="uptime",
                name="Uptime",
                icon="mdi:clock-outline",
                value_fn=lambda data: self._format_uptime(data["system_stats"].get("uptime", 0))
            ),
        )

    def _format_uptime(self, seconds: float) -> str:
        days, remainder = divmod(int(seconds), 86400)
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

class UnraidCPUTemperatureSensor(UnraidSensorBase):
    """Representation of Unraid CPU temperature sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="cpu_temperature",
                name="CPU Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                value_fn=lambda data: self._get_temperature(data)
            ),
        )

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get CPU temperature from data."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
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

class UnraidMotherboardTemperatureSensor(UnraidSensorBase):
    """Representation of Unraid motherboard temperature sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="motherboard_temperature",
                name="Motherboard Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                value_fn=lambda data: self._get_temperature(data)
            ),
        )

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get motherboard temperature from data."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            # Common motherboard temperature patterns in priority order
            mb_patterns = [
                'mb temp', 'board temp', 'system temp',
                'motherboard', 'systin', 'temp1'
            ]

            # Iterate through each pattern in the specified order
            for pattern in mb_patterns:
                pattern_lower = pattern.lower()
                for sensor_data in sensors_data.values():
                    for key, value in sensor_data.items():
                        if isinstance(value, (str, float)) and pattern_lower in key.lower():
                            temp = self._parse_temperature(str(value))
                            if temp is not None:
                                    return temp
            return None
        except Exception as err:
            _LOGGER.debug("Error getting motherboard temperature: %s", err)
            return None

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

class UnraidNetworkSensor(UnraidSensorBase):
    def __init__(self, coordinator: UnraidDataUpdateCoordinator, interface: str, direction: str) -> None:
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"network_{interface}_{direction}",
                name=f"Network {interface} {direction.capitalize()}",
                icon="mdi:arrow-down" if direction == "inbound" else "mdi:arrow-up",
                device_class=SensorDeviceClass.DATA_RATE,
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda data: self._get_speed(data)
            ),
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
                "interface_info": stats.get("interface_info", "Unknown")
            }
            
        except Exception as err:
            _LOGGER.warning(
                "Error getting attributes for network sensor %s: %s",
                self._interface,
                err
            )
            return {}
        
    def _get_speed(self, data: dict) -> float:
        """Calculate network speed."""
        try:
            stats = data.get("system_stats", {}).get("network_stats", {}).get(self._interface, {})
            speed_key = "rx_speed" if self._direction == "inbound" else "tx_speed"
            current_speed = stats.get(speed_key, 0)
            return round(current_speed * 8, 2)  # Convert to bits/s
        except Exception as err:
            _LOGGER.error("Error calculating network speed: %s", err)
            return 0

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
    
class UnraidUPSPowerSensor(UnraidSensorBase):
    """Representation of Unraid UPS Power sensor.
    
    Supports power and energy monitoring for UPS devices with or without NOMPOWER reporting.
    Power can be derived from model numbers when NOMPOWER isn't available.
    
    Attributes:
        POWER_FACTOR_ESTIMATE: Conservative estimate for VA to W conversion
        MODEL_PATTERNS: Dictionary mapping UPS model patterns to their power factors
    """

    POWER_FACTOR_ESTIMATE = 0.9  # Conservative estimate for VA to W conversion
    
    # Known UPS model patterns for power calculation
    MODEL_PATTERNS = {
        r'smart-ups.*?(\d{3,4})': 1.0,       # Smart-UPS models use direct VA rating
        r'back-ups.*?(\d{3,4})': 0.9,        # Back-UPS models typically 90% of VA
        r'back-ups pro.*?(\d{3,4})': 0.95,   # Back-UPS Pro models ~95% of VA
        r'smart-ups\s*x.*?(\d{3,4})': 1.0,   # Smart-UPS X series
        r'smart-ups\s*xl.*?(\d{3,4})': 1.0,  # Smart-UPS XL series
        r'smart-ups\s*rt.*?(\d{3,4})': 1.0,  # Smart-UPS RT series
        r'symmetra.*?(\d{3,4})': 1.0,        # Symmetra models
        r'sua\d{3,4}': 1.0,                  # Smart-UPS alternative model format
        r'smx\d{3,4}': 1.0,                  # Smart-UPS SMX model format
        r'smt\d{3,4}': 1.0,                  # Smart-UPS SMT model format
    }

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, sensor_type: str) -> None:
        """Initialize the UPS Power sensor."""
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"ups_power_{sensor_type}",
                name=f"UPS {sensor_type.replace('_', ' ').title()}",
                icon="mdi:flash",
                device_class=self._get_device_class(sensor_type),
                state_class=self._get_state_class(sensor_type),
                native_unit_of_measurement=self._get_unit_measurement(sensor_type),
                value_fn=lambda data: self._compute_value(data)
            ),
        )
        self._sensor_type = sensor_type
        self._attr_entity_registry_enabled_default = True
        self._last_reset: datetime | None = None
        self._last_value: float | None = None
        self._last_calculation_time: datetime | None = None
        self._accumulated_energy: float = 0.0
        self._error_count = 0
        self._last_power_value: float | None = None
        self._suggested_display_precision = 2
        self._power_source: str = "direct"

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

    @staticmethod
    def _get_unit_measurement(sensor_type: str) -> str | None:
        """Return the unit of measurement."""
        return {
            "current_power": "W",
            "energy_consumption": "kWh",
            "load_percentage": "%",
            "apparent_power": "VA",
        }.get(sensor_type)
    
    def _validate_derived_power(self, va_rating: int, factor: float) -> float | None:
        """Validate derived power values.
        
        Args:
            va_rating: VA rating from UPS model number
            factor: Power factor to convert VA to Watts
            
        Returns:
            float: Validated power value in Watts
            None: If validation fails
        """
        try:
            power = va_rating * factor
            if 0 < power <= 10000:  # Reasonable range for UPS power
                return power
            _LOGGER.warning("Derived power %sW outside reasonable range", power)
            return None
        except Exception as err:
            _LOGGER.error("Error validating derived power: %s", err)
            return None
    
    def _get_nominal_power(self, ups_info: dict) -> float | None:
        """Get nominal power either directly or derived from model."""
        try:
            # First try direct NOMPOWER
            if "NOMPOWER" in ups_info:
                nominal_power = self._validate_value(ups_info.get("NOMPOWER"), "NOMPOWER")
                if nominal_power is not None:
                    self._last_power_value = nominal_power
                    self._power_source = "direct"
                    return nominal_power

            # Try to derive from model if no NOMPOWER
            model = ups_info.get("MODEL", "").strip().lower()
            if not model:
                return self._last_power_value  # Return last known value if available

            # Try each model pattern
            import re
            for pattern, factor in self.MODEL_PATTERNS.items():
                if match := re.search(pattern, model):
                    va_rating = int(match.group(1))
                    nominal_power = self._validate_derived_power(va_rating, factor)
                    if nominal_power:
                        _LOGGER.debug(
                            "Derived power for model %s: %sVA * %s = %sW",
                            model,
                            va_rating,
                            factor,
                            nominal_power
                        )
                        self._last_power_value = nominal_power
                        self._power_source = "derived"
                        return nominal_power

            # If we have a last known value, use it
            if self._last_power_value is not None:
                return self._last_power_value

            _LOGGER.warning("Could not determine power rating for UPS model: %s", model)
            return None

        except Exception as err:
            _LOGGER.error("Error calculating nominal power: %s", err)
            return self._last_power_value

    def _compute_value(self, data: dict) -> float | None:
        """Calculate the sensor value based on type."""
        ups_info = data["system_stats"].get("ups_info", {})
        
        try:
            if self._sensor_type == "current_power":
                nominal_power = self._get_nominal_power(ups_info)
                load_percent = self._validate_value(ups_info.get("LOADPCT"), "LOADPCT")
                
                if nominal_power is None or load_percent is None:
                    return None
                    
                return round((nominal_power * load_percent) / 100.0, 2)
                
            elif self._sensor_type == "energy_consumption":
                nominal_power = self._get_nominal_power(ups_info)
                load_percent = self._validate_value(ups_info.get("LOADPCT"), "LOADPCT")
                
                if nominal_power is None or load_percent is None:
                    return self._accumulated_energy
                
                current_power = (nominal_power * load_percent) / 100.0
                current_time = datetime.now(timezone.utc)
                
                if self._last_calculation_time is None:
                    self._last_calculation_time = current_time
                    return self._accumulated_energy
                
                time_diff = (current_time - self._last_calculation_time).total_seconds() / 3600
                if time_diff > 24:  # Detect large gaps (e.g., HA restart)
                    _LOGGER.warning("Large time gap detected (%s hours), resetting energy calculation", time_diff)
                    self._reset_energy_counter()
                    return 0.0
                
                energy_increment = (current_power * time_diff) / 1000
                self._accumulated_energy += energy_increment
                self._last_calculation_time = current_time
                
                _LOGGER.debug(
                    "Energy calculation - Power: %.2fW, Time: %.4fh, Increment: %.4fkWh, Total: %.4fkWh",
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
            "battery_voltage": ("BATTV", "V"),
            "battery_charge": ("BCHARGE", "%"),
            "time_on_battery": ("TONBATT", "seconds"),
            "temperature": ("ITEMP", "°C"),
        }
        
        for attr_name, (metric, unit) in base_metrics.items():
            value = ups_info.get(metric)
            if unit:
                validated_value = self._validate_value(value, metric)
                if validated_value is not None:
                    attributes[attr_name] = f"{validated_value}{unit}"
            else:
                attributes[attr_name] = value if value else "Unknown"
        
        # Add model information and power derivation method
        model = ups_info.get("MODEL")
        if model:
            attributes["ups_model"] = model
            if self._power_source == "derived":
                nominal_power = self._get_nominal_power(ups_info)
                if nominal_power:
                    attributes["derived_power"] = f"{nominal_power}W"
                    attributes["power_derivation"] = "Calculated from model rating"
        
        if self._sensor_type == "current_power":
            power_factor = self._validate_value(ups_info.get("POWERFACTOR"), "POWERFACTOR")
            apparent_power = self._validate_value(ups_info.get("LOADAPNT"), "LOADAPNT")
            
            if power_factor is not None:
                attributes["power_factor"] = power_factor
            if apparent_power is not None:
                attributes["apparent_power"] = f"{apparent_power}VA"

            attributes["power_source"] = self._power_source
            
        elif self._sensor_type == "energy_consumption":
            attributes["last_reset"] = self._last_reset.isoformat() if self._last_reset else "Never"
            if time_diff := self._get_time_since_last_calculation():
                attributes["calculation_age"] = f"{time_diff:.1f}h"

        if self._error_count > 0:
            attributes["error_count"] = self._error_count

        return attributes
    
    def _get_time_since_last_calculation(self) -> float | None:
        """Get time since last energy calculation in hours."""
        if self._last_calculation_time:
            return (datetime.now(timezone.utc) - self._last_calculation_time).total_seconds() / 3600
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reset error count on successful update."""
        super()._handle_coordinator_update()
        if self.coordinator.last_update_success:
            self._error_count = 0