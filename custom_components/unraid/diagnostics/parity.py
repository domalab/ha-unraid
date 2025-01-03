"""Parity disk monitoring for Unraid."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import BinarySensorDeviceClass # type: ignore
from homeassistant.const import EntityCategory # type: ignore
from homeassistant.core import callback # type: ignore
from homeassistant.helpers.typing import StateType # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidBinarySensorBase
from .const import (
    UnraidBinarySensorEntityDescription,
    PARITY_HISTORY_DATE_FORMAT,
    PARITY_TIME_FORMAT,
    PARITY_FULL_DATE_FORMAT,
    DEFAULT_PARITY_ATTRIBUTES,
)
from ..const import (
    DOMAIN,
    SpinDownDelay,
)
from ..coordinator import UnraidDataUpdateCoordinator
from ..helpers import DiskDataHelperMixin, format_bytes
from ..naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UnraidParityDiskSensor(UnraidBinarySensorBase, DiskDataHelperMixin):
    """Binary sensor for parity disk health with enhanced monitoring."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        parity_info: Dict[str, Any]
    ) -> None:
        """Initialize the parity disk sensor."""
        self._parity_info = parity_info
        self._disk_serial = parity_info.get("diskId.0", "")  # Get serial number
        self._device = parity_info.get("rdevName.0", "").strip()
        
        _LOGGER.debug(
            "Initializing parity disk sensor | device: %s | info: %s",
            self._device,
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
        self._attr_name = f"{naming.clean_hostname()} Parity Health"
        
        # Initialize state variables
        self._last_state: bool | None = None
        self._problem_attributes: Dict[str, Any] = {}
        self._last_smart_check: datetime | None = None
        self._smart_status: bool | None = None
        self._last_temperature: int | None = None
        self._disk_state = "unknown"
        self._cached_size: int | None = None
        
        # Get spin down delay from config
        self._spin_down_delay = self._get_spin_down_delay()

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay for parity disk with fallback."""
        try:
            # Check disk config for parity-specific setting
            disk_cfg = self.coordinator.data.get("disk_config", {})
            
            # Get parity delay (diskSpindownDelay.0)
            delay = disk_cfg.get("diskSpindownDelay.0")
            
            # Handle disk-specific setting if present and not -1
            if delay and delay != "-1":
                _LOGGER.debug("Using parity-specific spin down delay: %s", delay)
                try:
                    return SpinDownDelay(int(delay))
                except ValueError:
                    _LOGGER.warning(
                        "Invalid parity-specific delay value: %s, falling back to global setting",
                        delay
                    )

            # Use global setting
            global_delay = disk_cfg.get("spindownDelay", "0")
            _LOGGER.debug("Using global spin down delay: %s", global_delay)
            
            # Handle special cases for global delay
            if global_delay in (None, "", "-1"):
                return SpinDownDelay.NEVER
                
            return SpinDownDelay(int(global_delay))
            
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for parity disk: %s. Using default Never.",
                err
            )
            return SpinDownDelay.NEVER

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
                _LOGGER.debug(
                    "Using cached temperature for standby parity disk: %d°C",
                    self._last_temperature
                )
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
                            "Updated spin down delay for parity to %s",
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
            _LOGGER.debug("Error checking parity disk health: %s", err)
            return self._last_state if self._last_state is not None else None

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

    def _get_temperature_str(self, temp: int | None, is_standby: bool) -> str:
        """Format temperature string with standby indication."""
        if temp is None:
            return "Unknown"
            
        base_str = f"{temp}°C"
        return f"{base_str} (Standby)" if is_standby else base_str

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        if self.is_on:
            return "Problem"
        return "OK"

class UnraidParityCheckSensor(UnraidBinarySensorBase):
    """Sensor for monitoring Unraid parity check status."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
    ) -> None:
        """Initialize the parity check sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="parity"
        )
        
        description = UnraidBinarySensorEntityDescription(
            key="parity_check",
            name=f"{naming.clean_hostname()} Parity Check",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk-plus",
        )
        
        super().__init__(coordinator, description)
        
        self._attr_name = f"{naming.clean_hostname()} Parity Check Status"
        self._last_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if parity check is running."""
        try:
            array_state = self.coordinator.data.get("array_state", {})
            if array_state.get("state") != "STARTED":
                return False

            # Check if sync action is running
            sync_action = array_state.get("mdResyncAction", "")
            resync_active = int(array_state.get("mdResync", "0")) > 0
            
            return bool(sync_action and sync_action != "IDLE" and resync_active)

        except Exception as err:
            _LOGGER.debug("Error checking parity status: %s", err)
            return self._last_state

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        try:
            array_state = self.coordinator.data.get("array_state", {})
            
            # Check if array is started
            if array_state.get("state") != "STARTED":
                return "Success"  # Default to Success when array not started
                
            # Get sync action and history
            sync_action = array_state.get("mdResyncAction", "")
            history = array_state.get("parity_history", {})
            
            # If sync is running
            if sync_action and sync_action != "IDLE":
                return "Running"
                
            # Return status from history or default to Success
            return history.get("status", "Success")
            
        except Exception as err:
            _LOGGER.debug("Error determining state: %s", err)
            return "Success"  # Default to Success on error

    @property
    def icon(self) -> str:
        """Return the icon based on state."""
        return "mdi:check-circle" if self.state == "Success" else "mdi:progress-check"

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            array_state = self.coordinator.data.get("array_state", {})
            _LOGGER.debug("Current array state: %s", array_state)
            
            # Start with default attributes
            attrs = DEFAULT_PARITY_ATTRIBUTES.copy()
            attrs["next_check"] = self.coordinator.data.get("next_parity_check", "Unknown")

            # Check if sync action is running
            sync_action = array_state.get("mdResyncAction", "")
            resync_active = int(array_state.get("mdResync", "0")) > 0
            
            if sync_action and sync_action != "IDLE" and resync_active:
                _LOGGER.debug("Found active sync action: %s", sync_action)
                
                attrs["status"] = "Running" if sync_action == "check P" else sync_action.capitalize()
                
                self._update_progress(attrs, array_state)
                self._update_speed(attrs, array_state)
                attrs["errors"] = int(array_state.get("mdSyncErrs", 0))
                
                _LOGGER.debug("Current errors: %s", attrs["errors"])
            else:
                attrs["status"] = "Success"

            # Get last check details from history
            if history := array_state.get("parity_history"):
                self._update_history_attributes(attrs, history)

            _LOGGER.debug("Final attributes: %s", attrs)
            return attrs

        except Exception as err:
            _LOGGER.error(
                "Error getting parity attributes: %s",
                err,
                exc_info=True
            )
            return DEFAULT_PARITY_ATTRIBUTES.copy()

    def _update_progress(self, attrs: Dict[str, Any], array_state: Dict[str, Any]) -> None:
        """Update progress information."""
        if (pos := array_state.get("mdResyncPos")) and (
            size := array_state.get("mdResyncSize")
        ):
            try:
                attrs["progress"] = round((int(pos) / int(size)) * 100, 2)
                _LOGGER.debug(
                    "Calculated progress: %s%% (pos=%s, size=%s)",
                    attrs["progress"],
                    pos,
                    size
                )
            except (ValueError, ZeroDivisionError) as err:
                _LOGGER.warning("Error calculating progress: %s", err)
                attrs["progress"] = 0

    def _update_speed(self, attrs: Dict[str, Any], array_state: Dict[str, Any]) -> None:
        """Update speed information."""
        if speed := array_state.get("mdResyncSpeed"):
            try:
                speed_mb = round(float(speed) / (1024 * 1024), 2)
                attrs["speed"] = f"{speed_mb} MB/s"
                _LOGGER.debug("Calculated speed: %s", attrs["speed"])
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Error calculating speed: %s", err)
                attrs["speed"] = "N/A"

    def _update_history_attributes(self, attrs: Dict[str, Any], history: Dict[str, Any]) -> None:
        """Update history attributes."""
        _LOGGER.debug("Found parity history: %s", history)
        try:
            if check_date := history.get("date"):
                parsed_date = datetime.strptime(
                    check_date, 
                    PARITY_HISTORY_DATE_FORMAT
                ).replace(tzinfo=timezone.utc)
                
                now = dt_util.now()
                time_diff = now - parsed_date
                
                if time_diff.days == 0:
                    attrs["last_check"] = f"Today at {parsed_date.strftime(PARITY_TIME_FORMAT)}"
                elif time_diff.days == 1:
                    attrs["last_check"] = f"Yesterday at {parsed_date.strftime(PARITY_TIME_FORMAT)}"
                else:
                    attrs["last_check"] = parsed_date.strftime(PARITY_FULL_DATE_FORMAT)
                
                _LOGGER.debug("Formatted last check date: %s", attrs["last_check"])

            # Add other history details
            attrs["duration"] = history.get("duration", "N/A")
            attrs["last_status"] = history.get("status", "N/A")
            attrs["last_speed"] = history.get("speed", "N/A")
            
            _LOGGER.debug(
                "Added history details: duration=%s, status=%s, speed=%s",
                attrs["duration"],
                attrs["last_status"],
                attrs["last_speed"]
            )

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error formatting history data: %s",
                err,
                exc_info=True
            )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
