"""Storage-related sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE # type: ignore
from homeassistant.core import callback # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidSensorBase, ValueValidationMixin
from .const import UnraidSensorEntityDescription
from ..coordinator import UnraidDataUpdateCoordinator
from ..helpers import format_bytes, get_pool_info

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

class StorageUsageMixin(ValueValidationMixin):
    """Mixin for storage usage calculations."""

    def _calculate_usage_percentage(self, total: int, used: int) -> float | None:
        """Calculate storage usage percentage."""
        try:
            if total > 0:
                return round((used / total) * 100, 1)
            return 0.0
        except (TypeError, ZeroDivisionError):
            return None

    def _get_storage_attributes(
        self,
        total: int,
        used: int,
        free: int,
        mount_point: str | None = None,
        device: str | None = None,
    ) -> dict[str, Any]:
        """Get common storage attributes."""
        attrs = {
            "total_size": format_bytes(total),
            "used_space": format_bytes(used),
            "free_space": format_bytes(free),
            "percentage": round((used / total) * 100, 1) if total > 0 else 0,
            "last_update": dt_util.now().isoformat(),
        }

        if mount_point:
            attrs["mount_point"] = mount_point
        if device:
            attrs["device"] = device

        return attrs

class UnraidArraySensor(UnraidSensorBase, StorageUsageMixin):
    """Array usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="array_usage",
            name="Array Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:harddisk",
            suggested_display_precision=1,
            value_fn=self._get_array_usage,
        )
        super().__init__(coordinator, description)
        StorageUsageMixin.__init__(self)

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
        array_state = self.coordinator.data.get("system_stats", {}).get("array_state", {})

        attrs = self._get_storage_attributes(
            array_data.get("total", 0),
            array_data.get("used", 0),
            array_data.get("free", 0)
        )

        if array_state:
            attrs.update({
                "status": array_state.get("state", "unknown"),
                "synced": array_state.get("synced", False),
                "sync_action": array_state.get("sync_action"),
                "sync_progress": array_state.get("sync_progress", 0),
                "sync_errors": array_state.get("sync_errors", 0),
            })

        return attrs

