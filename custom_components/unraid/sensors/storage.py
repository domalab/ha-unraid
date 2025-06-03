"""Storage-related sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import ( # type: ignore
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE # type: ignore
from homeassistant.core import callback # type: ignore
import homeassistant.util.dt as dt_util

from .base import UnraidSensorBase
from .const import UnraidSensorEntityDescription
from ..coordinator import UnraidDataUpdateCoordinator
from ..helpers import (
    DiskDataHelperMixin,
    format_bytes,
    get_disk_identifiers,
    get_pool_info
)

# from ..helpers import EntityNaming

_LOGGER = logging.getLogger(__name__)

def get_disk_number(disk_name: str) -> int | None:
    """Extract disk number from disk name with enhanced error handling."""
    try:
        if not disk_name.startswith("disk"):
            return None
        # Extract only digits after "disk"
        number_str = ''.join(filter(str.isdigit, disk_name))
        return int(number_str) if number_str else None
    except (ValueError, AttributeError):
        return None

def sort_array_disks(disks: list[dict]) -> list[dict]:
    """Sort array disks by disk number with validation."""
    try:
        # Filter valid array disks and extract numbers
        array_disks = []
        for disk in disks:
            name = disk.get("name", "")
            if not name.startswith("disk"):
                continue

            disk_num = get_disk_number(name)
            if disk_num is not None:
                array_disks.append((disk_num, disk))

        # Sort by disk number and return only the disk dictionaries
        return [disk for _, disk in sorted(array_disks, key=lambda x: x[0])]

    except (TypeError, ValueError, AttributeError) as err:
        _LOGGER.debug("Error sorting disks: %s", err)
        return list(disks)  # Return original list on error

class UnraidDiskSensor(UnraidSensorBase, DiskDataHelperMixin):
    """Representation of an individual Unraid disk usage sensor."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        disk_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._disk_name = disk_name
        self._disk_number = get_disk_number(disk_name)
        self._last_value: Optional[float] = None
        self._last_temperature: Optional[int] = None



        # Get pretty name with capitalized first letter
        pretty_name = disk_name.capitalize()

        # Initialize base sensor class
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"disk_{disk_name}_usage",
                name=f"{pretty_name} Usage",
                icon="mdi:harddisk",
                device_class=None,  # Removed POWER_FACTOR
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=PERCENTAGE,
                value_fn=self._get_disk_usage,
                suggested_display_precision=1,
            ),
        )

        # Initialize DiskDataHelperMixin
        DiskDataHelperMixin.__init__(self)

        # Get device and serial using the helper
        self._device, self._serial = get_disk_identifiers(coordinator.data, disk_name)

        _LOGGER.debug(
            "Initialized disk sensor for %s (device: %s, serial: %s)",
            disk_name,
            self._device or "unknown",
            self._serial or "unknown"
        )

    def _get_disk_usage(self, data: dict) -> float | None:
        """Get the disk usage percentage."""
        try:
            # Get disk info from individual_disks array
            for disk in data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == self._disk_name:
                    is_standby = disk.get("state") == "standby"

                    # Calculate percentage from total and used
                    if "total" in disk and "used" in disk:
                        percentage = self._calculate_usage_percentage(
                            disk["total"],
                            disk["used"]
                        )
                        if percentage is not None:
                            self._last_value = percentage

                    # Fallback to percentage field if available
                    elif "percentage" in disk:
                        percentage = float(disk["percentage"])
                        self._last_value = percentage

                    # For standby state, return last known value
                    if is_standby:
                        return self._last_value if self._last_value is not None else 0.0

                    return self._last_value

            return None

        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error getting disk usage for %s: %s",
                self._disk_name,
                err
            )
            return self._last_value if self._last_value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == self._disk_name:
                    # Get device and serial using helper
                    device, serial = get_disk_identifiers(self.coordinator.data, self._disk_name)

                    is_standby = disk.get("state") == "standby"

                    # Base attributes using DiskDataHelperMixin method
                    attrs = self._get_storage_attributes(
                        total=disk.get("total", 0),
                        used=disk.get("used", 0),
                        free=disk.get("free", 0),
                        mount_point=disk.get("mount_point"),
                        device=device,
                        is_standby=is_standby
                    )

                    # Add device and serial information
                    attrs.update({
                        "Device": device or "Unknown",
                        "Disk Serial": serial or "Unknown",
                        "Power State": "Standby" if is_standby else "Active",
                    })

                    # Handle temperature using helper method
                    temp = disk.get("temperature")
                    if not is_standby and temp is not None:
                        self._last_temperature = temp

                    attrs["Temperature"] = self._get_temperature_str(
                        self._last_temperature if is_standby else temp,
                        is_standby
                    )

                    # Add current usage with standby handling
                    attrs["Current Usage"] = (
                        "N/A (Standby)" if is_standby
                        else f"{self._get_disk_usage(self.coordinator.data):.1f}%"
                    )

                    # Add additional disk information
                    if "health" in disk:
                        attrs["Health Status"] = disk["health"]
                    if "spin_down_delay" in disk:
                        attrs["Spin Down Delay"] = disk["spin_down_delay"]

                    return attrs

            return {}

        except Exception as err:
            _LOGGER.error(
                "Error getting disk attributes: %s",
                err,
                exc_info=True
            )
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update device and serial using helper
        new_device, new_serial = get_disk_identifiers(self.coordinator.data, self._disk_name)

        # Log device changes
        if new_device != self._device:
            _LOGGER.debug(
                "Device mapping changed for %s: %s -> %s",
                self._disk_name,
                self._device or "unknown",
                new_device or "unknown"
            )
            self._device = new_device

        # Update serial if changed
        if new_serial != self._serial:
            _LOGGER.debug(
                "Serial changed for %s: %s -> %s",
                self._disk_name,
                self._serial or "unknown",
                new_serial or "unknown"
            )
            self._serial = new_serial

        super()._handle_coordinator_update()

