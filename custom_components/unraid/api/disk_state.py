"""Disk state management for Unraid."""
from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from enum import Enum

from .disk_utils import is_valid_disk_name

_LOGGER = logging.getLogger(__name__)

class DiskState(Enum):
    """Disk power state."""
    ACTIVE = "active"
    STANDBY = "standby"
    UNKNOWN = "unknown"

class DiskStateManager:
    """Manager for disk state tracking with enhanced detection."""

    def __init__(self, instance: Any):
        self._instance = instance
        self._states: Dict[str, DiskState] = {}
        self._last_check: Dict[str, datetime] = {}
        self._spindown_delays: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._device_types: Dict[str, str] = {}  # Track device types (nvme, sata, etc)
        self._device_paths_cache: Dict[str, str] = {}  # Cache for device paths

    def clear_md_cache(self) -> None:
        """Clear cached MD device paths to force re-resolution."""
        md_devices = [k for k, v in self._device_paths_cache.items() if v.startswith('/dev/md')]
        for device in md_devices:
            del self._device_paths_cache[device]
            _LOGGER.debug("Cleared cached MD device path for %s", device)

    async def _get_device_path(self, device: str) -> str | None:
        """Get actual device path from mount point."""
        try:
            # Check cache first
            if device in self._device_paths_cache:
                _LOGGER.debug("Using cached device path for %s: %s", device, self._device_paths_cache[device])
                return self._device_paths_cache[device]

            mount_cmd = f"findmnt -n -o SOURCE /mnt/{device}"
            _LOGGER.debug("Executing mount command for %s: %s", device, mount_cmd)
            result = await self._instance.execute_command(mount_cmd)
            _LOGGER.debug("Mount command result for %s: exit_code=%d, stdout='%s'", device, result.exit_status, result.stdout.strip())

            if result.exit_status == 0 and (device_path := result.stdout.strip()):
                # If it's an MD device, resolve to underlying physical device
                _LOGGER.debug("Checking if device_path '%s' is MD device (starts with /dev/md: %s, contains p1: %s)",
                             device_path, device_path.startswith('/dev/md'), 'p1' in device_path)
                if device_path.startswith('/dev/md') and 'p1' in device_path:
                    # Extract MD number (e.g., md1 from /dev/md1p1)
                    md_device = device_path.split('p1')[0]  # /dev/md1
                    _LOGGER.debug("Attempting to resolve MD device %s to physical device for %s", md_device, device)
                    physical_device = await self._resolve_md_to_physical(md_device)
                    if physical_device:
                        device_path = physical_device
                        _LOGGER.debug("Resolved MD device %s to physical device %s for %s", md_device, physical_device, device)
                    else:
                        _LOGGER.warning("Failed to resolve MD device %s for %s", md_device, device)

                self._device_paths_cache[device] = device_path
                _LOGGER.debug("Found and cached device path for %s: %s", device, device_path)
                return device_path

            _LOGGER.warning("Could not find device path for %s (exit_code=%d)", device, result.exit_status)
            return None
        except Exception as err:
            _LOGGER.error("Error getting device path for %s: %s", device, err)
            return None

    async def _resolve_md_to_physical(self, md_device: str) -> str | None:
        """Resolve MD device to underlying physical device using mdcmd status."""
        try:
            # Extract MD number (e.g., md1 from /dev/md1)
            md_num = md_device.replace('/dev/md', '')

            # Use mdcmd status to get the mapping
            result = await self._instance.execute_command("mdcmd status")
            if result.exit_status != 0:
                _LOGGER.warning("mdcmd status failed with exit code %d", result.exit_status)
                return None

            # Parse the output to find the physical device for this MD device
            for line in result.stdout.splitlines():
                line = line.strip()
                # Look for diskName.X=mdYp1 where Y matches our MD number
                if line.startswith(f"diskName.") and line.endswith(f"=md{md_num}p1"):
                    # Extract the disk number (X from diskName.X)
                    disk_number = line.split('.')[1].split('=')[0]

                    # Now find the corresponding rdevName.X line
                    for rdev_line in result.stdout.splitlines():
                        rdev_line = rdev_line.strip()
                        if rdev_line.startswith(f"rdevName.{disk_number}="):
                            physical_device = f"/dev/{rdev_line.split('=')[1]}"
                            _LOGGER.debug("Resolved %s to physical device: %s", md_device, physical_device)
                            return physical_device

            _LOGGER.warning("Could not find mapping for MD device %s in mdcmd status", md_device)
            return None
        except Exception as err:
            _LOGGER.error("Error resolving MD device %s: %s", md_device, err)
            return None

    async def get_disk_state(self, device: str) -> DiskState:
        """Get disk state using multiple methods with SMART as primary."""
        try:
            # Initialize result as None at start
            result = None

            # Skip system paths and invalid disk names
            if not is_valid_disk_name(device):
                _LOGGER.debug("Skipping invalid disk name: %s", device)
                return DiskState.UNKNOWN

            # Format device path correctly
            device_path = device
            if not device.startswith('/dev/'):
                if device.startswith('sd'):
                    device_path = f"/dev/{device}"
                elif device == "cache" or device == "garbage":
                    # Check if this is a ZFS pool (either cache or garbage for testing)
                    pool_name = device  # Use the actual pool name
                    zfs_result = await self._instance.execute_command(f"zpool list -H -o name {pool_name} 2>/dev/null")
                    if zfs_result.exit_status == 0 and zfs_result.stdout.strip():
                        _LOGGER.debug(f"{pool_name} is a ZFS pool, setting as ACTIVE")
                        self._device_types[device] = 'zfs'
                        return DiskState.ACTIVE

                    # If not ZFS, try traditional path
                    if actual_path := await self._get_device_path("cache"):
                        device_path = actual_path
                        self._device_types[device] = 'nvme' if 'nvme' in actual_path.lower() else 'sata'
                        return DiskState.ACTIVE
                    _LOGGER.error("Could not find cache device path")
                    return DiskState.UNKNOWN
                elif device.startswith("disk"):
                    # Use actual device path from mount point instead of sequential assignment
                    if actual_path := await self._get_device_path(device):
                        device_path = actual_path
                        _LOGGER.debug("Found device path for %s: %s", device, device_path)
                    else:
                        _LOGGER.error("Could not find device path for %s", device)
                        return DiskState.UNKNOWN
                else:
                    # For custom pools or other disks
                    if actual_path := await self._get_device_path(device):
                        device_path = actual_path
                        _LOGGER.debug("Found device path for %s: %s", device, device_path)
                    else:
                        _LOGGER.error("Could not find device path for %s", device)
                        return DiskState.UNKNOWN

            if device_path not in self._device_types:
                if any(x in str(device_path).lower() for x in ['nvme', 'nvm']):
                    self._device_types[device_path] = 'nvme'
                    _LOGGER.debug("NVMe device detected: %s", device_path)
                    # For NVMe, set state as ACTIVE without running SMART/hdparm
                    return DiskState.ACTIVE
                else:
                    self._device_types[device_path] = 'sata'
                    _LOGGER.debug("SATA device detected: %s", device_path)

            device_type = self._device_types[device_path]
            state = DiskState.UNKNOWN

            if device_type == 'sata':
                # Try SMART first
                smart_cmd = f"smartctl -n standby -j {device_path}"
                _LOGGER.debug("Executing SMART command for %s: %s", device_path, smart_cmd)

                result = await self._instance.execute_command(smart_cmd)
                _LOGGER.debug(
                    "SMART command result for %s: exit_code=%d, stdout='%s', stderr='%s'",
                    device_path,
                    result.exit_status,
                    result.stdout.strip() if result.stdout else "None",
                    result.stderr.strip() if result.stderr else "None"
                )

                # Interpret SMART results
                if result.exit_status == 2:
                    _LOGGER.debug("SMART reports device %s in STANDBY (exit code 2)", device_path)
                    state = DiskState.STANDBY
                elif result.exit_status == 0:
                    _LOGGER.debug("SMART reports device %s is ACTIVE (exit code 0)", device_path)
                    state = DiskState.ACTIVE
                else:
                    # Fallback to hdparm if SMART check fails
                    _LOGGER.debug("SMART check failed (exit code %d), trying hdparm for %s",
                                result.exit_status, device_path)
                    try:
                        hdparm_cmd = f"hdparm -C {device_path}"
                        _LOGGER.debug("Executing hdparm command: %s", hdparm_cmd)

                        result = await self._instance.execute_command(hdparm_cmd)
                        _LOGGER.debug(
                            "hdparm result for %s: exit_code=%d, stdout='%s', stderr='%s'",
                            device_path,
                            result.exit_status,
                            result.stdout.strip() if result.stdout else "None",
                            result.stderr.strip() if result.stderr else "None"
                        )

                        output = result.stdout.lower()
                        if "active" in output or "idle" in output:
                            _LOGGER.debug("hdparm reports device %s is ACTIVE", device_path)
                            state = DiskState.ACTIVE
                        elif "standby" in output:
                            _LOGGER.debug("hdparm reports device %s is in STANDBY", device_path)
                            state = DiskState.STANDBY
                        else:
                            _LOGGER.warning(
                                "Both SMART and hdparm failed to determine state for %s "
                                "(smart_exit=%d, hdparm_output='%s'), assuming ACTIVE",
                                device_path,
                                result.exit_status,
                                output.strip()
                            )
                            state = DiskState.ACTIVE
                    except Exception as err:
                        _LOGGER.warning(
                            "hdparm check failed for %s: %s, SMART exit was %d, assuming ACTIVE",
                            device_path,
                            err,
                            result.exit_status
                        )
                        state = DiskState.ACTIVE
            else:
                # NVMe drives are always active
                state = DiskState.ACTIVE
                _LOGGER.debug("NVMe device %s: always active", device_path)

            # Cache the state
            self._states[device_path] = state
            self._last_check[device_path] = datetime.now(timezone.utc)

            # Log final decision with full context, handle NVMe case
            if device_type == 'nvme':
                _LOGGER.debug(
                    "Final state for %s (%s): %s (NVMe device - no SMART/hdparm check needed)",
                    device_path,
                    device_type,
                    state.value
                )
            else:
                _LOGGER.debug(
                    "Final state for %s (%s): %s (SMART result: %s, hdparm result: %s)",
                    device_path,
                    device_type,
                    state.value,
                    getattr(result, 'exit_status', 'not_run'),
                    getattr(result, 'stdout', 'not_run').strip() if hasattr(result, 'stdout') else 'not_run'
                )
            return state

        except Exception as err:
            _LOGGER.error(
                "Error checking disk state for %s: %s",
                device_path if 'device_path' in locals() else device,
                err,
                exc_info=True
            )
            return DiskState.UNKNOWN

    async def update_spindown_delays(self) -> None:
        """Update disk spin-down delay settings."""
        try:
            result = await self._instance.execute_command("cat /boot/config/disk.cfg")
            if result.exit_status != 0:
                return

            for line in result.stdout.splitlines():
                if line.startswith("spindownDelay="):
                    delay = int(line.split("=")[1].strip('"'))
                    self._spindown_delays["default"] = delay * 60
                elif line.startswith("diskSpindownDelay."):
                    disk_num = line.split(".")[1].split("=")[0]
                    delay = int(line.split("=")[1].strip('"'))
                    if delay >= 0:
                        self._spindown_delays[f"disk{disk_num}"] = delay * 60

        except Exception as err:
            _LOGGER.error("Error updating spin-down delays: %s", err)

    def get_spindown_delay(self, disk_name: str) -> int:
        """Get spin-down delay for disk in seconds."""
        return self._spindown_delays.get(
            disk_name,
            self._spindown_delays.get("default", 1800)
        )
