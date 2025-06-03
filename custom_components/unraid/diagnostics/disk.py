"""Array disk health monitoring for Unraid."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from homeassistant.components.binary_sensor import BinarySensorDeviceClass # type: ignore
from homeassistant.const import EntityCategory # type: ignore
from homeassistant.helpers.typing import StateType # type: ignore

from .base import UnraidBinarySensorBase
from .const import UnraidBinarySensorEntityDescription
from ..const import SpinDownDelay
from ..coordinator import UnraidDataUpdateCoordinator
from ..helpers import (
    DiskDataHelperMixin,
    get_disk_identifiers,
    get_disk_number,
)
from ..api.disk_mapping import get_unraid_disk_mapping
# from ..helpers import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UnraidArrayDiskSensor(UnraidBinarySensorBase, DiskDataHelperMixin):
    """Binary sensor for array disk health monitoring."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        disk_name: str,
    ) -> None:
        """Initialize the array disk health sensor."""
        if not disk_name.startswith("disk"):
            raise ValueError(f"Not an array disk: {disk_name}")

        self._disk_name = disk_name
        self._disk_num = get_disk_number(disk_name)

        if self._disk_num is None:
            raise ValueError(f"Invalid array disk number: {disk_name}")

        # Entity naming not used in this class
        # EntityNaming(
        #     domain=DOMAIN,
        #     hostname=coordinator.hostname,
        #     component="disk"
        # )

        description = UnraidBinarySensorEntityDescription(
            key=f"disk_health_{disk_name}",
            name=f"{disk_name.capitalize()} Health",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk",
            has_warning_threshold=True,
        )

        super().__init__(coordinator, description)

        # Get device and serial from helpers
        self._device, self._serial = get_disk_identifiers(coordinator.data, disk_name)

        # Initialize tracking variables
        self._last_smart_check: datetime | None = None
        self._smart_status: bool | None = None
        self._last_problem_state: bool | None = None
        self._spin_down_delay = self._get_spin_down_delay()
        self._last_temperature: int | None = None
        self._problem_attributes: Dict[str, Any] = {}

        _LOGGER.debug(
            "Initialized array disk sensor | disk: %s | device: %s | serial: %s",
            disk_name,
            self._device or "unknown",
            self._serial or "unknown"
        )

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay for this array disk."""
        try:
            disk_cfg = self.coordinator.data.get("disk_config", {})

            # Get global setting (default to NEVER/0 if not specified)
            global_setting = disk_cfg.get("spindownDelay", "0")
            if global_setting in (None, "", "-1"):
                return SpinDownDelay.NEVER

            global_delay = int(global_setting)

            # Check for disk-specific setting
            disk_delay = disk_cfg.get(f"diskSpindownDelay.{self._disk_num}")
            if disk_delay and disk_delay != "-1":  # -1 means use global setting
                try:
                    return SpinDownDelay(int(disk_delay))
                except ValueError:
                    _LOGGER.warning(
                        "Invalid disk-specific delay value for %s: %s, using global setting",
                        self._disk_name,
                        disk_delay
                    )

            return SpinDownDelay(global_delay)

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for %s: %s. Using default Never.",
                self._disk_name,
                err
            )
            return SpinDownDelay.NEVER

    def _analyze_smart_status(self, disk_data: Dict[str, Any]) -> bool:
        """Analyze SMART status and attributes for array disk problems."""
        self._problem_attributes = {}

        try:
            _LOGGER.debug(
                "Starting SMART analysis for array disk %s with data: %s",
                self._disk_name,
                {k: v for k, v in disk_data.items() if k not in ['smart_data']}
            )

            # Check disk state using proper standby detection
            disk_state = disk_data.get("state", "unknown").lower()
            _LOGGER.debug("Array disk %s current state: %s", self._disk_name, disk_state)

            if disk_state == "standby":
                _LOGGER.debug(
                    "Array disk %s is in standby, using cached state: %s",
                    self._disk_name,
                    self._last_problem_state
                )
                return self._last_problem_state if self._last_problem_state is not None else False

            has_problem = False

            # Get and validate SMART data
            smart_data = disk_data.get("smart_data", {})
            if not smart_data:
                _LOGGER.debug("No SMART data available for array disk %s", self._disk_name)
                return self._last_problem_state if self._last_problem_state is not None else False

            # Check overall SMART status
            smart_status = smart_data.get("smart_status", True)
            _LOGGER.debug("Array disk %s SMART status: %s", self._disk_name, smart_status)

            if not smart_status:
                self._problem_attributes["smart_status"] = "FAILED"
                has_problem = True
                _LOGGER.warning(
                    "Array disk %s has failed SMART status",
                    self._disk_name
                )

            # Process SMART attributes
            attributes = smart_data.get("ata_smart_attributes", {}).get("table", [])

            # Map of critical attributes and their thresholds for raw values
            critical_attrs = {
                "Reallocated_Sector_Ct": 0,
                "Current_Pending_Sector": 0,
                "Offline_Uncorrectable": 0,
                "Reallocated_Event_Count": 0,
                "Reported_Uncorrect": 0
            }

            # Attributes that should be evaluated based on normalized values, not raw values
            normalized_attrs = {
                "UDMA_CRC_Error_Count": True,
                "Command_Timeout": True
            }

            # Process each attribute
            for attr in attributes:
                name = attr.get("name")
                if not name:
                    continue

                # Check if this is a normalized attribute (like Command_Timeout or UDMA_CRC_Error_Count)
                if name in normalized_attrs:
                    # For these attributes, we check if the normalized value is below threshold
                    # or if the attribute has failed according to SMART
                    normalized_value = attr.get("value", 100)  # Default to 100 (good)
                    threshold_value = attr.get("thresh", 0)    # Default to 0 (minimum threshold)
                    when_failed = attr.get("when_failed", "")

                    # Only consider it a problem if the normalized value is below threshold
                    # or if SMART has marked it as failed
                    if normalized_value < threshold_value or when_failed:
                        raw_value = attr.get("raw", {}).get("value", 0)
                        try:
                            raw_value_int = int(raw_value)
                        except (ValueError, TypeError):
                            raw_value_int = 0

                        self._problem_attributes[name.lower()] = raw_value_int
                        has_problem = True
                        _LOGGER.warning(
                            "Array disk %s has failing %s: normalized value %d below threshold %d",
                            self._disk_name,
                            name,
                            normalized_value,
                            threshold_value
                        )
                    else:
                        # Log high raw values at debug level only
                        raw_value = attr.get("raw", {}).get("value", 0)
                        try:
                            raw_value_int = int(raw_value)
                        except (ValueError, TypeError):
                            raw_value_int = 0

                        _LOGGER.debug(
                            "Array disk %s has high %s raw value: %d, but normalized value %d is above threshold %d",
                            self._disk_name,
                            name,
                            raw_value_int,
                            normalized_value,
                            threshold_value
                        )

                # Check critical attributes based on raw values
                elif name in critical_attrs:
                    raw_value = attr.get("raw", {}).get("value", 0)
                    threshold = critical_attrs[name]

                    # Ensure raw_value is a valid integer
                    try:
                        raw_value_int = int(raw_value)
                    except (ValueError, TypeError):
                        _LOGGER.debug(
                            "Invalid %s value for array disk %s: %s",
                            name,
                            self._disk_name,
                            raw_value
                        )
                        continue

                    _LOGGER.debug(
                        "Checking %s for array disk %s: value=%s, threshold=%s",
                        name,
                        self._disk_name,
                        raw_value_int,
                        threshold
                    )

                    if raw_value_int > threshold:
                        self._problem_attributes[name.lower()] = raw_value_int
                        has_problem = True
                        _LOGGER.warning(
                            "Array disk %s has high %s: %d (threshold: %d)",
                            self._disk_name,
                            name,
                            raw_value_int,
                            threshold
                        )

                # Temperature check
                elif name == "Temperature_Celsius":
                    temp = attr.get("raw", {}).get("value")
                    if temp is not None:
                        # Ensure temperature is a valid integer
                        try:
                            temp_int = int(temp)
                            # Sanity check - temperature should be between 0 and 100°C
                            if temp_int < 0 or temp_int > 100:
                                _LOGGER.debug(
                                    "Invalid temperature value for array disk %s: %s°C",
                                    self._disk_name,
                                    temp
                                )
                                continue

                            _LOGGER.debug(
                                "Array disk %s temperature: %d°C",
                                self._disk_name,
                                temp_int
                            )
                            if temp_int > 55:  # Temperature threshold
                                self._problem_attributes["temperature"] = f"{temp_int}°C"
                                has_problem = True
                                _LOGGER.warning(
                                    "Array disk %s temperature is high: %d°C (threshold: 55°C)",
                                    self._disk_name,
                                    temp_int
                                )
                        except (ValueError, TypeError):
                            _LOGGER.debug(
                                "Invalid temperature value for array disk %s: %s",
                                self._disk_name,
                                temp
                            )

            # Store final state
            self._last_problem_state = has_problem

            if has_problem:
                _LOGGER.warning(
                    "Array disk %s has problems: %s",
                    self._disk_name,
                    self._problem_attributes
                )
            else:
                _LOGGER.debug(
                    "No problems found for array disk %s",
                    self._disk_name
                )

            return has_problem

        except Exception as err:
            _LOGGER.error(
                "SMART analysis failed for array disk %s: %s",
                self._disk_name,
                err,
                exc_info=True
            )
            return self._last_problem_state if self._last_problem_state is not None else False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        try:
            # Check if disk exists in coordinator data
            disks = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            disk_exists = any(disk["name"] == self._disk_name for disk in disks)

            return self.coordinator.last_update_success and disk_exists

        except Exception as err:
            _LOGGER.debug(
                "Error checking availability for array disk %s: %s",
                self._disk_name,
                err
            )
            return False

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
                            "Updated spin down delay for array disk %s to %s",
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
            _LOGGER.debug("Error checking array disk health: %s", err)
            return self._last_problem_state if self._last_problem_state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Get current disk state
                    is_standby = disk.get("state", "unknown").lower() == "standby"

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
                    if not is_standby and temp is not None:
                        self._last_temperature = temp

                    attrs["Temperature"] = self._get_temperature_str(
                        self._last_temperature if is_standby else temp,
                        is_standby
                    )

                    # Add SMART status
                    if smart_data := disk.get("smart_data", {}):
                        attrs["SMART Status"] = (
                            "Passed" if smart_data.get("smart_status", True)
                            else "Failed"
                        )

                    # Add spin down delay
                    attrs["Spin Down Delay"] = self._spin_down_delay.to_human_readable()

                    # Add any problem details
                    if self._problem_attributes:
                        attrs["problem_details"] = self._problem_attributes

                    return attrs

            return {}

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Missing key in array disk data: %s", err)
            return {}

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        if self.is_on:
            return "Problem"
        return "OK"