class UnraidArraySensor(UnraidSensorBase, DiskDataHelperMixin):
    """Array usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""


        description = UnraidSensorEntityDescription(
            key="array_usage",
            name="Array Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=None,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:harddisk",
            suggested_display_precision=1,
            value_fn=self._get_array_usage,
        )
        super().__init__(coordinator, description)
        DiskDataHelperMixin.__init__(self)

    def _get_array_usage(self, data: dict) -> float | None:
        """Get array usage percentage."""
        array_data = data.get("system_stats", {}).get("array_usage", {})
        return self._calculate_usage_percentage(
            array_data.get("total", 0),
            array_data.get("used", 0)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        array_data = self.coordinator.data.get("system_stats", {}).get("array_usage", {})

        # Get storage attributes with improved formatting
        attrs = self._get_storage_attributes(
            array_data.get("total", 0),
            array_data.get("used", 0),
            array_data.get("free", 0)
        )

        # Add array-specific attributes (not duplicating Array Status sensor)
        attrs.update({
            "Disk Status": self._format_disk_status(),
            "Capacity Status": self._format_capacity_status(array_data),
            "Last Updated": dt_util.now().isoformat(),
        })

        return attrs

    def _format_disk_status(self) -> str:
        """Format disk status summary for array."""
        try:
            array_state = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_state:
                return "Unknown"

            total_disks = array_state.get("num_disks", 0)
            disabled = array_state.get("num_disabled", 0)
            invalid = array_state.get("num_invalid", 0)
            missing = array_state.get("num_missing", 0)

            healthy = total_disks - disabled - invalid - missing

            if total_disks == 0:
                return "No Disks"
            elif healthy == total_disks:
                return f"All {total_disks} Disks Healthy"
            else:
                issues = []
                if disabled > 0:
                    issues.append(f"{disabled} Failed")
                if invalid > 0:
                    issues.append(f"{invalid} Invalid")
                if missing > 0:
                    issues.append(f"{missing} Missing")

                return f"{healthy}/{total_disks} Healthy ({', '.join(issues)})"
        except Exception:
            return "Unknown"

    def _format_capacity_status(self, array_data: dict) -> str:
        """Format capacity status for array."""
        try:
            total = array_data.get("total", 0)
            used = array_data.get("used", 0)

            if total == 0:
                return "No Capacity"

            usage_pct = (used / total) * 100

            if usage_pct < 70:
                return "Good"
            elif usage_pct < 85:
                return "Moderate"
            elif usage_pct < 95:
                return "High"
            else:
                return "Critical"
        except Exception:
            return "Unknown"

class UnraidPoolSensor(UnraidSensorBase, DiskDataHelperMixin):
    """Storage pool and solid state drive sensor for Unraid."""

    def __init__(self, coordinator, pool_name: str) -> None:
        """Initialize the sensor."""
        # Set initial values first
        self._pool_name = pool_name
        self._last_value: Optional[float] = None
        self._last_temperature: Optional[int] = None

        # Get device and serial using the helper BEFORE using them in get_pool_icon
        self._device, self._serial = get_disk_identifiers(coordinator.data, pool_name)



        # Get pretty name with capitalized first letter
        pretty_name = pool_name.capitalize()

        # Initialize base sensor class
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"pool_{pool_name}_usage",
                name=f"{pretty_name} Usage",
                native_unit_of_measurement=PERCENTAGE,
                device_class=None,
                state_class=SensorStateClass.MEASUREMENT,
                icon=self._get_pool_icon(),  # Now _device is available
                suggested_display_precision=1,
                value_fn=self._get_usage,
            ),
        )

        # Initialize DiskDataHelperMixin
        DiskDataHelperMixin.__init__(self)

    def _get_pool_icon(self) -> str:
        """Get appropriate icon based on device type."""
        pool_name = self._pool_name.lower()
        try:
            # ZFS support removed

            # Check for NVMe devices
            if (self._device and "nvme" in self._device.lower()) or "nvme" in pool_name:
                return "mdi:harddisk"
        except (AttributeError, KeyError) as err:
            _LOGGER.debug(
                "Error determining icon for pool %s: %s",
                self._pool_name,
                err
            )
        return "mdi:harddisk"

    def _get_usage(self, data: dict) -> float | None:
        """Get usage percentage for the pool or SSD."""
        try:
            # First check individual disks for direct device
            for disk in data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == self._pool_name:
                    return self._calculate_usage_percentage(
                        disk.get("total", 0),
                        disk.get("used", 0)
                    )

            # Fallback to pool data
            pool_info = get_pool_info(data.get("system_stats", {}))
            if self._pool_name in pool_info:
                info = pool_info[self._pool_name]
                return self._calculate_usage_percentage(
                    info.get("total_size", 0),
                    info.get("used_size", 0)
                )

            return None

        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error getting usage: %s", err)
            return self._last_value if self._last_value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            # First try to get individual disk data
            for disk in self.coordinator.data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == self._pool_name:
                    device, serial = get_disk_identifiers(
                        self.coordinator.data,
                        self._pool_name
                    )

                    is_standby = disk.get("state") == "standby"

                    attrs = self._get_storage_attributes(
                        total=disk.get("total", 0),
                        used=disk.get("used", 0),
                        free=disk.get("free", 0),
                        mount_point=disk.get("mount_point"),
                        device=device,
                        is_standby=is_standby
                    )

                    attrs.update({
                        "Device": device or "Unknown",
                        "Disk Serial": serial or "Unknown",
                        "Power State": "Standby" if is_standby else "Active",
                        "Filesystem": disk.get("filesystem", "Unknown"),
                    })

                    # Handle temperature
                    temp = disk.get("temperature")
                    if not is_standby and temp is not None:
                        self._last_temperature = temp

                    attrs["Temperature"] = self._get_temperature_str(
                        self._last_temperature if is_standby else temp,
                        is_standby
                    )

                    return attrs

            # Fallback to pool data
            pool_info = get_pool_info(self.coordinator.data.get("system_stats", {}))
            if self._pool_name in pool_info:
                info = pool_info[self._pool_name]
                return {
                    "Filesystem": info.get("filesystem", "Unknown"),
                    "Device Count": len(info.get("devices", [])),
                    "Mount Point": info.get("mount_point", "Unknown"),
                    "Total Size": format_bytes(info.get("total_size", 0)),
                    "Used Space": format_bytes(info.get("used_size", 0)),
                    "Free Space": format_bytes(info.get("free_size", 0)),
                }

            return {}

        except Exception as err:
            _LOGGER.error("Error getting attributes: %s", err)
            return {}

class UnraidStorageSensors:
    """Helper class to create all storage sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize storage sensors."""
        self.entities = []

        # Add array sensor
        self.entities.append(UnraidArraySensor(coordinator))


