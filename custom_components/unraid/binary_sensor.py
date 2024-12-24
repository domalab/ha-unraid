"""Binary sensors for Unraid."""
from __future__ import annotations

import asyncio
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
from homeassistant.helpers.entity import DeviceInfo # type: ignore

from .const import (
    DOMAIN, 
    SpinDownDelay,
)

from .coordinator import UnraidDataUpdateCoordinator
from .helpers import (
    DiskDataHelperMixin,
    format_bytes,
    get_disk_identifiers,
    get_disk_number,
    get_unraid_disk_mapping,
)
from .naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

def is_valid_disk_name(disk_name: str) -> bool:
    """Determine if a disk name should be monitored.
    
    Args:
        disk_name: The name of the disk to check.
        
    Returns:
        bool: True if the disk should be monitored, False otherwise.
    """
    if not disk_name:
        return False
        
    # Array disks (disk1, disk2, etc)
    if disk_name.startswith("disk"):
        return True
        
    # Any cache pool (cache, cache2, cacheNVME, etc)
    if disk_name.startswith("cache"):
        return True
        
    # Custom pools (fastpool, nvmepool, etc)
    # Skip system paths and known special names
    invalid_names = {"parity", "flash", "boot", "temp", "user"}
    if disk_name.lower() not in invalid_names:
        return True
        
    return False

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
        
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component=description.key.split('_')[0]  # First part of key as component
        )
        
        # Set unique ID and name using naming utility
        self._attr_unique_id = naming.get_entity_id(description.key)
        self._attr_name = f"{naming.clean_hostname()} {description.name}"
        
        # All binary sensors belong to main server device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=f"Unraid Server ({coordinator.hostname})",
            manufacturer="Lime Technology",
            model="Unraid Server",
        )
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

