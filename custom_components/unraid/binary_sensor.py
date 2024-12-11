"""Binary sensors for Unraid."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
import logging

from homeassistant.components.binary_sensor import ( # type: ignore
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import EntityCategory # type: ignore
from homeassistant.core import HomeAssistant, callback # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore
from homeassistant.helpers.typing import StateType # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore

from .const import (
    DOMAIN, 
    SpinDownDelay,
)

from .coordinator import UnraidDataUpdateCoordinator
from .helpers import format_bytes

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Unraid binary sensor entity."""

    # Add inherited fields that need to be explicitly declared
    key: str
    name: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None

    # Custom fields
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
        hostname = coordinator.hostname.capitalize()
        
        # Clean the key of any existing hostname instances
        clean_key = description.key
        hostname_variations = [hostname.lower(), hostname.capitalize(), hostname.upper()]
        for variation in hostname_variations:
            clean_key = clean_key.replace(f"{variation}_", "")
        
        # Construct unique_id with guaranteed single hostname instance
        self._attr_unique_id = f"unraid_server_{hostname}_{clean_key}"
        
        # Keep the name simple and human-readable
        self._attr_name = f"{hostname} {description.name}"
        
        # All binary sensors belong to main server device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"Unraid Server ({hostname})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }
        self._attr_has_entity_name = True

        # Add sensor-specific model info
        model = "System Sensor"
        if "docker" in description.key:
            model = "Docker Sensor"
        elif "vm" in description.key:
            model = "VM Sensor"
        
        self._attr_device_info.update({
            "model": model
        })

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
        except KeyError as err:
            _LOGGER.debug(
                "Missing key in data for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except TypeError as err:
            _LOGGER.debug(
                "Type error processing sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except AttributeError as err:
            _LOGGER.debug(
                "Attribute error for sensor %s: %s",
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
        # Initialise _disk_num first
        self._disk_num = None
        if disk_name.startswith("disk"):
            try:
                self._disk_num = int(''.join(filter(str.isdigit, disk_name)))
            except ValueError:
                _LOGGER.debug("Could not extract disk number from %s", disk_name)
        
        # Handle naming for different disk types
        if disk_name == "cache":
            pretty_name = "Cache"
        elif disk_name == "parity":
            pretty_name = "Parity"
        else:
            # Add validation to ensure we have a valid disk number
            try:
                disk_num = ''.join(filter(str.isdigit, disk_name))
                if not disk_num:
                    raise ValueError(f"Invalid disk name format: {disk_name}")
                pretty_name = f"Disk {disk_num}"
            except ValueError as err:
                _LOGGER.error("Error parsing disk name %s: %s", disk_name, err)
                pretty_name = disk_name.title()

        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key=f"disk_health_{disk_name}",
                name=f"{pretty_name} Health",
                device_class=BinarySensorDeviceClass.PROBLEM, 
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:harddisk",
                has_warning_threshold=True,
            ),
        )

        self._disk_name = disk_name
        
        # Map device based on disk name
        self._device = None
        if disk_name == "cache":
            self._device = "nvme0n1"
        elif disk_name.startswith("disk"):
            try:
                disk_num = int(''.join(filter(str.isdigit, disk_name)))
                self._device = f"sd{chr(ord('b') + disk_num - 1)}"
                self._disk_num = disk_num  # Store disk number if valid
            except ValueError:
                _LOGGER.debug("Could not extract disk number from %s", disk_name)
                self._disk_num = None
        
        # Initialize tracking variables
        self._last_smart_check = None
        self._smart_status = None 
        self._last_problem_state = None
        self._spin_down_delay = self._get_spin_down_delay()
        self._last_temperature = None
        self._problem_attributes: Dict[str, Any] = {}

        _LOGGER.debug(
            "Initialized disk health sensor for %s (device: %s)",
            disk_name,
            self._device or "unknown"
        )

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay for this disk."""
        try:
            disk_cfg = self.coordinator.data.get("disk_config", {})
            # Get global setting (default to NEVER/0 if not specified)
            global_delay = int(disk_cfg.get("spindownDelay", "0"))
            # Check for disk-specific setting if this is an array disk
            if self._disk_num is not None:
                disk_delay = disk_cfg.get(f"diskSpindownDelay.{self._disk_num}")
                if disk_delay and disk_delay != "-1":  # -1 means use global setting
                    global_delay = int(disk_delay)
            # Convert to SpinDownDelay enum
            return SpinDownDelay(global_delay)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for %s: %s. Using default Never.",
                self._disk_name,
                err
            )
            return SpinDownDelay.NEVER

    def _analyze_smart_status(self, disk_data: Dict[str, Any]) -> bool:
        """Analyze SMART status and attributes for actual problems."""
        self._problem_attributes = {}
        
        try:
            # Log sanitized disk data (exclude large data structures)
            _LOGGER.debug(
                "Starting SMART analysis for disk %s with data: %s",
                self._disk_name,
                {k: v for k, v in disk_data.items() if k not in ['smart_data']}
            )

            # Detailed initial state logging
            _LOGGER.debug(
                "Disk %s initial state - State: %s, Health: %s, Temperature: %s, Status: %s, Smart Status: %s",
                self._disk_name,
                disk_data.get("state", "unknown"),
                disk_data.get("health", "unknown"),
                disk_data.get("temperature", "unknown"),
                disk_data.get("status", "unknown"),
                disk_data.get("smart_status", "unknown")
            )

            # Check disk state using proper standby detection
            disk_state = disk_data.get("state", "unknown").lower()
            _LOGGER.debug("Disk %s current state: %s", self._disk_name, disk_state)
            
            # Only return cached state for confirmed standby
            if disk_state == "standby":
                _LOGGER.debug(
                    "Disk %s is in standby, using cached problem state: %s",
                    self._disk_name,
                    self._last_problem_state
                )
                return self._last_problem_state if self._last_problem_state is not None else False

            has_problem = False

            # Get and validate SMART data
            smart_data = disk_data.get("smart_data", {})
            if not smart_data:
                _LOGGER.debug("No SMART data available for %s", self._disk_name)
                return self._last_problem_state if self._last_problem_state is not None else False

            # Check overall SMART status
            smart_status = smart_data.get("smart_status", True)
            _LOGGER.debug("Disk %s SMART status: %s", self._disk_name, smart_status)
            
            if not smart_status:
                self._problem_attributes["smart_status"] = "FAILED"
                has_problem = True
                _LOGGER.warning(
                    "Disk %s has failed SMART status",
                    self._disk_name
                )

            # Determine device type
            device_type = "nvme" if smart_data.get("type") == "nvme" else "sata"
            _LOGGER.debug(
                "Processing %s disk %s",
                device_type.upper(),
                self._disk_name
            )

            # Device specific checks
            if device_type == "nvme":
                # NVMe specific health checks
                nvme_health = smart_data.get("nvme_smart_health_information_log", {})
                _LOGGER.debug(
                    "NVMe health data for %s: %s",
                    self._disk_name,
                    nvme_health
                )
                
                # Media errors check
                media_errors = nvme_health.get("media_errors", 0)
                if int(media_errors) > 0:
                    self._problem_attributes["media_errors"] = media_errors
                    has_problem = True
                    _LOGGER.warning(
                        "NVMe disk %s has %d media errors",
                        self._disk_name,
                        media_errors
                    )
                    
                # Critical warning check
                if warning := nvme_health.get("critical_warning"):
                    if warning != 0:  # NVMe uses numeric warning flags
                        self._problem_attributes["critical_warning"] = warning
                        has_problem = True
                        _LOGGER.warning(
                            "NVMe disk %s has critical warning: %d",
                            self._disk_name,
                            warning
                        )

                # Temperature from NVMe health log
                if temp := nvme_health.get("temperature"):
                    _LOGGER.debug(
                        "NVMe temperature for %s: %d°C",
                        self._disk_name,
                        temp
                    )
                    if temp > 70:  # NVMe temperature threshold
                        self._problem_attributes["temperature"] = f"{temp}°C"
                        has_problem = True
                        _LOGGER.warning(
                            "NVMe disk %s temperature is high: %d°C (threshold: 70°C)",
                            self._disk_name,
                            temp
                        )

            else:
                # SATA disk checks
                _LOGGER.debug(
                    "Processing SATA attributes for %s",
                    self._disk_name
                )
                
                attributes = smart_data.get("ata_smart_attributes", {}).get("table", [])
                
                # Map of critical attributes and their thresholds
                critical_attrs = {
                    "Reallocated_Sector_Ct": 0,
                    "Current_Pending_Sector": 0,
                    "Offline_Uncorrectable": 0,
                    "UDMA_CRC_Error_Count": 100,
                    "Reallocated_Event_Count": 0,
                    "Reported_Uncorrect": 0,
                    "Command_Timeout": 100
                }
                
                # Process each attribute
                for attr in attributes:
                    name = attr.get("name")
                    if not name:
                        continue

                    # Check critical attributes
                    if name in critical_attrs:
                        raw_value = attr.get("raw", {}).get("value", 0)
                        threshold = critical_attrs[name]
                        
                        _LOGGER.debug(
                            "Checking %s for %s: value=%s, threshold=%s",
                            name,
                            self._disk_name,
                            raw_value,
                            threshold
                        )
                        
                        if int(raw_value) > threshold:
                            self._problem_attributes[name.lower()] = raw_value
                            has_problem = True
                            _LOGGER.warning(
                                "Disk %s has high %s: %d (threshold: %d)",
                                self._disk_name,
                                name,
                                raw_value,
                                threshold
                            )

                    # Temperature check from attributes
                    elif name == "Temperature_Celsius":
                        temp = attr.get("raw", {}).get("value")
                        if temp is not None:
                            _LOGGER.debug(
                                "SATA temperature for %s: %d°C",
                                self._disk_name,
                                temp
                            )
                            if temp > 55:  # SATA temperature threshold
                                self._problem_attributes["temperature"] = f"{temp}°C"
                                has_problem = True
                                _LOGGER.warning(
                                    "SATA disk %s temperature is high: %d°C (threshold: 55°C)",
                                    self._disk_name,
                                    temp
                                )

            # Store final state
            self._last_problem_state = has_problem
            
            if has_problem:
                _LOGGER.warning(
                    "Disk %s has problems: %s",
                    self._disk_name,
                    self._problem_attributes
                )
            else:
                _LOGGER.debug(
                    "No problems found for disk %s",
                    self._disk_name
                )
            
            return has_problem

        except Exception as err:
            _LOGGER.error(
                "SMART analysis failed for %s: %s",
                self._disk_name,
                err,
                exc_info=True
            )
            return self._last_problem_state if self._last_problem_state is not None else False

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

                    # Get current state
                    current_state = disk.get("state", "unknown").lower()
                    if current_state == "standby":
                        return self._last_problem_state if self._last_problem_state is not None else False

                    current_time = datetime.now(timezone.utc)
                    should_check_smart = (
                        self._smart_status is None  # First check
                        or self._spin_down_delay == SpinDownDelay.NEVER  # Never spin down
                        or (
                            self._last_smart_check is not None
                            and (
                                current_time - self._last_smart_check
                            ).total_seconds() >= self._spin_down_delay.to_seconds()
                        )
                    )

                    if should_check_smart:
                        # Smart data will be updated by coordinator
                        self._last_smart_check = current_time
                        return self._analyze_smart_status(disk)

                    # Use cached status
                    return self._last_problem_state if self._last_problem_state is not None else False

            return None

        except (KeyError, AttributeError, TypeError, ValueError) as err:
            _LOGGER.debug("Error checking disk health: %s", err)
            return self._last_problem_state if self._last_problem_state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            # Get disk info from mapping
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Get current disk state and type
                    disk_state = disk.get("state", "unknown")
                    is_nvme = "nvme" in str(self._device).lower()
                    
                    # Basic attributes
                    attrs = {
                        "mount_point": disk["mount_point"],
                        "device": self._device or disk.get("device", "unknown"),
                    }

                    # Handle temperature based on disk type and state
                    temp = disk.get("temperature")
                    if is_nvme:
                        # NVMe drives always show actual temperature from SMART data
                        smart_data = disk.get("smart_data", {})
                        nvme_temp = (
                            smart_data.get("temperature")
                            or temp  # Fallback to disk temperature
                            or smart_data.get("nvme_temperature")  # Additional fallback
                        )
                        attrs["temperature"] = f"{nvme_temp}°C" if nvme_temp is not None else "0°C"
                        attrs["disk_status"] = "active"  # NVMe drives are always active
                    else:
                        # SATA drives show 0°C in standby
                        if disk_state == "standby":
                            attrs["temperature"] = "0°C"
                            attrs["disk_status"] = "standby"
                        else:
                            attrs["temperature"] = f"{temp}°C" if temp is not None else "0°C"
                            attrs["disk_status"] = disk_state

                    # Usage information
                    attrs.update({
                        "current_usage": f"{disk['percentage']:.1f}%",
                        "total_size": format_bytes(disk["total"]),
                        "used_space": format_bytes(disk["used"]),
                        "free_space": format_bytes(disk["free"]),
                    })

                    # Status information
                    attrs.update({
                        "smart_status": disk.get("health", "healthy"),  # Default to healthy
                        "spin_down_delay": self._spin_down_delay.to_human_readable(),
                        "power_state": disk_state,
                    })

                    # Add SMART details
                    smart_data = disk.get("smart_data", {})
                    if smart_data:
                        if is_nvme:
                            nvme_health = {
                                "available_spare": f"{smart_data.get('available_spare', 0)}%",
                                "media_errors": smart_data.get('media_errors', 0),
                                "critical_warning": smart_data.get('critical_warning', 'none'),
                                "percentage_used": f"{smart_data.get('percentage_used', 0)}%",
                            }
                            # Add additional NVMe specific attributes if available
                            if 'data_units_read' in smart_data:
                                nvme_health["data_units_read"] = smart_data["data_units_read"]
                            if 'data_units_written' in smart_data:
                                nvme_health["data_units_written"] = smart_data["data_units_written"]
                            if 'power_on_hours' in smart_data:
                                nvme_health["power_on_hours"] = smart_data["power_on_hours"]
                                
                            attrs["nvme_health"] = nvme_health
                        else:
                            attrs["smart_details"] = {
                                "power_on_hours": smart_data.get("power_on_hours"),
                                "status": "Passed" if smart_data.get("smart_status", True) else "Failed",
                            }

                    # Add problem details if any exist
                    if self._problem_attributes:
                        attrs["problem_details"] = self._problem_attributes

                    return attrs

            return {}

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Missing key in disk data: %s", err)
            return {}

class UnraidParityDiskSensor(UnraidDiskHealthSensor):
    """Binary sensor for parity disk health."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        parity_info: Dict[str, Any]
    ) -> None:
        """Initialize the parity disk sensor."""
        self._parity_info = parity_info
        device = parity_info.get("rdevName.0", "").strip()
        if device and not device.startswith("/dev/"):
            device = f"/dev/{device}"
            
        super().__init__(
            coordinator=coordinator,
            disk_name="parity"
        )
        
        # Override device info for parity disk
        self._device = device
        self._attr_name = f"{coordinator.hostname.capitalize()} Parity Health"
        
        # Initialize state variables
        self._last_state = None
        self._mount_point = "/mnt/parity"
        self._disk_state = "unknown"
        self._problem_attributes: Dict[str, Any] = {}
        self._last_smart_check = None
        self._smart_status = None
        
        # Get spin down delay from config
        self._spin_down_delay = self._get_spin_down_delay()
        
        _LOGGER.debug(
            "Initialized parity disk sensor with device: %s",
            self._device
        )

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay configuration."""
        try:
            # Check disk config for parity-specific setting
            disk_cfg = self.coordinator.data.get("disk_config", {})
            
            # Try to get parity-specific spin down delay
            delay = disk_cfg.get("diskSpindownDelay.0")  # Parity is disk0
            if delay is None or delay == "-1":
                # Use global setting if no parity-specific setting
                delay = disk_cfg.get("spindownDelay", "0")
            
            return SpinDownDelay(int(delay))
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for parity disk: %s. Using default.",
                err
            )
            return SpinDownDelay.NEVER

    def _get_disk_state(self) -> str:
        """Get current disk state from smartctl."""
        try:
            if not self._device:
                return "unknown"
                
            # Look for cached state first
            for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                if (disk.get("device") == self._device.replace("/dev/", "") or 
                    disk.get("name") == "parity"):
                    return disk.get("state", "unknown").lower()

            # Check smart data
            smart_data = self.coordinator.data.get("smart_data", {}).get(self._device, {})
            if smart_data:
                return smart_data.get("state", "active")

            return "active"  # Default to active for parity
            
        except Exception as err:
            _LOGGER.error("Error getting disk state: %s", err)
            return "unknown"

    @property
    def is_on(self) -> bool | None:
        """Return true if there's a problem with the parity disk."""
        try:
            # Get latest parity info
            parity_info = self.coordinator.data.get("parity_info", self._parity_info)
            
            if not parity_info:
                return None

            has_problem = False
            self._problem_attributes = {}

            # Get current state
            self._disk_state = self._get_disk_state()
            
            # Check basic parity status
            if (status := parity_info.get("rdevStatus.0")) != "DISK_OK":
                self._problem_attributes["parity_status"] = status
                _LOGGER.warning("Parity disk status issue: %s", status)
                has_problem = True

            # Check disk state (7 is normal operation)
            if (state := parity_info.get("diskState.0", "0")) != "7":
                self._problem_attributes["disk_state"] = f"Abnormal ({state})"
                _LOGGER.warning("Parity disk state issue: %s", state)
                has_problem = True
            
            # Check SMART status if available
            if self._device:
                # Create disk data structure for SMART analysis
                disk_data = {
                    "name": "parity",
                    "device": self._device.replace("/dev/", ""),
                    "smart_data": self.coordinator.data.get("smart_data", {}).get(self._device, {}),
                    "state": self._disk_state,
                    "health": "Passed" if not has_problem else "Failed",
                }

                # Look for full disk data in coordinator
                for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                    if disk.get("name") == "parity":
                        disk_data.update(disk)
                        break

                smart_result = self._analyze_smart_status(disk_data)
                has_problem = has_problem or smart_result

            self._last_state = has_problem
            return has_problem

        except Exception as err:
            _LOGGER.error("Error checking parity health: %s", err)
            return self._last_state if self._last_state is not None else None

    def _get_temperature(self) -> Optional[int]:
        """Get current disk temperature."""
        try:
            # First check disk data
            for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == "parity" and (temp := disk.get("temperature")) is not None:
                    return temp
                    
            # Try SMART data
            if self._device:
                smart_data = self.coordinator.data.get("smart_data", {}).get(self._device, {})
                if temp := smart_data.get("temperature"):
                    return temp
                    
            return None
            
        except Exception as err:
            _LOGGER.error("Error getting temperature: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            # Get latest parity info
            parity_info = self.coordinator.data.get("parity_info", self._parity_info)
            if not parity_info:
                return {}

            # Get disk state
            self._disk_state = self._get_disk_state()

            # Get current temperature
            temperature = self._get_temperature()

            # Build base attributes
            attrs = {
                "mount_point": self._mount_point,
                "device": self._device,
                "disk_status": self._disk_state,
                "power_state": self._disk_state,
                "spin_down_delay": self._spin_down_delay.to_human_readable(),
                "smart_status": "Failed" if self._last_state else "Passed",
                "temperature": f"{temperature}°C" if temperature is not None else "0°C"
            }

            # Additional disk information
            attrs.update({
                "total_size": format_bytes(int(parity_info.get("diskSize.0", 0))),
            })
            
            # Add SMART details if available
            if self._device:
                smart_data = self.coordinator.data.get("smart_data", {}).get(self._device, {})
                if smart_data:
                    attrs["smart_details"] = {
                        "power_on_hours": smart_data.get("power_on_hours"),
                        "status": "Passed" if smart_data.get("smart_status", True) else "Failed"
                    }
            
            # Add any problem details if they exist
            if self._problem_attributes:
                attrs["problem_details"] = self._problem_attributes
            
            return attrs

        except Exception as err:
            _LOGGER.debug("Error getting parity attributes: %s", err)
            return {}

class UnraidUPSBinarySensor(UnraidBinarySensorEntity):
    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key="ups_status",
                name="UPS Status",
                device_class=BinarySensorDeviceClass.POWER,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:battery-medium",
            )
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
        except (KeyError, AttributeError, TypeError) as err:
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
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting UPS attributes: %s", err)
            return {}