class UnraidDiskSensor(UnraidSensorBase):
    """Representation of an individual Unraid disk usage sensor."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, disk_name: str) -> None:
        """Initialize the sensor."""
        if disk_name == "cache":
            pretty_name = "Cache"
        else:
            disk_number = disk_name.replace('disk', '')
            pretty_name = f"Disk {disk_number}"

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"disk_{disk_name}_usage",
                name=f"{pretty_name} Usage",
                icon=self._get_disk_icon(disk_name),
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=PERCENTAGE,
                value_fn=self._get_disk_usage,
                suggested_display_precision=1,
            ),
        )
        self._disk_name = disk_name
        self._disk_number = disk_number if disk_name.startswith('disk') else None
        self._last_known_device = None
        self._last_update = None
        self._error_count = 0
        self._last_value = None

        # Initial device mapping
        self._device = self._get_disk_device()
        _LOGGER.debug(
            "Initialized disk sensor for %s (device: %s)",
            disk_name,
            self._device or "unknown"
        )

    def _get_disk_icon(self, disk_name: str) -> str:
        """Get appropriate icon for disk type."""
        if disk_name == "cache":
            return "mdi:harddisk"
        return "mdi:harddisk"

    def _get_disk_usage(self, data: dict) -> float | None:
        """Get the disk usage percentage."""
        try:
            # Get disk info from individual_disks array
            for disk in data.get("system_stats", {}).get("individual_disks", []):
                if disk.get("name") == self._disk_name:
                    # For standby disks, return last known percentage
                    if disk.get("status") == "standby":
                        return self._last_value if self._last_value is not None else 0.0

                    # Calculate percentage from total and used if available
                    if "total" in disk and "used" in disk and disk["total"] > 0:
                        percentage = (disk["used"] / disk["total"]) * 100
                        self._last_value = percentage  # Store for standby state
                        return round(percentage, 1)

                    # Fallback to percentage field if available
                    if "percentage" in disk:
                        percentage = float(disk["percentage"])
                        self._last_value = percentage
                        return percentage

            return None

        except (TypeError, ValueError, ZeroDivisionError, KeyError, AttributeError) as err:
            _LOGGER.debug(
                "Error getting disk usage for %s: %s",
                self._disk_name,
                err
            )
            return self._last_value if self._last_value is not None else None

    def _get_disk_device(self) -> str | None:
        """Get the device name from disk mapping with fallback mechanisms."""
        try:
            # Get all disk data
            disks = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            if not disks:
                return self._last_known_device

            # Map array disks in order by disk number
            try:
                array_disks = []
                for disk in disks:
                    if disk.get("name", "").startswith("disk"):
                        try:
                            disk_num = int(''.join(filter(str.isdigit, disk.get("name", ""))))
                            array_disks.append((disk_num, disk))
                        except ValueError:
                            continue
                ordered_disks = [disk for _, disk in sorted(array_disks, key=lambda x: x[0])]

            except (TypeError, ValueError, AttributeError) as err:
                _LOGGER.debug("Error ordering disks: %s", err)
                ordered_disks = []

            # Create device mapping
            device_map = {}
            base_device = 'b'  # Start at sdb for first disk
            for disk in ordered_disks:
                disk_name = disk.get("name")
                if disk_name:
                    device_map[disk_name] = f"sd{base_device}"
                    base_device = chr(ord(base_device) + 1)

            # Try to get device from mapping
            if self._disk_name in device_map:
                self._last_known_device = device_map[self._disk_name]
                self._error_count = 0
                return device_map[self._disk_name]

            return self._last_known_device

        except (KeyError, AttributeError) as err:
            _LOGGER.debug("Error getting disk device for %s: %s", self._disk_name, err)
            return self._last_known_device

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            _LOGGER.debug(
                "Getting attributes for disk %s - Starting attribute collection",
                self._disk_name
            )
            
            # Log available system stats
            system_stats = self.coordinator.data.get("system_stats", {})
            _LOGGER.debug(
                "System stats available keys for %s: %s",
                self._disk_name,
                list(system_stats.keys()) if system_stats else "No system stats"
            )

            disks = system_stats.get("individual_disks", [])
            _LOGGER.debug(
                "Found %d disks in system stats. Looking for disk %s",
                len(disks),
                self._disk_name
            )

            if not disks:
                _LOGGER.warning(
                    "No disks found in system stats for %s",
                    self._disk_name
                )
                return {}

            for disk in disks:
                if disk.get("name") == self._disk_name:
                    _LOGGER.debug(
                        "Found disk %s in system stats. Raw disk data: %s",
                        self._disk_name,
                        disk
                    )

                    # Update and log device mapping
                    previous_device = self._device
                    self._device = self._get_disk_device()
                    _LOGGER.debug(
                        "Device mapping for %s: previous=%s, current=%s",
                        self._disk_name,
                        previous_device,
                        self._device
                    )

                    # Get and log current disk state
                    state = disk.get("state", "unknown")
                    _LOGGER.debug(
                        "Current state for %s: %s",
                        self._disk_name,
                        state
                    )

                    # Temperature processing
                    raw_temp = disk.get("temperature")
                    temp_str = "0°C" if state == "standby" else f"{raw_temp}°C"
                    _LOGGER.debug(
                        "Temperature processing for %s: raw=%s, state=%s, final=%s",
                        self._disk_name,
                        raw_temp,
                        state,
                        temp_str
                    )

                    # Basic attributes
                    attrs = {
                        "mount_point": disk.get("mount_point", "unknown"),
                        "device": self._device or disk.get("device", "unknown"),
                        "status": state,
                        "temperature": temp_str,
                    }
                    _LOGGER.debug(
                        "Basic attributes for %s: %s",
                        self._disk_name,
                        attrs
                    )

                    # Usage information
                    required_keys = ["total", "used", "free"]
                    has_usage_keys = all(k in disk for k in required_keys)
                    _LOGGER.debug(
                        "Usage keys check for %s: required=%s, present=%s",
                        self._disk_name,
                        required_keys,
                        [k for k in required_keys if k in disk]
                    )

                    if has_usage_keys:
                        current_usage = self._get_disk_usage(self.coordinator.data)
                        _LOGGER.debug(
                            "Usage calculation for %s: %s",
                            self._disk_name,
                            current_usage
                        )

                        usage_attrs = {
                            "total_size": format_bytes(disk["total"]),
                            "used_space": format_bytes(disk["used"]),
                            "free_space": format_bytes(disk["free"]),
                            "current_usage": (
                                f"{current_usage:.1f}%"
                                if current_usage is not None
                                else "unknown"
                            ),
                        }
                        attrs.update(usage_attrs)
                        _LOGGER.debug(
                            "Added usage attributes for %s: %s",
                            self._disk_name,
                            usage_attrs
                        )

                    # Device info
                    for extra in ["model", "health"]:
                        if extra in disk:
                            attrs[extra] = disk[extra]
                            _LOGGER.debug(
                                "Added %s info for %s: %s",
                                extra,
                                self._disk_name,
                                disk[extra]
                            )

                    # SMART status
                    smart_data = disk.get("smart_data", {})
                    if smart_data:
                        _LOGGER.debug(
                            "SMART data available for %s: %s",
                            self._disk_name,
                            smart_data
                        )
                        attrs["smart_status"] = (
                            "Passed" if smart_data.get("smart_status", True) else "Failed"
                        )

                    # Spin down delay
                    if "spin_down_delay" in disk:
                        attrs["spin_down_delay"] = disk["spin_down_delay"]
                        _LOGGER.debug(
                            "Spin down delay for %s: %s",
                            self._disk_name,
                            disk["spin_down_delay"]
                        )

                    # NVMe specific attributes
                    if "nvme" in str(self._device).lower():
                        _LOGGER.debug(
                            "Processing NVMe attributes for %s",
                            self._disk_name
                        )
                        nvme_attrs = disk.get("nvme_smart_data", {})
                        _LOGGER.debug(
                            "NVMe SMART data for %s: %s",
                            self._disk_name,
                            nvme_attrs
                        )
                        
                        if nvme_attrs:
                            nvme_specific = {
                                "nvme_available_spare": nvme_attrs.get("available_spare", "unknown"),
                                "nvme_temperature": nvme_attrs.get("temperature", "unknown"),
                                "nvme_critical_warning": nvme_attrs.get("critical_warning", "none"),
                            }
                            attrs.update(nvme_specific)
                            _LOGGER.debug(
                                "Added NVMe attributes for %s: %s",
                                self._disk_name,
                                nvme_specific
                            )

                    _LOGGER.debug(
                        "Final attributes for %s: %s",
                        self._disk_name,
                        attrs
                    )
                    return attrs

            _LOGGER.warning(
                "Disk %s not found in system stats",
                self._disk_name
            )
            return {}

        except (KeyError, AttributeError, ValueError, TypeError) as err:
            _LOGGER.error(
                "Error getting attributes for disk %s: %s. Coordinator data: %s",
                self._disk_name,
                err,
                {
                    k: v for k, v in self.coordinator.data.items() 
                    if k != "system_stats"  # Exclude full system stats for brevity
                },
                exc_info=True
            )
            return {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        return any(
            disk.get("name") == self._disk_name
            for disk in self.coordinator.data.get("system_stats", {})
            .get("individual_disks", [])
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update device mapping and timestamp
        self._device = self._get_disk_device()
        self._last_update = dt_util.utcnow()
        super()._handle_coordinator_update()

class UnraidPoolSensor(UnraidSensorBase, StorageUsageMixin):
    """Storage pool sensor for Unraid."""

    def __init__(self, coordinator, pool_name: str) -> None:
        """Initialize the sensor."""
        self._pool_name = pool_name
        pretty_name = pool_name.title().replace('_', ' ')

        description = UnraidSensorEntityDescription(
            key=f"pool_{pool_name}_usage",
            name=f"{pretty_name} Pool Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon=self._get_pool_icon(),
            suggested_display_precision=1,
            value_fn=self._get_pool_usage,
        )

        super().__init__(coordinator, description)
        StorageUsageMixin.__init__(self)

    def _get_pool_icon(self) -> str:
        """Get appropriate icon for pool type."""
        pool_name = self._pool_name.lower()
        if "cache" in pool_name:
            return "mdi:harddisk"
        elif "nvme" in pool_name:
            return "mdi:harddisk"
        return "mdi:harddisk"

    def _get_pool_usage(self, data: dict) -> float | None:
        """Get pool usage percentage."""
        pool_info = get_pool_info(data.get("system_stats", {}))
        if self._pool_name in pool_info:
            info = pool_info[self._pool_name]
            return self._calculate_usage_percentage(
                info.get("total_size", 0),
                info.get("used_size", 0)
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional pool attributes."""
        try:
            pool_info = get_pool_info(self.coordinator.data.get("system_stats", {}))
            if self._pool_name not in pool_info:
                return {}

            info = pool_info[self._pool_name]
            attrs = self._get_storage_attributes(
                info["total_size"],
                info["used_size"],
                info.get("free_size", 0),
                info.get("mount_point")
            )

            attrs.update({
                "filesystem": info.get("filesystem", "unknown"),
                "device_count": len(info.get("devices", [])),
                "status": info.get("status", "unknown"),
            })

            # Add device details
            for i, device in enumerate(info.get("devices", []), 1):
                attrs[f"device_{i}"] = device

            return attrs

        except (KeyError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting pool attributes: %s", err)
            return {}

class UnraidStorageSensors:
    """Helper class to create all storage sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize storage sensors."""
        self.entities = []

        # Add array sensor
        self.entities.append(UnraidArraySensor(coordinator))

        # Add individual disk sensors
        try:
            # Get disk data with type validation
            disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])
            if not isinstance(disk_data, list):
                _LOGGER.error("Invalid disk data format - expected list, got %s", type(disk_data))
                disk_data = []

            # Define ignored mounts and filesystem types
            ignored_mounts = {
                "disks", "remotes", "addons", "rootshare",
                "user/0", "dev/shm"
            }

            # Track processed disks
            processed_disks = set()

            # Sort array disks first
            array_disks = []
            for disk in disk_data:
                if not isinstance(disk, dict):
                    _LOGGER.warning("Invalid disk entry format: %s", disk)
                    continue

                disk_name = disk.get("name", "")
                mount_point = disk.get("mount_point", "")
                filesystem = disk.get("filesystem", "")

                # Skip if invalid, already processed, tmpfs, or ignored mount
                if (
                    not disk_name
                    or disk_name in processed_disks
                    or filesystem == "tmpfs"
                    or any(mount in mount_point for mount in ignored_mounts)
                ):
                    continue

                # Collect array disks for sorting
                if disk_name.startswith("disk"):
                    try:
                        disk_num = int(''.join(filter(str.isdigit, disk_name)))
                        array_disks.append((disk_num, disk))
                    except ValueError:
                        _LOGGER.warning("Invalid disk number format: %s", disk_name)
                        continue
                # Process cache disk immediately
                elif disk_name == "cache":
                    try:
                        self.entities.append(
                            UnraidDiskSensor(
                                coordinator=coordinator,
                                disk_name=disk_name
                            )
                        )
                        processed_disks.add(disk_name)
                        _LOGGER.debug("Added disk sensor for: %s", disk_name)
                    except ValueError as err:
                        _LOGGER.warning(
                            "Error adding disk sensor for %s: %s",
                            disk_name,
                            err
                        )

            # Process sorted array disks
            for _, disk in sorted(array_disks, key=lambda x: x[0]):
                try:
                    disk_name = disk.get("name", "")
                    if disk_name not in processed_disks:
                        self.entities.append(
                            UnraidDiskSensor(
                                coordinator=coordinator,
                                disk_name=disk_name
                            )
                        )
                        processed_disks.add(disk_name)
                        _LOGGER.debug("Added disk sensor for: %s", disk_name)
                except ValueError as err:
                    _LOGGER.warning(
                        "Error adding disk sensor for %s: %s",
                        disk_name,
                        err
                    )
                    continue

        except (TypeError, KeyError, AttributeError) as err:
            _LOGGER.error("Error setting up disk sensors: %s", err)

        # Add pool sensors
        try:
            pool_info = get_pool_info(coordinator.data.get("system_stats", {}))
            for pool_name in pool_info:
                self.entities.append(UnraidPoolSensor(coordinator, pool_name))
                _LOGGER.debug("Added pool sensor for: %s", pool_name)
        except (TypeError, KeyError, AttributeError, ValueError) as err:
            _LOGGER.error("Error setting up pool sensors: %s", err)
