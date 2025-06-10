"""Array status and health binary sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, Any

from homeassistant.const import EntityCategory
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
import homeassistant.util.dt as dt_util

from .base import UnraidBinarySensorBase
from .const import UnraidBinarySensorEntityDescription
from ..coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

class UnraidArrayStatusBinarySensor(UnraidBinarySensorBase):
    """Binary sensor for array status monitoring."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize array status binary sensor."""
        description = UnraidBinarySensorEntityDescription(
            key="array_status",
            name="Array Status",
            device_class=None,  # Remove device_class to use custom state strings
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk-plus",
        )

        super().__init__(coordinator, description)

        _LOGGER.debug(
            "Initialized Array Status binary sensor | name: %s",
            self._attr_name
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if the array is started/running."""
        try:
            # Try to get array_state first (from batched command)
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            # Get state from the data
            if isinstance(array_data, dict):
                state = array_data.get("state", "unknown").lower()
            elif isinstance(array_data, str):
                state = array_data.lower()
            else:
                state = "unknown"

            # Return True if array is started
            return state == "started"

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting array status: %s", err)
            return None

    @property
    def state(self) -> str:
        """Return the state of the binary sensor as a string."""
        if self.is_on is True:
            return "Started"
        elif self.is_on is False:
            return "Stopped"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return additional state attributes."""
        try:
            # Try to get array_state first (from batched command)
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            # If array_data is a string, just return the raw state
            if isinstance(array_data, str):
                return {
                    "Array State": self._format_array_state(array_data),
                    "Last Updated": dt_util.now().isoformat(),
                }

            # Otherwise, extract all the attributes with user-friendly formatting
            return {
                "Array State": self._format_array_state(array_data.get("state", "unknown")),
                "Parity Synchronized": self._format_boolean(array_data.get("synced", False)),
                "Current Operation": self._format_sync_action(array_data.get("sync_action")),
                "Operation Progress": self._format_sync_progress(array_data.get("sync_progress", 0)),
                "Operation Errors": self._format_sync_errors(array_data.get("sync_errors", 0)),
                "Total Disks": self._format_disk_count(array_data.get("num_disks", 0)),
                "Disabled Disks": self._format_disabled_disks(array_data.get("num_disabled", 0)),
                "Invalid Disks": self._format_invalid_disks(array_data.get("num_invalid", 0)),
                "Missing Disks": self._format_missing_disks(array_data.get("num_missing", 0)),
                "Last Updated": dt_util.now().isoformat(),
            }
        except Exception as err:
            _LOGGER.debug("Error getting array attributes: %s", err)
            return {}

    def _format_array_state(self, state: str) -> str:
        """Format array state to user-friendly description."""
        if not state:
            return "Unknown"

        state_upper = state.upper()
        state_mappings = {
            "STARTED": "Array Running",
            "STOPPED": "Array Stopped",
            "STARTING": "Array Starting",
            "STOPPING": "Array Stopping",
            "UNKNOWN": "Status Unknown",
            "ERROR": "Array Error"
        }
        return state_mappings.get(state_upper, state.title())

    def _format_boolean(self, value: bool) -> str:
        """Format boolean values to Yes/No."""
        return "Yes" if value else "No"

    def _format_sync_action(self, action: str) -> str:
        """Format sync action to user-friendly description."""
        if not action or action == "IDLE":
            return "None"

        action_mappings = {
            "check P": "Parity Check",
            "check": "Parity Check",
            "recon P": "Parity Rebuild",
            "recon": "Data Rebuild",
            "clear": "Disk Clear",
            "sync": "Synchronizing"
        }
        return action_mappings.get(action, action.title())

    def _format_sync_progress(self, progress: float) -> str:
        """Format sync progress with percentage."""
        if progress == 0:
            return "Not Running"
        return f"{progress:.1f}%"

    def _format_sync_errors(self, errors: int) -> str:
        """Format sync errors count."""
        if errors == 0:
            return "None"
        elif errors == 1:
            return "1 Error"
        else:
            return f"{errors} Errors"

    def _format_disk_count(self, count: int) -> str:
        """Format disk count."""
        if count == 0:
            return "No Disks"
        elif count == 1:
            return "1 Disk"
        else:
            return f"{count} Disks"

    def _format_disabled_disks(self, count: int) -> str:
        """Format disabled disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Failed/Offline)"
        else:
            return f"{count} Disks (Failed/Offline)"

    def _format_invalid_disks(self, count: int) -> str:
        """Format invalid disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Wrong/Unrecognized)"
        else:
            return f"{count} Disks (Wrong/Unrecognized)"

    def _format_missing_disks(self, count: int) -> str:
        """Format missing disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Not Present)"
        else:
            return f"{count} Disks (Not Present)"


class UnraidArrayHealthSensor(UnraidBinarySensorBase):
    """Binary sensor for overall array health monitoring."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize array health binary sensor."""
        description = UnraidBinarySensorEntityDescription(
            key="array_health",
            name="Array Health",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk-plus",
        )

        super().__init__(coordinator, description)

        _LOGGER.debug(
            "Initialized Array Health binary sensor | name: %s",
            self._attr_name
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if there are array health problems."""
        try:
            health_status = self._get_overall_health_status()
            # For problem device class: True = problem detected, False = no problems
            return not health_status["healthy"]

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting array health status: %s", err)
            return None

    @property
    def state(self) -> str | None:
        """Return the state of the sensor."""
        if self.is_on is True:
            return "Problem"
        elif self.is_on is False:
            return "Healthy"
        return None

    def _get_overall_health_status(self) -> Dict[str, Any]:
        """Get overall array health status by checking all components."""
        health_status = {
            "healthy": True,
            "problems": [],
            "component_status": {}
        }

        # Check array operational status
        array_running = self._check_array_status()
        health_status["component_status"]["array_status"] = array_running
        if not array_running:
            health_status["healthy"] = False
            health_status["problems"].append("Array not started")

        # Check comprehensive disk health
        disk_health = self._check_disk_health()
        health_status["component_status"]["disk_health"] = disk_health

        # Check for any failed disks across all types
        failed_disks = []
        if disk_health["array_failed"]:
            failed_disks.extend([f"Array disk {disk}" for disk in disk_health["array_failed"]])
        if disk_health["parity_failed"]:
            failed_disks.append("Parity disk")
        if disk_health["pool_failed"]:
            failed_disks.extend([f"Pool disk {disk}" for disk in disk_health["pool_failed"]])

        if failed_disks:
            health_status["healthy"] = False
            health_status["problems"].extend([f"{disk} health failed" for disk in failed_disks])

        # Check parity health
        parity_health = self._check_parity_health()
        health_status["component_status"]["parity_health"] = parity_health
        if not parity_health:
            health_status["healthy"] = False
            health_status["problems"].append("Parity health issues")

        # Check pool health
        pool_health = self._check_pool_health()
        health_status["component_status"]["pool_health"] = pool_health
        if pool_health["failed_pools"]:
            health_status["healthy"] = False
            health_status["problems"].extend([
                f"Pool {pool} health failed" for pool in pool_health["failed_pools"]
            ])

        # Check for missing/failed disks from mdcmd
        missing_disks = self._check_missing_disks()
        health_status["component_status"]["missing_disks"] = missing_disks
        if missing_disks > 0:
            health_status["healthy"] = False
            health_status["problems"].append(f"{missing_disks} missing disk(s)")

        return health_status

    def _check_array_status(self) -> bool:
        """Check if array is running."""
        try:
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            if isinstance(array_data, dict):
                state = array_data.get("state", "unknown").lower()
            elif isinstance(array_data, str):
                state = array_data.lower()
            else:
                state = "unknown"

            return state == "started"
        except Exception:
            return False

    def _check_disk_health(self) -> Dict[str, Any]:
        """Check health of all disks using spindown-aware logic - comprehensive overview."""
        disk_status = {
            # Array data disks
            "array_healthy": [],
            "array_failed": [],
            "array_standby": [],
            "array_total": 0,
            # Parity disk
            "parity_healthy": False,
            "parity_failed": False,
            "parity_standby": False,
            "parity_total": 0,
            # Pool disks (cache, ZFS, etc.)
            "pool_healthy": [],
            "pool_failed": [],
            "pool_standby": [],
            "pool_total": 0,
            # Overall totals
            "total_physical_disks": 0,
            "total_healthy": 0,
            "total_failed": 0,
            "total_standby": 0
        }

        try:
            # First, check parity disk from array state data
            parity_info = self._get_parity_disk_info()
            if parity_info:
                disk_status["parity_total"] = 1
                disk_status["total_physical_disks"] += 1

                parity_state = self._get_parity_disk_state(parity_info)
                if parity_state == "standby":
                    disk_status["parity_standby"] = True
                    disk_status["total_standby"] += 1
                    _LOGGER.debug("Parity disk %s is in standby, treating as healthy (spindown-aware)", parity_info.get("device", "unknown"))
                elif parity_state == "failed":
                    disk_status["parity_failed"] = True
                    disk_status["total_failed"] += 1
                else:
                    disk_status["parity_healthy"] = True
                    disk_status["total_healthy"] += 1

            # Then check individual disks from disk data
            disk_data = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            processed_disks = set()

            for disk in disk_data:
                disk_name = disk.get("name", "")
                disk_state = disk.get("state", "unknown").lower()
                mount_point = disk.get("mount_point", "")
                filesystem = disk.get("filesystem", "")

                # Skip if already processed or is a duplicate entry
                if disk_name in processed_disks:
                    _LOGGER.debug("Skipping duplicate disk entry: %s", disk_name)
                    continue

                # Determine disk type and process accordingly
                if disk_name.startswith("disk"):
                    # Array data disk
                    processed_disks.add(disk_name)
                    disk_status["array_total"] += 1
                    disk_status["total_physical_disks"] += 1

                    health_result = self._check_individual_disk_health(disk, "array")
                    if health_result["status"] == "healthy":
                        disk_status["array_healthy"].append(disk_name)
                        disk_status["total_healthy"] += 1
                    elif health_result["status"] == "failed":
                        disk_status["array_failed"].append(disk_name)
                        disk_status["total_failed"] += 1
                    elif health_result["status"] == "standby":
                        disk_status["array_standby"].append(disk_name)
                        disk_status["total_standby"] += 1

                elif self._is_pool_disk(disk):
                    # Pool disk (cache, ZFS, etc.) - but not ZFS device entries
                    if not self._is_zfs_device_entry(disk):
                        processed_disks.add(disk_name)
                        disk_status["pool_total"] += 1
                        disk_status["total_physical_disks"] += 1

                        # For ZFS pools, check actual underlying device state
                        if filesystem == "zfs":
                            health_result = self._check_zfs_pool_disk_health(disk)
                        else:
                            health_result = self._check_individual_disk_health(disk, "pool")

                        if health_result["status"] == "healthy":
                            disk_status["pool_healthy"].append(disk_name)
                            disk_status["total_healthy"] += 1
                        elif health_result["status"] == "failed":
                            disk_status["pool_failed"].append(disk_name)
                            disk_status["total_failed"] += 1
                        elif health_result["status"] == "standby":
                            disk_status["pool_standby"].append(disk_name)
                            disk_status["total_standby"] += 1
                else:
                    _LOGGER.debug(
                        "Skipping non-storage disk: %s (filesystem: %s, mount: %s)",
                        disk_name, filesystem, mount_point
                    )

        except Exception as err:
            _LOGGER.debug("Error checking comprehensive disk health: %s", err)

        return disk_status

    def _get_parity_disk_info(self) -> Dict[str, Any]:
        """Get parity disk information from raw array state data."""
        try:
            # Access the same raw array state data that the parity sensor uses
            # This is stored directly in the coordinator data, not under system_stats
            raw_array_data = None

            # First try to get from the parity sensor's data source
            if hasattr(self.coordinator, 'data') and 'array_state' in self.coordinator.data:
                raw_array_data = self.coordinator.data['array_state']
                _LOGGER.debug("Found raw array_state data at top level")

            # Fallback to system_stats location
            if not raw_array_data:
                raw_array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
                _LOGGER.debug("Checking array_state under system_stats")

            # Also check if it's stored under a different key structure
            if not raw_array_data and hasattr(self.coordinator, 'data'):
                # Look for any key that might contain the raw array state
                for key, value in self.coordinator.data.items():
                    if isinstance(value, dict) and 'rdevName.0' in value:
                        raw_array_data = value
                        _LOGGER.debug("Found raw array_state data under key: %s", key)
                        break

            if isinstance(raw_array_data, dict) and raw_array_data:
                # Look for parity disk in raw array state (rdevName.0 for parity)
                parity_device = raw_array_data.get("rdevName.0", "")
                if parity_device:
                    _LOGGER.debug("Found parity disk in raw array_state: %s", parity_device)
                    return {
                        "device": parity_device,
                        "status": raw_array_data.get("rdevStatus.0", ""),
                        "size": raw_array_data.get("rdevSize.0", "0"),
                        "errors": raw_array_data.get("rdevNumErrors.0", "0"),
                        "disk_state": raw_array_data.get("diskState.0", "0")
                    }
                else:
                    _LOGGER.debug("No rdevName.0 found in raw array_state, checking available keys: %s", list(raw_array_data.keys())[:10])
            else:
                _LOGGER.debug("Raw array state data not found or not a dict: %s", type(raw_array_data))

            _LOGGER.debug("No parity disk found in raw array_state")
            return {}
        except Exception as err:
            _LOGGER.debug("Error getting parity disk info: %s", err)
            return {}

    def _get_parity_disk_state(self, parity_info: Dict[str, Any]) -> str:
        """Check the actual power state of the parity disk."""
        try:
            parity_device = parity_info.get("device", "")
            if not parity_device:
                return "unknown"

            # Check if parity disk is in standby using SMART data first (most reliable)
            if hasattr(self.coordinator, 'api') and hasattr(self.coordinator.api, 'disk_state_manager'):
                try:
                    # Check the state of the parity device directly
                    device_path = f"/dev/{parity_device}"
                    state_result = self.coordinator.api.disk_state_manager.get_disk_state(device_path)
                    if state_result and state_result.get("state") == "standby":
                        _LOGGER.debug("Parity disk %s confirmed in standby via disk state manager", parity_device)
                        return "standby"
                    elif state_result and state_result.get("state") == "active":
                        _LOGGER.debug("Parity disk %s confirmed active via disk state manager", parity_device)
                        # Continue to check other sources for confirmation
                except Exception as e:
                    _LOGGER.debug("Could not check parity disk state via disk state manager: %s", e)

            # Check individual_disks data for the parity device
            disk_data = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            for disk in disk_data:
                disk_name = disk.get("name", "")
                device_path = disk.get("device", "")

                # Check if this disk corresponds to the parity device
                if (disk_name == "parity" or
                    device_path == f"/dev/{parity_device}" or
                    (device_path and parity_device in device_path) or
                    (disk_name and parity_device in disk_name)):

                    disk_state = disk.get("state", "unknown").lower()
                    if disk_state == "standby":
                        _LOGGER.debug("Parity disk %s found in individual_disks as standby", parity_device)
                        return "standby"
                    elif disk_state == "active":
                        _LOGGER.debug("Parity disk %s found in individual_disks as active", parity_device)
                        # Don't return here, continue checking other sources
                        break

            # Check disk state from array state data (less reliable for power state)
            disk_state = parity_info.get("disk_state", "0")
            try:
                disk_state_int = int(disk_state)
                # Note: diskState in array state doesn't directly indicate power state
                # It indicates array membership state, not power state
                _LOGGER.debug("Parity disk %s array state: %s (this is array membership, not power state)", parity_device, disk_state)
            except (ValueError, TypeError):
                _LOGGER.debug("Invalid disk_state value for parity disk %s: %s", parity_device, disk_state)

            # Check SMART status for health (not power state)
            parity_status = parity_info.get("status", "")
            if parity_status == "DISK_OK":
                _LOGGER.debug("Parity disk %s has DISK_OK status", parity_device)
                # Since we couldn't determine standby state definitively,
                # and the disk is healthy, assume it's in the same state as array disks
                # Check if array disks are in standby
                array_disks_standby = self._are_array_disks_in_standby()
                if array_disks_standby:
                    _LOGGER.debug("Parity disk %s assumed to be in standby (array disks are in standby)", parity_device)
                    return "standby"
                else:
                    _LOGGER.debug("Parity disk %s assumed to be healthy and active", parity_device)
                    return "healthy"
            elif parity_status in ["DISK_INVALID", "DISK_MISSING"]:
                _LOGGER.debug("Parity disk %s has failed status: %s", parity_device, parity_status)
                return "failed"
            else:
                _LOGGER.debug("Parity disk %s has unknown status: %s, treating as healthy", parity_device, parity_status)
                return "healthy"  # Default to healthy for unknown states

        except Exception as err:
            _LOGGER.debug("Error checking parity disk state: %s", err)
            return "healthy"

    def _are_array_disks_in_standby(self) -> bool:
        """Check if array disks are in standby mode."""
        try:
            disk_data = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            array_disk_count = 0
            standby_count = 0

            for disk in disk_data:
                disk_name = disk.get("name", "")
                if disk_name.startswith("disk"):
                    array_disk_count += 1
                    disk_state = disk.get("state", "unknown").lower()
                    if disk_state == "standby":
                        standby_count += 1

            # If most array disks are in standby, assume parity follows the same pattern
            if array_disk_count > 0:
                standby_ratio = standby_count / array_disk_count
                _LOGGER.debug("Array disks standby ratio: %d/%d (%.1f%%)", standby_count, array_disk_count, standby_ratio * 100)
                return standby_ratio >= 0.5  # If 50% or more are in standby

            return False
        except Exception as err:
            _LOGGER.debug("Error checking array disk standby state: %s", err)
            return False

    def _is_zfs_device_entry(self, disk: Dict[str, Any]) -> bool:
        """Check if this is a ZFS device entry (not the pool itself)."""
        mount_point = disk.get("mount_point", "")
        return mount_point.startswith("ZFS device (") and mount_point.endswith(")")

    def _check_zfs_pool_disk_health(self, disk: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of a ZFS pool disk by examining the underlying device state."""
        disk_name = disk.get("name", "")

        try:
            # First check if the pool itself reports as standby
            disk_state = disk.get("state", "unknown").lower()
            if disk_state == "standby":
                _LOGGER.debug("ZFS pool %s is directly reported as standby", disk_name)
                return {"status": "standby", "reason": "pool reported as standby"}

            # For ZFS pools, we need to check the actual underlying device state
            # Look for the corresponding ZFS device entry
            disk_data = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])
            for zfs_device in disk_data:
                zfs_mount = zfs_device.get("mount_point", "")
                if (zfs_mount.startswith("ZFS device (") and
                    zfs_mount.endswith(f") in pool '{disk_name}'")):

                    # Extract the device path from the mount point
                    device_path = zfs_mount.split("ZFS device (")[1].split(")")[0]
                    _LOGGER.debug("Found ZFS pool %s underlying device: %s", disk_name, device_path)

                    # Check if the underlying device is in standby
                    if hasattr(self.coordinator, 'api') and hasattr(self.coordinator.api, 'disk_state_manager'):
                        try:
                            state_result = self.coordinator.api.disk_state_manager.get_disk_state(device_path)
                            if state_result and state_result.get("state") == "standby":
                                _LOGGER.debug("ZFS pool %s underlying device %s is in standby", disk_name, device_path)
                                return {"status": "standby", "reason": "underlying device in standby"}
                            elif state_result:
                                _LOGGER.debug("ZFS pool %s underlying device %s state: %s", disk_name, device_path, state_result.get("state"))
                        except Exception as e:
                            _LOGGER.debug("Could not check ZFS pool %s device %s state: %s", disk_name, device_path, e)

                    # Also check the ZFS device entry state
                    zfs_device_state = zfs_device.get("state", "unknown").lower()
                    if zfs_device_state == "standby":
                        _LOGGER.debug("ZFS pool %s device entry shows standby", disk_name)
                        return {"status": "standby", "reason": "ZFS device entry in standby"}

                    break

            # If we can't determine standby state, treat as healthy
            _LOGGER.debug("ZFS pool %s state could not be determined, treating as healthy", disk_name)
            return {"status": "healthy", "reason": "ZFS pool state unknown, treated as healthy"}

        except Exception as err:
            _LOGGER.debug("Error checking ZFS pool disk health for %s: %s", disk_name, err)
            return {"status": "healthy", "reason": "error checking state, treated as healthy"}

    def _check_individual_disk_health(self, disk: Dict[str, Any], disk_type: str) -> Dict[str, Any]:
        """Check health of an individual disk with spindown awareness."""
        disk_name = disk.get("name", "")
        disk_state = disk.get("state", "unknown").lower()

        # Check disk power state first
        if disk_state == "standby":
            _LOGGER.debug(
                "%s disk %s is in standby, treating as healthy (spindown-aware)",
                disk_type.title(), disk_name
            )
            return {"status": "standby", "reason": "disk in standby mode"}

        # Only check SMART status for active disks
        smart_data = disk.get("smart_data", {})
        if smart_data:
            # Check actual SMART status from smart_data
            smart_status = smart_data.get("smart_status", True)
            if smart_status:
                return {"status": "healthy", "reason": "SMART data shows healthy"}
            else:
                _LOGGER.warning(
                    "%s disk %s has genuine SMART failure",
                    disk_type.title(), disk_name
                )
                return {"status": "failed", "reason": "SMART failure detected"}
        else:
            # No SMART data available but disk is active - check basic status
            basic_smart_status = disk.get("smart_status", "").lower()
            if basic_smart_status == "passed":
                return {"status": "healthy", "reason": "basic SMART status passed"}
            elif basic_smart_status == "failed":
                _LOGGER.warning(
                    "%s disk %s marked as failed in basic status",
                    disk_type.title(), disk_name
                )
                return {"status": "failed", "reason": "basic SMART status failed"}
            else:
                # Unknown status for active disk - treat as healthy to avoid false alarms
                _LOGGER.debug(
                    "%s disk %s has unknown SMART status, treating as healthy",
                    disk_type.title(), disk_name
                )
                return {"status": "healthy", "reason": "unknown status treated as healthy"}

    def _is_parity_disk(self, disk: Dict[str, Any]) -> bool:
        """Check if disk is a parity disk."""
        disk_name = disk.get("name", "")
        mount_point = disk.get("mount_point", "")

        # Check if it's explicitly named parity or has parity characteristics
        return (
            disk_name == "parity" or
            mount_point == "/mnt/parity" or
            # Check if it's part of the parity array (no mount point, used for parity)
            (not mount_point.startswith("/mnt/") and disk_name not in ["user", "user0"])
        )

    def _is_pool_disk(self, disk: Dict[str, Any]) -> bool:
        """Check if disk is a pool disk (cache, ZFS, etc.)."""
        disk_name = disk.get("name", "")
        mount_point = disk.get("mount_point", "")
        filesystem = disk.get("filesystem", "")

        # Pool disks have specific characteristics
        return (
            # Must not be an array disk or parity
            not disk_name.startswith("disk") and
            disk_name not in ["user", "user0", "parity"] and
            # Must have a proper mount point (pools are mounted)
            mount_point.startswith("/mnt/") and
            # Must have a recognized filesystem
            filesystem in ["btrfs", "zfs", "xfs", "ext4", "reiserfs"] and
            # Exclude boot device
            not mount_point.startswith("/boot")
        )

    def _check_parity_health(self) -> bool:
        """Check parity disk health."""
        try:
            # Check if parity info exists and is healthy
            parity_info = self.coordinator.data.get("parity_info", {})
            if not parity_info:
                return True  # No parity configured is not an error

            # Check parity disk status
            parity_status = parity_info.get("rdevStatus.0", "")
            return parity_status == "DISK_OK"

        except Exception as err:
            _LOGGER.debug("Error checking parity health: %s", err)
            return False

    def _check_pool_health(self) -> Dict[str, Any]:
        """Check health of all pools (cache, etc.) using spindown-aware logic."""
        pool_status = {
            "healthy_pools": [],
            "failed_pools": [],
            "standby_pools": [],
            "total_pools": 0
        }

        try:
            disk_data = self.coordinator.data.get("system_stats", {}).get("individual_disks", [])

            # Define what constitutes actual storage pools vs other devices
            known_pools = set()

            for disk in disk_data:
                disk_name = disk.get("name", "")
                mount_point = disk.get("mount_point", "")
                filesystem = disk.get("filesystem", "")

                # Only count actual storage pools, not individual disks or system devices
                is_actual_pool = (
                    # Must not be an array disk
                    not disk_name.startswith("disk") and
                    # Must not be system mounts
                    disk_name not in ["user", "user0", "parity"] and
                    # Must have a proper mount point (pools are mounted)
                    mount_point.startswith("/mnt/") and
                    # Must have a recognized filesystem
                    filesystem in ["btrfs", "zfs", "xfs", "ext4", "reiserfs"] and
                    # Exclude boot device
                    not mount_point.startswith("/boot")
                )

                if is_actual_pool:
                    # Avoid counting the same pool multiple times (e.g., multi-device pools)
                    if disk_name not in known_pools:
                        known_pools.add(disk_name)
                        pool_status["total_pools"] += 1

                        _LOGGER.debug(
                            "Detected storage pool: %s (filesystem: %s, mount: %s)",
                            disk_name, filesystem, mount_point
                        )

                        # Check disk power state first
                        disk_state = disk.get("state", "unknown").lower()

                        if disk_state == "standby":
                            # Pool is spun down - don't consider this a health problem
                            pool_status["standby_pools"].append(disk_name)
                            _LOGGER.debug(
                                "Pool %s is in standby, treating as healthy (spindown-aware)",
                                disk_name
                            )
                            continue

                        # Only check SMART status for active pools
                        smart_data = disk.get("smart_data", {})
                        if smart_data:
                            # Check actual SMART status from smart_data
                            smart_status = smart_data.get("smart_status", True)
                            if smart_status:
                                pool_status["healthy_pools"].append(disk_name)
                            else:
                                pool_status["failed_pools"].append(disk_name)
                                _LOGGER.warning(
                                    "Pool %s has genuine SMART failure",
                                    disk_name
                                )
                        else:
                            # No SMART data available but pool is active - check basic status
                            basic_smart_status = disk.get("smart_status", "").lower()
                            if basic_smart_status == "passed":
                                pool_status["healthy_pools"].append(disk_name)
                            elif basic_smart_status == "failed":
                                # For pools, "failed" might be normal (e.g., ZFS pools show as failed)
                                # Only flag as problem if there are actual error indicators
                                pool_status["healthy_pools"].append(disk_name)
                                _LOGGER.debug(
                                    "Pool %s shows 'failed' status but treating as healthy (pools often show this)",
                                    disk_name
                                )
                            else:
                                # Unknown status for active pool - treat as healthy
                                pool_status["healthy_pools"].append(disk_name)
                                _LOGGER.debug(
                                    "Pool %s has unknown SMART status, treating as healthy",
                                    disk_name
                                )
                else:
                    _LOGGER.debug(
                        "Skipping non-pool device: %s (filesystem: %s, mount: %s)",
                        disk_name, filesystem, mount_point
                    )

        except Exception as err:
            _LOGGER.debug("Error checking pool health: %s", err)

        return pool_status

    def _check_missing_disks(self) -> int:
        """Check for missing disks from array state."""
        try:
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if isinstance(array_data, dict):
                return int(array_data.get("num_missing", 0))
            return 0
        except Exception:
            return 0

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return user-friendly state attributes."""
        try:
            health_status = self._get_overall_health_status()
            component_status = health_status["component_status"]

            # Core status information
            attrs = {
                "status": "Healthy" if health_status["healthy"] else "Attention Required",
                "array_operational": "Yes" if component_status.get("array_status", False) else "No",
            }

            # Problems summary (only show if there are issues)
            problems = health_status["problems"]
            if problems:
                attrs["issues_detected"] = problems

            # Comprehensive disk summary
            disk_health = component_status.get("disk_health", {})

            # Total physical disks overview
            total_physical = disk_health.get("total_physical_disks", 0)
            total_healthy = disk_health.get("total_healthy", 0)
            total_failed = disk_health.get("total_failed", 0)
            total_standby = disk_health.get("total_standby", 0)

            if total_physical > 0:
                if total_failed > 0:
                    attrs["total_disks"] = f"{total_failed} failed, {total_healthy} healthy, {total_standby} sleeping of {total_physical} total"
                elif total_standby == total_physical:
                    attrs["total_disks"] = f"All {total_physical} disks sleeping (energy saving)"
                elif total_healthy == total_physical:
                    attrs["total_disks"] = f"All {total_physical} disks healthy and active"
                else:
                    attrs["total_disks"] = f"{total_healthy} active, {total_standby} sleeping of {total_physical} total"
            else:
                attrs["total_disks"] = "No disks detected"

            # Array data disks breakdown
            array_total = disk_health.get("array_total", 0)
            array_healthy = len(disk_health.get("array_healthy", []))
            array_failed = len(disk_health.get("array_failed", []))
            array_standby = len(disk_health.get("array_standby", []))

            if array_total > 0:
                if array_failed > 0:
                    attrs["array_disks"] = f"{array_failed} failed, {array_healthy} healthy, {array_standby} sleeping"
                elif array_standby == array_total:
                    attrs["array_disks"] = f"All {array_total} array disks sleeping"
                elif array_healthy == array_total:
                    attrs["array_disks"] = f"All {array_total} array disks healthy"
                else:
                    attrs["array_disks"] = f"{array_healthy} active, {array_standby} sleeping"
            else:
                attrs["array_disks"] = "No array disks detected"

            # Parity disk status
            parity_total = disk_health.get("parity_total", 0)
            if parity_total > 0:
                if disk_health.get("parity_failed", False):
                    attrs["parity_disk"] = "Failed"
                elif disk_health.get("parity_standby", False):
                    attrs["parity_disk"] = "Sleeping (energy saving)"
                elif disk_health.get("parity_healthy", False):
                    attrs["parity_disk"] = "Healthy and active"
                else:
                    attrs["parity_disk"] = "Status unknown"
            else:
                attrs["parity_disk"] = "No parity disk detected"

            # Pool disks status with actual power states
            pool_total = disk_health.get("pool_total", 0)
            pool_healthy = len(disk_health.get("pool_healthy", []))  # These are active pools
            pool_failed = len(disk_health.get("pool_failed", []))
            pool_standby = len(disk_health.get("pool_standby", []))

            if pool_total > 0:
                if pool_failed > 0:
                    attrs["pool_disks"] = f"{pool_failed} failed, {pool_healthy} active, {pool_standby} sleeping"
                elif pool_standby == pool_total:
                    attrs["pool_disks"] = f"All {pool_total} pool disks sleeping"
                elif pool_healthy == pool_total:
                    attrs["pool_disks"] = f"All {pool_total} pool disks active"
                else:
                    attrs["pool_disks"] = f"{pool_healthy} active, {pool_standby} sleeping"
            else:
                attrs["pool_disks"] = "No pool disks detected"



            # Parity protection status
            parity_healthy = component_status.get("parity_health", False)
            attrs["parity_protection"] = "Active and healthy" if parity_healthy else "Issues detected"

            # Missing disks warning
            missing_disks = component_status.get("missing_disks", 0)
            if missing_disks > 0:
                attrs["missing_disks"] = f"{missing_disks} disk{'s' if missing_disks != 1 else ''} missing"

            # Action required summary (only show when action is needed)
            if not health_status["healthy"]:
                critical_issues = [p for p in problems if any(word in p.lower() for word in ["failed", "missing", "error"])]
                if critical_issues:
                    attrs["action_required"] = "Immediate attention - hardware issues detected"
                else:
                    attrs["action_required"] = "Review system status"

            # Last check timestamp
            attrs["last_checked"] = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")

            return attrs

        except Exception as err:
            _LOGGER.debug("Error getting array health attributes: %s", err)
            return {
                "status": "Unknown",
                "action_required": "Unable to determine system status",
                "last_checked": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