async def _get_parity_info(coordinator: UnraidDataUpdateCoordinator) -> Optional[Dict[str, Any]]:
    """Get parity disk information from mdcmd status."""
    try:
        result = await coordinator.api.execute_command("mdcmd status")
        if result.exit_status != 0:
            return None

        parity_info = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in [
                "diskNumber.0", "diskName.0", "diskSize.0", "diskState.0",
                "diskId.0", "rdevNumber.0", "rdevStatus.0", "rdevName.0",
                "rdevOffset.0", "rdevSize.0", "rdevId.0"
            ]:
                parity_info[key] = value

        # Only return if we found valid parity info
        if "rdevName.0" in parity_info and "diskState.0" in parity_info:
            return parity_info

        return None

    except Exception as err:
        _LOGGER.error("Error getting parity disk info: %s", err)
        return None

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensors."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[UnraidBinarySensorEntity] = []
    processed_disks = set()  # Track processed disks

    # Add base sensors first
    for description in SENSOR_DESCRIPTIONS:
        entities.append(UnraidBinarySensorEntity(coordinator, description))

    # Add UPS sensor if UPS info is available
    if coordinator.data.get("system_stats", {}).get("ups_info"):
        entities.append(UnraidUPSBinarySensor(coordinator))

    # Check for and add parity disk sensor
    parity_info = await _get_parity_info(coordinator)
    if parity_info:
        # Store parity info in coordinator data for future updates
        coordinator.data["parity_info"] = parity_info
        entities.append(UnraidParityDiskSensor(coordinator, parity_info))
        _LOGGER.debug(
            "Added parity disk sensor for device: %s", 
            parity_info.get("rdevName.0")
        )

    # Filter out tmpfs and special mounts
    ignored_mounts = {
        "disks", "remotes", "addons", "rootshare", 
        "user/0", "dev/shm"
    }

    # Process disk health sensors
    disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])
    valid_disks = [
        disk for disk in disk_data
        if (
            disk.get("name")
            and not any(mount in disk.get("mount_point", "") for mount in ignored_mounts)
            and disk.get("filesystem") != "tmpfs"
        )
    ]

    for disk in valid_disks:
        disk_name = disk.get("name")

        # Skip if invalid or already processed
        if not disk_name or disk_name in processed_disks:
            continue

        if disk_name.startswith("disk") or disk_name == "cache":
            _LOGGER.debug(
                "Adding health sensor for disk: %s", 
                disk_name
            )
            try:
                entities.append(
                    UnraidDiskHealthSensor(
                        coordinator=coordinator,
                        disk_name=disk_name
                    )
                )
                processed_disks.add(disk_name)
            except ValueError as err:
                _LOGGER.warning("Skipping invalid disk %s: %s", disk_name, err)
                continue

    async_add_entities(entities)
