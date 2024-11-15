"""Binary sensors for Unraid."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Final, Any, Callable
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SpinDownDelay
from .coordinator import UnraidDataUpdateCoordinator

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
        key="ssh_connectivity",
        name="Server Connection",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats") is not None,
        icon="mdi:server-network",
    ),
    UnraidBinarySensorEntityDescription(
        key="docker_service",
        name="Docker Service",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("docker_containers")),
        icon="mdi:docker",
    ),
    UnraidBinarySensorEntityDescription(
        key="vm_service",
        name="VM Service",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("vms")),
        icon="mdi:desktop-tower",
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
        self._attr_name = f"Unraid {description.name}"  # Add Unraid prefix here
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
        pretty_name = "Cache" if disk_name == "cache" else f"Disk {disk_name.replace('disk', '')}"
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key=f"disk_health_{disk_name}",
                name=f"{pretty_name} Health",  # Base class will add Unraid prefix
                device_class=BinarySensorDeviceClass.PROBLEM,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:harddisk",
                has_warning_threshold=True,
            ),
        )
        self._disk_name = disk_name
        self._last_smart_check = None
        self._smart_status = None
        self._spin_down_delay = SpinDownDelay.MINUTES_30  # Default to 30 minutes

    @property
    def is_on(self) -> bool | None:
        """Return true if there's a problem with the disk."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Update spin down delay if changed
                    new_delay = SpinDownDelay(disk.get("spin_down_delay", SpinDownDelay.MINUTES_30))
                    if new_delay != self._spin_down_delay:
                        self._spin_down_delay = new_delay
                        _LOGGER.debug(
                            "Updated spin down delay for %s to %s",
                            self._disk_name,
                            self._spin_down_delay.to_human_readable()
                        )

                    # If disk is in standby, don't check SMART
                    if disk.get("status") == "standby":
                        return False

                    current_time = datetime.now(timezone.utc)
                    should_check_smart = (
                        self._smart_status is None  # First check
                        or self._spin_down_delay == SpinDownDelay.NEVER  # Never spin down
                        or (
                            self._last_smart_check is not None
                            and (current_time - self._last_smart_check).total_seconds() >= self._spin_down_delay.to_seconds()
                        )
                    )

                    if should_check_smart:
                        self._smart_status = disk.get("health")
                        self._last_smart_check = current_time
                        _LOGGER.debug(
                            "Updated SMART status for %s: %s", 
                            self._disk_name, 
                            self._smart_status
                        )

                    return self._smart_status != "PASSED"
            return None
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        attrs = {}
        
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Disk information
                    attrs.update({
                        "mount_point": disk["mount_point"],
                        "device": disk.get("device", "unknown"),
                        "model": disk.get("model", "unknown"),
                        "temperature": f"{disk.get('temperature', '0')}°C",
                    })
                    
                    # Usage information
                    attrs.update({
                        "current_usage": f"{disk['percentage']:.1f}%",
                        "total_size": format_bytes(disk["total"]),
                        "used_space": format_bytes(disk["used"]),
                        "free_space": format_bytes(disk["free"]),
                    })
                    
                    # Status information
                    attrs.update({
                        "smart_status": disk.get("health", "Unknown"),
                        "disk_status": disk.get("status", "unknown"),
                        "spin_down_delay": self._spin_down_delay.to_human_readable(),
                        "last_smart_check": self._last_smart_check,
                    })
                    
                    break
        except Exception as err:
            _LOGGER.debug("Error getting disk attributes for %s: %s", self._disk_name, err)

        return attrs
    
