"""Binary sensors for Unraid."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Any, Callable
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

TEMP_WARNING_THRESHOLD: Final = 80  # Celsius
MEMORY_WARNING_THRESHOLD: Final = 90  # Percent
DISK_WARNING_THRESHOLD: Final = 90  # Percent
FAN_WARNING_THRESHOLD: Final = 200  # RPM

_LOGGER = logging.getLogger(__name__)

def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable sizes."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"

@dataclass
class UnraidBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Unraid binary sensor entity."""

    value_fn: Callable[[dict[str, Any]], bool | None] = field(default=lambda x: None)
    has_warning_threshold: bool = False
    warning_threshold: float | None = None


SENSOR_DESCRIPTIONS: tuple[UnraidBinarySensorEntityDescription, ...] = (
    UnraidBinarySensorEntityDescription(
        key="array_health",
        name="Array Health Status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats", {}).get("array_usage", {}).get("percentage", 0) >= DISK_WARNING_THRESHOLD if data.get("system_stats", {}).get("array_usage") else None,
        has_warning_threshold=True,
        warning_threshold=DISK_WARNING_THRESHOLD,
        icon="mdi:harddisk-plus",
    ),
    UnraidBinarySensorEntityDescription(
        key="ssh_connectivity",
        name="Server Connection Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats") is not None,
        icon="mdi:server-network",
    ),
    UnraidBinarySensorEntityDescription(
        key="docker_service",
        name="Docker Service Status",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("docker_containers")),
        icon="mdi:docker",
    ),
    UnraidBinarySensorEntityDescription(
        key="vm_service",
        name="VM Service Status",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("vms")),
        icon="mdi:desktop-tower",
    ),
    UnraidBinarySensorEntityDescription(
        key="cpu_temperature_warning",
        name="CPU Temperature Monitor",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: any(
            float(data["Core 0"].split()[0]) >= TEMP_WARNING_THRESHOLD
            for sensor, data in data.get("system_stats", {})
            .get("temperature_data", {})
            .get("sensors", {})
            .items()
            if "Core 0" in data
        ) if data.get("system_stats", {}).get("temperature_data", {}).get("sensors") else None,
        has_warning_threshold=True,
        warning_threshold=TEMP_WARNING_THRESHOLD,
        icon="mdi:cpu-64-bit",
    ),
    UnraidBinarySensorEntityDescription(
        key="memory_warning",
        name="Memory Usage Monitor",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats", {}).get("memory_usage", {}).get("percentage", 0) >= MEMORY_WARNING_THRESHOLD if data.get("system_stats", {}).get("memory_usage") else None,
        has_warning_threshold=True,
        warning_threshold=MEMORY_WARNING_THRESHOLD,
        icon="mdi:memory",
    ),
    UnraidBinarySensorEntityDescription(
        key="motherboard_temperature_warning",
        name="Motherboard Temperature Monitor",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: any(
            float(data["MB Temp"].split()[0]) >= TEMP_WARNING_THRESHOLD
            for sensor, data in data.get("system_stats", {})
            .get("temperature_data", {})
            .get("sensors", {})
            .items()
            if "MB Temp" in data
        ) if data.get("system_stats", {}).get("temperature_data", {}).get("sensors") else None,
        has_warning_threshold=True,
        warning_threshold=TEMP_WARNING_THRESHOLD,
        icon="mdi:chip",
    ),
    UnraidBinarySensorEntityDescription(
        key="fan_status",
        name="Fan Status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: any(
            int(fan_data.split()[0]) < FAN_WARNING_THRESHOLD
            for sensor, sensor_data in data.get("system_stats", {})
            .get("temperature_data", {})
            .get("sensors", {})
            .items()
            for fan_key, fan_data in sensor_data.items()
            if "Fan" in fan_key and "RPM" in fan_data
        ) if data.get("system_stats", {}).get("temperature_data", {}).get("sensors") else None,
        icon="mdi:fan",
    ),
)


class UnraidBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Base entity for Unraid binary sensors."""

    entity_description: UnraidBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"Unraid Server ({coordinator.entry.data['host']})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.entity_description.key == "ssh_connectivity":
            return True
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except Exception as err:
            _LOGGER.debug(
                "Error getting state for %s: %s",
                self.entity_description.key,
                err
            )
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional sensor state attributes."""
        attrs = {}
        
        try:
            if self.entity_description.has_warning_threshold:
                attrs["warning_threshold"] = f"{self.entity_description.warning_threshold}%"

            if self.entity_description.key == "array_health":
                array_usage = self.coordinator.data["system_stats"].get("array_usage", {})
                attrs.update({
                    "current_usage": f"{array_usage.get('percentage', 0):.1f}%",
                    "warning_level": f"Warns at {DISK_WARNING_THRESHOLD}% usage",
                })
            elif self.entity_description.key == "memory_warning":
                memory_usage = self.coordinator.data["system_stats"].get("memory_usage", {})
                attrs.update({
                    "current_usage": f"{memory_usage.get('percentage', 0):.1f}%",
                    "warning_level": f"Warns at {MEMORY_WARNING_THRESHOLD}% usage",
                })
            elif self.entity_description.key == "cpu_temperature_warning":
                temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
                for sensor, data in temp_data.get("sensors", {}).items():
                    if "Core 0" in data:
                        attrs.update({
                            "current_temperature": f"{float(data['Core 0'].split()[0]):.1f}°C",
                            "warning_level": f"Warns at {TEMP_WARNING_THRESHOLD}°C",
                        })
                        break
            elif self.entity_description.key == "motherboard_temperature_warning":
                temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
                for sensor, data in temp_data.get("sensors", {}).items():
                    if "MB Temp" in data:
                        attrs.update({
                            "current_temperature": f"{float(data['MB Temp'].split()[0]):.1f}°C",
                            "warning_level": f"Warns at {TEMP_WARNING_THRESHOLD}°C",
                        })
                        break
            elif self.entity_description.key == "fan_status":
                temp_data = self.coordinator.data["system_stats"].get("temperature_data", {})
                fan_count = 1
                attrs["warning_level"] = f"Warns if any fan is below {FAN_WARNING_THRESHOLD} RPM"
                
                for sensor, sensor_data in temp_data.get("sensors", {}).items():
                    for fan_key, fan_data in sensor_data.items():
                        if "Fan" in fan_key and "RPM" in fan_data:
                            # Extract fan speed value and remove any parenthetical text
                            fan_speed = fan_data.split('(')[0].strip()
                            
                            # Check if it's specifically named (like "Array Fan") or needs generic naming
                            if "Array Fan" in fan_key:
                                fan_name = f"Array Fan {fan_count}"
                                fan_count += 1
                            else:
                                fan_name = f"Fan {fan_count}"
                                fan_count += 1
                                
                            attrs[fan_name] = fan_speed

        except Exception as err:
            _LOGGER.debug("Error getting attributes for %s: %s", self.entity_description.key, err)

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class UnraidDiskHealthSensor(UnraidBinarySensorEntity):
    """Binary sensor for individual disk health."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        disk_name: str,
    ) -> None:
        """Initialize the disk health sensor."""
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key=f"disk_health_{disk_name}",
                name=f"Disk {disk_name} Usage Monitor",
                device_class=BinarySensorDeviceClass.PROBLEM,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:harddisk",
                has_warning_threshold=True,
                warning_threshold=DISK_WARNING_THRESHOLD,
            ),
        )
        self._disk_name = disk_name

    @property
    def is_on(self) -> bool | None:
        """Return true if the disk usage is above warning threshold."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    return disk["percentage"] >= DISK_WARNING_THRESHOLD
            return None
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        attrs = {
            "warning_threshold": f"{DISK_WARNING_THRESHOLD}%",
            "warning_level": f"Warns at {DISK_WARNING_THRESHOLD}% usage",
        }
        
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    attrs.update({
                        "current_usage": f"{disk['percentage']:.1f}%",
                        "total_size": format_bytes(disk["total"]),
                        "used_space": format_bytes(disk["used"]),
                        "free_space": format_bytes(disk["free"]),
                        "mount_point": disk["mount_point"],
                    })
                    break
        except Exception as err:
            _LOGGER.debug("Error getting disk attributes for %s: %s", self._disk_name, err)

        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensors based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities: list[UnraidBinarySensorEntity] = []

    # Add all standard sensors
    for description in SENSOR_DESCRIPTIONS:
        entities.append(UnraidBinarySensorEntity(coordinator, description))

    # Add disk health sensors for each disk
    for disk in coordinator.data.get("system_stats", {}).get("individual_disks", []):
        if disk["name"].startswith("disk") or disk["name"] == "cache":
            entities.append(
                UnraidDiskHealthSensor(
                    coordinator=coordinator,
                    disk_name=disk["name"],
                )
            )

    async_add_entities(entities)