class UnraidDiskHealthSensor(UnraidBinarySensorEntity, DiskDataHelperMixin):
    """Binary sensor for individual disk health."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        disk_name: str,
    ) -> None:
        """Initialize the disk health sensor."""
        self._disk_name = disk_name
        self._disk_num = get_disk_number(disk_name)
        
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="disk"
        )
        
        # Get pretty name using naming utility
        component_type = "cache" if disk_name == "cache" else "disk"
        pretty_name = naming.get_entity_name(disk_name, component_type)

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

        # Get device and serial from helpers
        self._device, self._serial = get_disk_identifiers(coordinator.data, disk_name)
                        
        # Initialize tracking variables
        self._last_smart_check = None
        self._smart_status = None 
        self._last_problem_state = None
        self._spin_down_delay = self._get_spin_down_delay()
        self._last_temperature = None
        self._problem_attributes: Dict[str, Any] = {}

        _LOGGER.debug(
            "Initialized disk health sensor with device: %s, serial: %s",
            self._device or "unknown",
            self._serial or "unknown"
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
                    is_standby = disk.get("state", "unknown").lower() == "standby"
                    if is_standby:
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
                        self._last_smart_check = current_time
                        return self._analyze_smart_status(disk)

                    return self._last_problem_state if self._last_problem_state is not None else False

            return None

        except (KeyError, AttributeError, TypeError, ValueError) as err:
            _LOGGER.debug("Error checking disk health: %s", err)
            return self._last_problem_state if self._last_problem_state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Get current disk state and device type
                    is_standby = disk.get("state", "unknown").lower() == "standby"
                    is_nvme = "nvme" in str(self._device or "").lower()
                    
                    # Get storage attributes
                    attrs = self._get_storage_attributes(
                        total=disk.get("total", 0),
                        used=disk.get("used", 0),
                        free=disk.get("free", 0),
                        mount_point=disk.get("mount_point"),
                        device=self._device,
                        is_standby=is_standby
                    )

                    # Add disk serial
                    disk_map = get_unraid_disk_mapping(
                        {"system_stats": self.coordinator.data.get("system_stats", {})}
                    )
                    if serial := disk_map.get(self._disk_name, {}).get("serial"):
                        attrs["disk_serial"] = serial

                    # Handle temperature
                    temp = disk.get("temperature")
                    if is_nvme:
                        # NVMe drives always show actual temperature from SMART data
                        smart_data = disk.get("smart_data", {})
                        nvme_temp = (
                            smart_data.get("temperature")
                            or temp  
                            or smart_data.get("nvme_temperature")
                        )
                        if not is_standby and nvme_temp is not None:
                            self._last_temperature = nvme_temp
                    else:
                        # SATA drives
                        if not is_standby and temp is not None:
                            self._last_temperature = temp
                            
                    attrs["temperature"] = self._get_temperature_str(
                        self._last_temperature if is_standby else temp,
                        is_standby
                    )

                    # Add SMART status
                    if smart_data := disk.get("smart_data", {}):
                        attrs["smart_status"] = (
                            "Passed" if smart_data.get("smart_status", True)
                            else "Failed"
                        )

                    # Add spin down delay
                    attrs["spin_down_delay"] = self._spin_down_delay.to_human_readable()

                    # Add any problem details
                    if self._problem_attributes:
                        attrs["problem_details"] = self._problem_attributes

                    return attrs

            return {}

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Missing key in disk data: %s", err)
            return {}

class UnraidParityDiskSensor(UnraidBinarySensorEntity, DiskDataHelperMixin):
    """Binary sensor for parity disk health with enhanced monitoring."""

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay for parity disk with fallback."""
        try:
            # Check disk config for parity-specific setting
            disk_cfg = self.coordinator.data.get("disk_config", {})
            
            # Get parity delay (diskSpindownDelay.0)
            delay = disk_cfg.get("diskSpindownDelay.0")
            if delay and delay != "-1":
                _LOGGER.debug("Using parity-specific spin down delay: %s", delay)
                return SpinDownDelay(int(delay))
                
            # Use global setting
            global_delay = disk_cfg.get("spindownDelay", "0")
            _LOGGER.debug("Using global spin down delay: %s", global_delay)
            return SpinDownDelay(int(global_delay))
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for parity disk: %s. Using default.",
                err
            )
            return SpinDownDelay.NEVER

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        parity_info: Dict[str, Any]
    ) -> None:
        """Initialize the parity disk sensor."""
        self._parity_info = parity_info
        self._disk_serial = parity_info.get("diskId.0", "")  # Get serial number
        device = parity_info.get("rdevName.0", "").strip()
        
        _LOGGER.debug(
            "Initializing parity disk sensor with device: %s, info: %s",
            device,
            {k: v for k, v in parity_info.items() if k != "smart_data"}
        )
        
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="parity"
        )
                
        description = UnraidBinarySensorEntityDescription(
            key="parity_health",
            name=f"{naming.get_entity_name('parity', 'parity')} Health",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk",
            has_warning_threshold=True,
        )
        
        # Initialize parent class
        super().__init__(coordinator, description)
        
        # Override device info for parity disk
        self._device = device
        self._attr_name = f"{naming.clean_hostname()} Parity Health"
        
        # Initialize state variables
        self._last_state = None
        self._problem_attributes: Dict[str, Any] = {}
        self._last_smart_check = None
        self._smart_status = None
        self._last_temperature = None
        self._disk_state = "unknown"  # Add disk state initialization
        
        # Get spin down delay from config
        self._spin_down_delay = self._get_spin_down_delay()

    def _get_temperature(self) -> Optional[int]:
        """Get current disk temperature."""
        try:
            # Get current array state
            array_state = self.coordinator.data.get("array_state", {})
            self._disk_state = "active" if array_state.get("state") == "STARTED" else "standby"

            # First check disk data
            for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == "parity" and (temp := disk.get("temperature")) is not None:
                    _LOGGER.debug("Got parity temperature %d°C from disk data", temp)
                    self._last_temperature = temp
                    return temp

            # Try SMART data if available    
            if self._device:
                smart_data = self.coordinator.data.get("smart_data", {}).get(self._device, {})
                if temp := smart_data.get("temperature"):
                    _LOGGER.debug("Got parity temperature %d°C from SMART data", temp)
                    self._last_temperature = temp
                    return temp
                    
            # Return cached temperature if available
            if self._disk_state == "standby" and self._last_temperature is not None:
                _LOGGER.debug("Using cached temperature for standby parity disk: %d°C", self._last_temperature)
                return self._last_temperature

            _LOGGER.debug("No temperature data available for parity disk")
            return None
            
        except Exception as err:
            _LOGGER.error("Error getting parity temperature: %s", err)
            return None

    def _analyze_smart_status(self, disk_data: Dict[str, Any]) -> bool:
        """Analyze SMART status and attributes for actual problems."""
        self._problem_attributes = {}
        previous_state = self._last_state
        
        try:
            _LOGGER.debug(
                "Starting SMART analysis for parity disk with data: %s",
                {k: v for k, v in disk_data.items() if k not in ['smart_data', 'attributes']}
            )

            _LOGGER.debug(
                "Parity disk initial state - State: %s, Temperature: %s°C, Status: %s",
                disk_data.get("state", "unknown"),
                disk_data.get("temperature", "unknown"),
                self._parity_info.get("rdevStatus.0", "unknown")
            )

            has_problem = False

            # Check parity status first
            if (status := self._parity_info.get("rdevStatus.0")) != "DISK_OK":
                self._problem_attributes["parity_status"] = status
                has_problem = True
                _LOGGER.warning("Parity disk status issue: %s", status)

            # Check disk state (7 is normal operation)
            if (state := self._parity_info.get("diskState.0", "0")) != "7":
                self._problem_attributes["disk_state"] = f"Abnormal ({state})"
                has_problem = True
                _LOGGER.warning("Parity disk state issue: %s", state)

            # Get and validate SMART data
            smart_data = disk_data.get("smart_data", {})
            if smart_data:
                _LOGGER.debug("Processing SMART data for parity disk")
                
                # Check overall SMART status
                smart_status = smart_data.get("smart_status", True)
                if not smart_status:
                    self._problem_attributes["smart_status"] = "FAILED"
                    has_problem = True
                    _LOGGER.warning("Parity disk has failed SMART status")

                # Process SMART attributes
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
                            "Checking parity disk attribute %s: value=%s, threshold=%s",
                            name,
                            raw_value,
                            threshold
                        )
                        
                        if int(raw_value) > threshold:
                            self._problem_attributes[name.lower()] = raw_value
                            has_problem = True
                            _LOGGER.warning(
                                "Parity disk has high %s: %d (threshold: %d)",
                                name,
                                raw_value,
                                threshold
                            )

                    # Temperature check
                    elif name == "Temperature_Celsius":
                        temp = attr.get("raw", {}).get("value")
                        if temp is not None:
                            _LOGGER.debug("Parity disk temperature from SMART: %d°C", temp)
                            if temp > 55:  # Temperature threshold
                                self._problem_attributes["temperature"] = f"{temp}°C"
                                has_problem = True
                                _LOGGER.warning(
                                    "Parity disk temperature is high: %d°C (threshold: 55°C)",
                                    temp
                                )

            # Log state changes
            if previous_state != has_problem:
                _LOGGER.info(
                    "Parity disk health state changed: %s -> %s",
                    "Problem" if previous_state else "OK",
                    "Problem" if has_problem else "OK"
                )

            # Store final state
            self._last_state = has_problem
            
            if has_problem:
                _LOGGER.warning(
                    "Parity disk has problems: %s",
                    self._problem_attributes
                )
            else:
                _LOGGER.debug("No problems found for parity disk")
            
            return has_problem

        except Exception as err:
            _LOGGER.error(
                "SMART analysis failed for parity disk: %s",
                err,
                exc_info=True
            )
            return self._last_state if self._last_state is not None else False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and bool(self._device)
            and bool(self._parity_info)
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if there's a problem with the disk."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == "parity":
                    # Update spin down delay if changed
                    new_delay = SpinDownDelay(disk.get("spin_down_delay", SpinDownDelay.MINUTES_30))
                    if new_delay != self._spin_down_delay:
                        self._spin_down_delay = new_delay
                        _LOGGER.debug(
                            "Updated spin down delay for %s to %s",
                            "parity",
                            self._spin_down_delay.to_human_readable()
                        )

                    # Get current state
                    current_state = disk.get("state", "unknown").lower()
                    if current_state == "standby":
                        return self._last_state if self._last_state is not None else False

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
                    return self._last_state if self._last_state is not None else False

            return None

        except (KeyError, AttributeError, TypeError, ValueError) as err:
            _LOGGER.debug("Error checking disk health: %s", err)
            return self._last_state if self._last_state is not None else None

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        if self.is_on:
            return "Problem"
        return "OK"

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            # Get current status from array state
            array_state = self.coordinator.data.get("array_state", {})
            disk_status = "active" if array_state.get("state") == "STARTED" else "standby"

            # Build attributes
            attrs = {
                "device": self._device,
                "disk_status": disk_status,
                "power_state": disk_status,
                "spin_down_delay": self._spin_down_delay.to_human_readable(),
                "smart_status": "Failed" if self._last_state else "Passed",
                "disk_serial": self._disk_serial
            }

            # Add temperature if available
            attrs["temperature"] = self._get_temperature_str(
                self._get_temperature(),
                disk_status == "standby"
            )

            # Add disk size information using cached size
            if size := self._parity_info.get("diskSize.0"):
                try:
                    # Get device path
                    device_path = self._parity_info.get("rdevName.0")
                    # Use cached size if available, otherwise use sector calculation
                    if hasattr(self, '_cached_size'):
                        size_bytes = self._cached_size
                    else:
                        size_bytes = int(size) * 512  # Fallback to sector calculation
                    
                    attrs["total_size"] = format_bytes(size_bytes)
                    _LOGGER.debug(
                        "Added disk size for %s: %s (raw sectors: %s)",
                        device_path or "unknown",
                        attrs["total_size"],
                        size
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.error("Error calculating disk size: %s", err)
                    size_bytes = int(size) * 512  # Fallback
                    attrs["total_size"] = format_bytes(size_bytes)

            # Add SMART details if available
            if self._device:
                smart_data = self.coordinator.data.get("smart_data", {}).get(self._device, {})
                if smart_data:
                    attrs["smart_details"] = {
                        "power_on_hours": smart_data.get("power_on_hours"),
                        "status": "Passed" if smart_data.get("smart_status", True) else "Failed",
                        "device_model": smart_data.get("model_name", "Unknown"),
                        "serial_number": smart_data.get("serial_number", "Unknown"),
                        "firmware": smart_data.get("firmware_version", "Unknown")
                    }
                    _LOGGER.debug("Added SMART details: %s", attrs["smart_details"])

            # Add any problem details
            if self._problem_attributes:
                attrs["problem_details"] = self._problem_attributes
                _LOGGER.debug("Added problem details: %s", self._problem_attributes)

            return attrs

        except Exception as err:
            _LOGGER.error("Error getting parity attributes: %s", err)
            return {}

    async def async_update_disk_size(self) -> None:
        """Update disk size asynchronously."""
        try:
            if size := self._parity_info.get("diskSize.0"):
                device_path = self._parity_info.get("rdevName.0")
                if device_path:
                    result = await self.coordinator.api.execute_command(
                        f"lsblk -b -d -o SIZE /dev/{device_path} | tail -n1"
                    )
                    if result.exit_status == 0 and result.stdout.strip():
                        self._cached_size = int(result.stdout.strip())
                        _LOGGER.debug(
                            "Updated cached disk size for %s: %d bytes", 
                            device_path, 
                            self._cached_size
                        )
                    else:
                        self._cached_size = int(size) * 512
                else:
                    self._cached_size = int(size) * 512
        except Exception as err:
            _LOGGER.error("Error updating disk size: %s", err)
            if size:
                self._cached_size = int(size) * 512

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Initialize disk size
        await self.async_update_disk_size()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Schedule disk size update
        asyncio.create_task(self.async_update_disk_size())
        super()._handle_coordinator_update()

class UnraidUPSBinarySensor(UnraidBinarySensorEntity):
    """Binary sensor for UPS monitoring."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize UPS binary sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ups"
        )

        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key="ups_status",
                name=f"{naming.get_entity_name('ups', 'ups')} Status",
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
        _LOGGER.debug(
            "Added binary sensor | description_key: %s | name: %s",
            description.key,
            description.name,
        )

    # Add UPS sensor if UPS info is available
    if coordinator.data.get("system_stats", {}).get("ups_info"):
        entities.append(UnraidUPSBinarySensor(coordinator))
        _LOGGER.debug(
            "Added UPS binary sensor | name: %s",
            "UPS Status",
        )

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
        mount_point = disk.get("mount_point", "")

        # Skip if invalid or already processed
        if not disk_name or disk_name in processed_disks:
            continue

        if is_valid_disk_name(disk_name):
            _LOGGER.debug(
                "Adding health sensor for disk: %s (mount: %s)", 
                disk_name,
                mount_point
            )
            try:
                entities.append(
                    UnraidDiskHealthSensor(
                        coordinator=coordinator,
                        disk_name=disk_name
                    )
                )
                processed_disks.add(disk_name)
                _LOGGER.info(
                    "Added health sensor for %s disk: %s",
                    "pool" if not (disk_name.startswith("disk") or disk_name == "cache") else "array",
                    disk_name
                )
            except ValueError as err:
                _LOGGER.warning("Skipping invalid disk %s: %s", disk_name, err)
                continue

    async_add_entities(entities)