class UnraidUPSBinarySensor(UnraidBinarySensorEntity):
    """Binary sensor for UPS status."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
    ) -> None:
        """Initialize the UPS binary sensor."""
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key="ups_status",
                name="UPS Status",  # Base class will add Unraid prefix
                device_class=BinarySensorDeviceClass.POWER,  # Changed to POWER device class
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:battery-medium",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info")
        return self.coordinator.last_update_success and bool(ups_info)

    @property
    def is_on(self) -> bool | None:
        """Return true if the UPS is online."""
        try:
            status = self.coordinator.data["system_stats"].get("ups_info", {}).get("STATUS")
            if status is None:
                return None
            return status.upper() in ["ONLINE", "ON LINE"]
        except Exception as err:
            _LOGGER.debug("Error getting UPS status: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            ups_info = self.coordinator.data["system_stats"].get("ups_info", {})
            
            # Format numeric values with units
            attrs = {
                "model": ups_info.get("MODEL", "Unknown"),
                "status": ups_info.get("STATUS", "Unknown"),
            }
            
            # Add percentage values
            if "BCHARGE" in ups_info:
                attrs["battery_charge"] = f"{ups_info['BCHARGE']}%"
            if "LOADPCT" in ups_info:
                attrs["load_percentage"] = f"{ups_info['LOADPCT']}%"
            
            # Add time values
            if "TIMELEFT" in ups_info:
                attrs["runtime_left"] = f"{ups_info['TIMELEFT']} minutes"
                
            # Add power/voltage values
            if "NOMPOWER" in ups_info:
                attrs["nominal_power"] = f"{ups_info['NOMPOWER']}W"
            if "LINEV" in ups_info:
                attrs["line_voltage"] = f"{ups_info['LINEV']}V"
            if "BATTV" in ups_info:
                attrs["battery_voltage"] = f"{ups_info['BATTV']}V"

            return attrs
            
        except Exception as err:
            _LOGGER.debug("Error getting UPS attributes: %s", err)
            return {}
        
class UnraidParityCheckSensor(UnraidBinarySensorEntity):
    """Binary sensor for Unraid parity check status."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
    ) -> None:
        """Initialize the parity check sensor."""
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key="parity_check",
                name="Parity",
                device_class=BinarySensorDeviceClass.PROBLEM,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:harddisk-plus",
            ),
        )
        self._attr_has_entity_name = True
        self._previous_state = None
        self._last_updated = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        parity_data = self.coordinator.data.get("parity_status", {})
        return parity_data.get("has_parity", False)

    @property
    def is_on(self) -> bool | None:
        """Return true if parity is INVALID."""
        parity_data = self.coordinator.data.get("parity_status")
        if not parity_data or not parity_data.get("has_parity"):
            return None
            
        current_state = bool(parity_data.get("errors", 0) > 0)
        if self._previous_state != current_state:
            self._last_updated = dt_util.utcnow()
            self._previous_state = current_state

        return current_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        parity_data = self.coordinator.data.get("parity_status", {})
        attributes: dict[str, Any] = {}

        try:
            # Basic status first
            status = "checking" if parity_data.get("is_active") else "valid" if not self.is_on else "invalid"
            attributes["status"] = status

            # Last check information
            if last_check := parity_data.get("last_check"):
                try:
                    # Only format if last_check is actually a datetime object
                    if isinstance(last_check, datetime):
                        check_time = last_check.strftime("%I:%M:%S %p").lstrip('0')
                        check_date = last_check.strftime("%a %d %b %Y")
                        attributes["last_check"] = f"{check_date} {check_time}"
                    else:
                        attributes["last_check"] = str(last_check)

                    # Add other attributes only if they exist
                    if duration := parity_data.get('duration'):
                        attributes["duration"] = duration
                    
                    if avg_speed := parity_data.get('avg_speed'):
                        attributes["average_speed"] = f"{float(avg_speed):.1f} MB/s"
                    
                    attributes["errors"] = parity_data.get('errors', 0)
                    
                except (AttributeError, TypeError, ValueError) as err:
                    _LOGGER.debug("Error formatting last check info: %s", err)
                    # Still include raw data if formatting fails
                    attributes["last_check_raw"] = str(last_check)

            # Active check information
            if parity_data.get("is_active"):
                if progress := parity_data.get('progress'):
                    attributes["progress"] = f"{float(progress):.1f}%"
                
                if speed := parity_data.get('speed'):
                    attributes["current_speed"] = f"{float(speed):.1f} MB/s"
                else:
                    attributes["current_speed"] = "Unknown"
                    
                # Add estimated completion if available and valid
                if est := parity_data.get("estimated_completion"):
                    if isinstance(est, datetime):
                        try:
                            attributes["estimated_finish"] = est.strftime("%I:%M:%S %p %d %b %Y").lstrip('0')
                        except (AttributeError, TypeError):
                            attributes["estimated_finish"] = str(est)

        except Exception as err:
            _LOGGER.debug("Error preparing parity check attributes: %s", err)
            # Ensure we at least return a status
            attributes["status"] = "unknown"
            attributes["error"] = str(err)

        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        parity_data = self.coordinator.data.get("parity_status", {})
        if parity_data.get("schedule") == "Disabled":
            return False
        return True

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        parity_data = self.coordinator.data.get("parity_status", {})
        if parity_data.get("schedule") == "Disabled":
            registry = er.async_get(self.hass)
            if entity_id := registry.async_get_entity_id(
                self.platform.domain,
                DOMAIN,
                self.unique_id,
            ):
                registry.async_remove(entity_id)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensors based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities: list[UnraidBinarySensorEntity] = []

    # Check for parity configuration
    has_parity = await coordinator.api.has_parity_configured()
    if has_parity:
        _LOGGER.debug("Parity drive detected, creating parity sensor")
        entities.append(UnraidParityCheckSensor(coordinator))
    else:
        _LOGGER.debug("No parity drive detected, skipping parity sensor")

    # Add all standard sensors
    for description in SENSOR_DESCRIPTIONS:
        entities.append(UnraidBinarySensorEntity(coordinator, description))

    # Add UPS sensor if enabled
    if coordinator.has_ups:
        entities.append(UnraidUPSBinarySensor(coordinator))

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