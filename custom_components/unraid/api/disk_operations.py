"""Disk operations for Unraid."""
from __future__ import annotations

import asyncio
import logging
import aiofiles # type: ignore
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
import re
import json
from datetime import datetime

from .disk_utils import is_valid_disk_name
from .disk_mapper import DiskMapper
from .smart_operations import SmartDataManager
from .disk_state import DiskState, DiskStateManager
from .error_handling import with_error_handling, safe_parse

_LOGGER = logging.getLogger(__name__)

@dataclass
class DiskInfo:
    """Disk information from smartctl."""
    name: str
    device: str
    model: str = "Unknown"
    status: str = "unknown"
    health: str = "Unknown"
    temperature: Optional[int] = None
    size: int = 0

class SmartAttribute:
    """SMART attribute with validation."""
    def __init__(self, attr_id: str, name: str, value: str, raw_value: str):
        self.attr_id = attr_id
        self.name = name
        self.value = value
        self.raw_value = raw_value

    @property
    def normalized_value(self) -> Optional[int]:
        """Get normalized value with validation."""
        try:
            return int(self.value)
        except (ValueError, TypeError):
            return None

    @property
    def normalized_raw(self) -> Optional[int]:
        """Get normalized raw value."""
        try:
            if "Temperature" in self.name and "(" in self.raw_value:
                temp = self.raw_value.split("(")[0].strip()
                return int(temp)
            match = re.search(r'\d+', self.raw_value)
            return int(match.group(0)) if match else None
        except (ValueError, TypeError):
            return None

class DiskOperationsMixin:
    """Mixin for disk-related operations."""

    def __init__(self):
        """Initialize disk operations."""
        super().__init__()
        _LOGGER.debug("Initializing DiskOperationsMixin")
        self._disk_operations = self

        self._disk_cache: Dict[str, Dict[str, Any]] = {}
        self._smart_thresholds = {
            "Raw_Read_Error_Rate": {"warn": 50, "crit": 30},
            "Reallocated_Sector_Ct": {"warn": 10, "crit": 20},
            "Current_Pending_Sector": {"warn": 1, "crit": 5},
            "Offline_Uncorrectable": {"warn": 1, "crit": 5},
            "Temperature_Celsius": {"warn": 50, "crit": 60},
            "UDMA_CRC_Error_Count": {"warn": 100, "crit": 200},
        }

        self._smart_manager = SmartDataManager(self)
        self._state_manager = DiskStateManager(self)
        _LOGGER.debug("Created SmartDataManager and DiskStateManager")

        self._disk_lock = asyncio.Lock()
        self._cached_disk_info: Dict[str, DiskInfo] = {}
        self._last_update: Dict[str, datetime] = {}
        self._update_interval = 60  # seconds

    @property
    def disk_operations(self) -> 'DiskOperationsMixin':
        """Return self as disk operations interface."""
        return self

    async def initialize(self) -> None:
        """Initialize disk operations."""
        _LOGGER.debug("Starting disk operations initialization")
        try:
            await self._state_manager.update_spindown_delays()
            _LOGGER.debug("Updated spin-down delays successfully")

            # Log the current disk states
            for disk in await self.get_individual_disk_usage():
                if disk_name := disk.get("name"):
                    try:
                        state = await self._state_manager.get_disk_state(disk_name)
                        _LOGGER.debug("Initial state for disk %s: %s", disk_name, state.value)
                    except Exception as err:
                        _LOGGER.warning("Could not get initial state for disk %s: %s", disk_name, err)

        except Exception as err:
            _LOGGER.error("Error during disk operations initialization: %s", err)

    @with_error_handling(fallback_return={})
    async def get_disk_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive disk mappings including serials."""
        async with self._disk_lock:
            # Use the new DiskMapper class
            disk_mapper = DiskMapper(self.execute_command)
            disk_identifiers = await disk_mapper.refresh_mappings()

            # Convert DiskIdentifier objects to dictionaries for backward compatibility
            mappings = {}
            for disk_name, identifier in disk_identifiers.items():
                mappings[disk_name] = {
                    "name": disk_name,
                    "device": identifier.device or "",
                    "serial": identifier.serial or "",
                    "status": identifier.status,
                    "filesystem": identifier.filesystem or "",
                    "spindown_delay": identifier.spindown_delay
                }

            if not mappings:
                _LOGGER.warning("No disk mappings found from any source")
            else:
                _LOGGER.debug("Found disk mappings: %s", mappings)

            return mappings

    async def _get_array_status(self) -> str:
        """Get Unraid array status using mdcmd."""
        try:
            result = await self.execute_command("mdcmd status")
            if result.exit_status != 0:
                return "unknown"

            status_dict = {}
            for line in result.stdout.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    status_dict[key] = value.strip()

            state = status_dict.get("mdState", "").upper()
            if state == "STARTED":
                if status_dict.get("mdResyncAction"):
                    return f"syncing_{status_dict['mdResyncAction'].lower()}"
                return "started"
            elif state == "STOPPED":
                return "stopped"
            else:
                return state.lower()

        except (OSError, ValueError) as err:
            _LOGGER.error("Error getting array status: %s", err)
            return "error"

    async def update_disk_status(self, disk_info: Dict[str, Any]) -> Dict[str, Any]:
        """Update disk status information."""
        try:
            device = disk_info.get("device")
            disk_name = disk_info.get("name")

            if not disk_name:
                return disk_info

            # Get disk mappings to get serial
            mappings = await self.get_disk_mappings()
            if disk_name in mappings:
                disk_info["serial"] = mappings[disk_name].get("serial")
                _LOGGER.debug("Added serial for disk %s: %s",
                            disk_name, disk_info.get("serial"))

            # Map device name to proper device path
            if not device:
                if disk_name.startswith("disk"):
                    try:
                        disk_num = int(''.join(filter(str.isdigit, disk_name)))
                        device = f"sd{chr(ord('b') + disk_num - 1)}"
                    except ValueError:
                        _LOGGER.error("Invalid disk name format: %s", disk_name)
                        return disk_info
                elif disk_name == "cache":
                    device = "nvme0n1"

            disk_info["device"] = device

            # Get disk state using mapped device
            state = await self._state_manager.get_disk_state(disk_name)
            disk_info["state"] = state.value

            # Only get SMART data if disk is active
            if state == DiskState.ACTIVE and device:
                smart_data = await self._smart_manager.get_smart_data(device)
                if smart_data:
                    disk_info.update({
                        "smart_status": "Passed" if smart_data.get("smart_status") else "Failed",
                        "temperature": smart_data.get("temperature"),
                        "power_on_hours": smart_data.get("power_on_hours"),
                        "smart_data": smart_data
                    })

            return disk_info

        except Exception as err:
            _LOGGER.error("Error updating disk status: %s", err)
            return disk_info

    @with_error_handling(fallback_return="Unknown")
    async def get_disk_model(self, device: str) -> str:
        """Get disk model with enhanced error handling."""
        smart_data = await self._smart_manager.get_smart_data(device)
        if smart_data:
            return smart_data.get("model_name", "Unknown")
        return "Unknown"

    @with_error_handling(fallback_return={"default": 0})
    async def get_disk_spin_down_settings(self) -> dict[str, int]:
        """Fetch disk spin down delay settings with validation."""
        config_path = "/boot/config/disk.cfg"
        default_delay = 0
        disk_delays = {}

        try:
            async with aiofiles.open(config_path, mode='r') as f:
                settings = await f.read()
        except FileNotFoundError:
            _LOGGER.warning("Disk config file not found: %s", config_path)
            return {"default": default_delay}

        for line in settings.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                if line.startswith("spindownDelay="):
                    value = line.split("=")[1].strip().strip('"')
                    default_delay = safe_parse(int, value, default=0,
                                             error_msg=f"Invalid default spindown delay: {value}")
                elif line.startswith("diskSpindownDelay."):
                    disk_num = line.split(".")[1].split("=")[0]
                    value = line.split("=")[1].strip().strip('"')

                    if not disk_num.isdigit():
                        continue

                    disk_name = f"disk{disk_num}"
                    delay = safe_parse(int, value, default=default_delay,
                                     error_msg=f"Invalid spindown delay for {disk_name}: {value}")
                    disk_delays[disk_name] = (
                        default_delay if delay < 0 else delay
                    )

            except (ValueError, IndexError) as err:
                _LOGGER.warning(
                    "Invalid spin down setting '%s': %s",
                    line,
                    err
                )
                continue

        return {"default": default_delay, **disk_delays}

    @with_error_handling(fallback_return={
        "status": "unknown",
        "percentage": 0,
        "total": 0,
        "used": 0,
        "free": 0,
        "sync_status": None,
        "errors": None
    })
    async def get_array_usage(self) -> Dict[str, Any]:
        """Fetch Array usage with enhanced error handling and status reporting."""
        _LOGGER.debug("Fetching array usage")
        array_state = await self._get_array_status()

        response = {
            "status": array_state,
            "percentage": 0,
            "total": 0,
            "used": 0,
            "free": 0,
            "sync_status": None,
            "errors": None
        }

        if array_state != "started" and not array_state.startswith("syncing"):
            _LOGGER.debug("Array is %s, skipping usage check", array_state)
            return response

        try:
            result = await self.execute_command(
                "df -k /mnt/user | awk 'NR==2 {print $2,$3,$4}'"
            )

            if result.exit_status != 0:
                response["status"] = "error"
                response["errors"] = ["Failed to get array usage"]
                return response

            output = result.stdout.strip()
            if not output:
                response["status"] = "empty"
                return response

            total, used, free = safe_parse(
                lambda x: list(map(int, x.split())),
                output,
                default=[0, 0, 0],
                error_msg=f"Error parsing array usage output: {output}"
            )
            percentage = (used / total) * 100 if total > 0 else 0

            response.update({
                "percentage": round(percentage, 1),
                "total": total * 1024,
                "used": used * 1024,
                "free": free * 1024,
            })

            if array_state.startswith("syncing"):
                sync_info = await self._get_array_sync_status()
                if sync_info:
                    response["sync_status"] = sync_info

            return response

        except Exception as err:
            _LOGGER.error("Error getting array usage: %s", err)
            response["status"] = "error"
            response["errors"] = [str(err)]
            return response

    async def _get_array_sync_status(self) -> Optional[Dict[str, Any]]:
        """Get detailed array sync status asynchronously."""
        try:
            result = await self.execute_command("mdcmd status")
            if result.exit_status != 0:
                return None

            sync_info = {}
            lines = result.stdout.splitlines()

            # Process lines asynchronously
            tasks = []
            for line in lines:
                if '=' not in line:
                    continue

                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                if key in ["mdResyncPos", "mdResyncSize", "mdResyncSpeed", "mdResyncCorr"]:
                    tasks.append(self._process_sync_value(key, value))
                elif key == "mdResyncAction":
                    sync_info["action"] = value

            # Gather all processed values
            processed_values = await asyncio.gather(*tasks, return_exceptions=True)
            for key, value in processed_values:
                if not isinstance(value, Exception):
                    sync_info[key] = value

            if sync_info and sync_info.get("total_size", 0) > 0:
                progress = (sync_info["position"] / sync_info["total_size"]) * 100
                sync_info["progress"] = round(progress, 2)

            return sync_info

        except (ValueError, TypeError, OSError) as err:
            _LOGGER.debug("Error getting sync status: %s", err)
            return None

    async def _process_sync_value(self, key: str, value: str) -> Tuple[str, Union[int, Exception]]:
        """Process sync values asynchronously."""
        try:
            value_int = int(value)
            key_map = {
                "mdResyncPos": "position",
                "mdResyncSize": "total_size",
                "mdResyncSpeed": "speed",
                "mdResyncCorr": "errors"
            }
            return key_map[key], value_int
        except ValueError as err:
            return key, err

    async def collect_disk_info(self) -> List[Dict[str, Any]]:
        """Collect information about disks using batched commands."""
        _LOGGER.debug("Collecting disk information with batched command")
        disks = []

        try:
            # Get array status for mapping md devices to physical devices
            array_info_result = await self.execute_command("mdcmd status")
            array_info = array_info_result.stdout if array_info_result.exit_status == 0 else ""

            # Get all disk information in a single command
            cmd = (
                # Get disk usage
                "echo '===DISK_USAGE==='; "
                "df -P -B1 /mnt/disk[0-9]* /mnt/cache* /mnt/user* 2>/dev/null | grep -v '^Filesystem' | awk '{print $6,$2,$3,$4}'; "
                # Get mount points and devices
                "echo '===MOUNT_INFO==='; "
                "mount | grep -E '/mnt/' | awk '{print $1,$3,$5}'; "
                # Add ZFS support
                "echo '===ZFS_POOLS==='; "
                "if command -v zpool >/dev/null 2>&1; then zpool list -H -o name,size,alloc,free,capacity,health; else echo 'zfs_not_installed'; fi; "
                # Get SMART data for all disks
                "echo '===SMART_DATA==='; "
                # First get a list of all physical devices
                "for dev in $(ls -1 /dev/sd[a-z] /dev/nvme[0-9]n[0-9] 2>/dev/null); do "
                "  echo \"$dev\"; "
                "  if [[ $dev == *nvme* ]]; then "
                "    nvme smart-log -o json $dev 2>/dev/null || smartctl -d nvme -a -j $dev 2>/dev/null || echo '{}'; "
                "  else "
                "    smartctl -A -j $dev 2>/dev/null || echo '{}'; "
                "  fi; "
                "  echo '---NEXT_DEVICE---'; "
                "done"
            )

            result = await self.execute_command(cmd)

            if result.exit_status == 0:
                # Split the output into sections
                sections = result.stdout.split('===DISK_USAGE===')[1].split('===MOUNT_INFO===')
                disk_usage_output = sections[0].strip()

                sections = sections[1].split('===ZFS_POOLS===')
                mount_info_output = sections[0].strip()

                sections = sections[1].split('===SMART_DATA===')
                zfs_pools_output = sections[0].strip()
                smart_data_output = sections[1].strip()

                # Parse mount info to create a mapping of mount points to devices and filesystem types
                mount_to_device = {}
                mount_to_fs_type = {}
                for line in mount_info_output.splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        device, mount_point, fs_type = parts[0], parts[1], parts[2]
                        mount_to_device[mount_point] = device
                        mount_to_fs_type[mount_point] = fs_type

                # Parse ZFS pool information
                zfs_pools = {}
                if zfs_pools_output != 'zfs_not_installed':
                    for line in zfs_pools_output.splitlines():
                        parts = line.split('\t')
                        if len(parts) >= 6:
                            name, size, alloc, free, capacity, health = parts
                            # Remove '%' from capacity
                            capacity = capacity.rstrip('%')
                            zfs_pools[name] = {
                                'name': name,
                                'size': size,
                                'alloc': alloc,
                                'free': free,
                                'capacity': capacity,
                                'health': health
                            }
                            _LOGGER.debug(f"Found ZFS pool: {name}")

                # Parse array info to map md devices to physical devices
                md_to_physical = {}
                disk_name_to_md = {}

                if array_info:
                    # First find the mapping from disk number to md device
                    for line in array_info.splitlines():
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()

                            if key.startswith("diskName.") and value.startswith("md"):
                                disk_num = key.split(".")[1]
                                md_match = re.search(r'md(\d+)', value)
                                if md_match:
                                    md_num = md_match.group(1)
                                    disk_name_to_md[disk_num] = md_num

                    # Now find the physical device for each disk
                    for line in array_info.splitlines():
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()

                            if key.startswith("rdevName."):
                                disk_num = key.split(".")[1]
                                if disk_num in disk_name_to_md and value.startswith("sd"):
                                    md_num = disk_name_to_md[disk_num]
                                    md_device = f"/dev/md{md_num}p1"
                                    physical_device = f"/dev/{value}"
                                    md_to_physical[md_device] = physical_device

                # Parse SMART data
                device_to_smart_data = {}
                current_device = None
                current_data = ""

                for line in smart_data_output.splitlines():
                    if line.startswith("/dev/"):
                        current_device = line.strip()
                        current_data = ""
                    elif line == "---NEXT_DEVICE---":
                        if current_device and current_data:
                            try:
                                device_to_smart_data[current_device] = json.loads(current_data)
                            except json.JSONDecodeError:
                                # Suppress warnings for boot devices (typically /dev/sda)
                                if current_device == "/dev/sda":
                                    _LOGGER.debug("No SMART data available for boot device %s", current_device)
                                else:
                                    _LOGGER.warning("Failed to parse SMART data for %s", current_device)
                        current_device = None
                        current_data = ""
                    elif current_device:
                        current_data += line + "\n"

                # Parse disk usage and create disk entries
                for line in disk_usage_output.splitlines():
                    try:
                        parts = line.split()
                        if len(parts) != 4:
                            continue

                        mount_point, total, used, free = parts
                        disk_name = mount_point.replace('/mnt/', '')

                        # Skip invalid or system disks while allowing custom pools
                        if not is_valid_disk_name(disk_name):
                            _LOGGER.debug("Skipping invalid disk name: %s", disk_name)
                            continue

                        # Check if this is a ZFS pool
                        is_zfs_pool = False
                        for pool_name, pool_info in zfs_pools.items():
                            if pool_name == disk_name:
                                is_zfs_pool = True
                                _LOGGER.debug(f"Detected {disk_name} as ZFS pool")

                        # Get current disk state
                        state = await self._state_manager.get_disk_state(disk_name)

                        disk_info = {
                            "name": disk_name,
                            "mount_point": mount_point,
                            "total": int(total),
                            "used": int(used),
                            "free": int(free),
                            "percentage": round((int(used) / int(total) * 100), 1) if int(total) > 0 else 0,
                            "state": state.value,
                            "smart_data": {},  # Will be populated with SMART data
                            "smart_status": "Unknown",
                            "temperature": None,
                            "device": None,
                        }

                        # Add filesystem type if available
                        if is_zfs_pool:
                            disk_info["filesystem"] = "zfs"
                        elif mount_point in mount_to_fs_type:
                            disk_info["filesystem"] = mount_to_fs_type[mount_point]

                        # Get device path
                        device_path = None
                        if mount_point in mount_to_device:
                            device_path = mount_to_device[mount_point]
                            # Map md device to physical device if needed
                            if device_path in md_to_physical:
                                device_path = md_to_physical[device_path]
                            disk_info["device"] = device_path

                        # Add SMART data if available and disk is active
                        if state == DiskState.ACTIVE and device_path and device_path in device_to_smart_data:
                            smart_data = device_to_smart_data[device_path]

                            # Extract SMART status
                            if "smart_status" in smart_data:
                                # Check if smart_status is already a string (from our updated SMART processing)
                                if isinstance(smart_data["smart_status"], str):
                                    # Convert to title case for consistency
                                    disk_info["smart_status"] = smart_data["smart_status"].title()
                                else:
                                    # Legacy format: smart_status is an object with a passed property
                                    disk_info["smart_status"] = "Passed" if smart_data["smart_status"].get("passed", True) else "Failed"

                            # Extract temperature
                            temperature = None
                            is_nvme = "nvme" in device_path.lower()

                            if is_nvme:
                                # Try different temperature field locations for NVMe
                                nvme_data = smart_data.get("nvme_smart_health_information_log", {})
                                if isinstance(nvme_data, dict) and "temperature" in nvme_data:
                                    temperature = nvme_data["temperature"]
                                elif "temperature" in smart_data:
                                    temp_data = smart_data["temperature"]
                                    if isinstance(temp_data, dict) and "current" in temp_data:
                                        temperature = temp_data["current"]
                                    elif isinstance(temp_data, (int, float)):
                                        temperature = temp_data

                                # Fix for NVMe temperature values reported in tenths of a degree
                                if temperature is not None and temperature > 100 and temperature < 1000:
                                    temperature = temperature / 10
                            else:
                                # For SATA drives
                                if "temperature" in smart_data and "current" in smart_data["temperature"]:
                                    temperature = smart_data["temperature"]["current"]
                                else:
                                    # Try to find temperature in attributes
                                    for attr in smart_data.get("ata_smart_attributes", {}).get("table", []):
                                        if attr.get("name") == "Temperature_Celsius" and "raw" in attr:
                                            temperature = attr["raw"].get("value")
                                            break

                            if temperature is not None:
                                disk_info["temperature"] = int(temperature)

                            # Store the full SMART data
                            disk_info["smart_data"] = smart_data

                        disks.append(disk_info)
                    except (ValueError, IndexError) as err:
                        _LOGGER.debug("Error parsing disk line '%s': %s", line, err)

                # Add ZFS pools information to the result
                if zfs_pools and zfs_pools != 'zfs_not_installed':
                    _LOGGER.debug(f"Adding ZFS pools information: {list(zfs_pools.keys())}")

                    # Add ZFS pools to individual_disks list if they're not already there
                    existing_disk_names = {disk.get('name') for disk in disks}
                    for pool_name, pool_info in zfs_pools.items():
                        if pool_name not in existing_disk_names:
                            # Check if the pool is mounted
                            mount_point = f"/mnt/{pool_name}"

                            # Convert size strings to bytes
                            try:
                                # Parse size (e.g., 222G)
                                size_str = pool_info.get('size', '0')
                                size_value = float(size_str[:-1])
                                size_unit = size_str[-1].upper()
                                total_bytes = 0

                                if size_unit == 'T':
                                    total_bytes = int(size_value * 1024 * 1024 * 1024 * 1024)
                                elif size_unit == 'G':
                                    total_bytes = int(size_value * 1024 * 1024 * 1024)
                                elif size_unit == 'M':
                                    total_bytes = int(size_value * 1024 * 1024)
                                elif size_unit == 'K':
                                    total_bytes = int(size_value * 1024)
                                else:
                                    total_bytes = int(size_value)

                                # Parse allocated space (e.g., 5.00G)
                                alloc_str = pool_info.get('alloc', '0')
                                alloc_value = float(alloc_str[:-1])
                                alloc_unit = alloc_str[-1].upper()
                                used_bytes = 0

                                if alloc_unit == 'T':
                                    used_bytes = int(alloc_value * 1024 * 1024 * 1024 * 1024)
                                elif alloc_unit == 'G':
                                    used_bytes = int(alloc_value * 1024 * 1024 * 1024)
                                elif alloc_unit == 'M':
                                    used_bytes = int(alloc_value * 1024 * 1024)
                                elif alloc_unit == 'K':
                                    used_bytes = int(alloc_value * 1024)
                                else:
                                    used_bytes = int(alloc_value)

                                # Calculate free space
                                free_bytes = total_bytes - used_bytes

                                # Get current disk state
                                state = await self._state_manager.get_disk_state(pool_name)

                                # Create disk info for the ZFS pool
                                disk_info = {
                                    "name": pool_name,
                                    "mount_point": mount_point,
                                    "total": total_bytes,
                                    "used": used_bytes,
                                    "free": free_bytes,
                                    "percentage": int(pool_info.get('capacity', '0').rstrip('%')),
                                    "state": state.value,
                                    "smart_data": {},
                                    "smart_status": "Unknown",
                                    "temperature": None,
                                    "device": None,
                                    "filesystem": "zfs",
                                    "health": pool_info.get('health', 'UNKNOWN')
                                }

                                disks.append(disk_info)
                                _LOGGER.info(f"Added ZFS pool {pool_name} to individual_disks")
                            except (ValueError, TypeError, IndexError) as err:
                                _LOGGER.warning(f"Error adding ZFS pool {pool_name} to individual_disks: {err}")

                    # Add ZFS pools to system stats
                    system_stats = {"zfs_pools": zfs_pools}
                    return disks, system_stats

                return disks, {}
            else:
                _LOGGER.warning("Batched disk info command failed with exit status %d", result.exit_status)
                return [], {}

        except Exception as err:
            _LOGGER.error("Error collecting disk information with batched command: %s", err)
            return [], {}

    async def get_individual_disk_usage(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Get usage information for individual disks."""
        try:
            # Try the optimized batched command approach first
            _LOGGER.debug("Fetching individual disk usage with optimized approach")
            disks, extra_stats = await self.collect_disk_info()
            # Return the disks or an empty list if none were found
            return disks if disks else [], extra_stats

        except Exception as err:
            _LOGGER.error("Error getting disk usage: %s", err)
            return [], {}

    async def get_cache_usage(self) -> Dict[str, Any]:
        """Get cache pool usage with enhanced error handling."""
        try:
            _LOGGER.debug("Fetching cache usage")

            mount_check = await self.execute_command("mountpoint -q /mnt/cache")
            if mount_check.exit_status != 0:
                return {
                    "status": "not_mounted",
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0
                }

            result = await self.execute_command(
                "df -k /mnt/cache | awk 'NR==2 {print $2,$3,$4}'"
            )

            if result.exit_status != 0:
                return {
                    "status": "error",
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0,
                    "error": "Failed to get cache usage"
                }

            try:
                total, used, free = map(int, result.stdout.strip().split())
                pool_info = await self._get_cache_pool_info()

                return {
                    "status": "active",
                    "percentage": round((used / total) * 100, 1) if total > 0 else 0,
                    "total": total * 1024,
                    "used": used * 1024,
                    "free": free * 1024,
                    "pool_status": pool_info
                }

            except (ValueError, TypeError) as err:
                _LOGGER.error("Error parsing cache usage: %s", err)
                return {
                    "status": "error",
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0,
                    "error": str(err)
                }

        except OSError as err:
            _LOGGER.error("Error getting cache usage: %s", err)
            return {
                "status": "error",
                "percentage": 0,
                "total": 0,
                "used": 0,
                "free": 0,
                "error": str(err)
            }

    async def _get_pool_info(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed pool information for any ZFS pool."""
        try:
            # Check if this is a ZFS pool
            zfs_result = await self.execute_command(f"zpool list -H -o name,size,alloc,free,capacity,health {pool_name} 2>/dev/null")
            if zfs_result.exit_status == 0 and zfs_result.stdout.strip():
                # This is a ZFS pool
                parts = zfs_result.stdout.strip().split('\t')
                if len(parts) >= 6:
                    name, size, alloc, free, capacity, health = parts
                    # Remove '%' from capacity
                    capacity = capacity.rstrip('%')

                    # Get ZFS pool devices
                    devices_result = await self.execute_command(f"zpool list -v {pool_name} | grep -E '^\\s+\\w+' | awk '{{print $1}}'")
                    devices = []
                    if devices_result.exit_status == 0:
                        devices = [f"/dev/{dev}" for dev in devices_result.stdout.strip().splitlines()]

                    return {
                        "filesystem": "zfs",
                        "devices": devices,
                        "total_devices": len(devices),
                        "raid_type": "zfs",
                        "health": health
                    }
            return None
        except (OSError, ValueError) as err:
            _LOGGER.debug(f"Error getting ZFS pool info for {pool_name}: {err}")
            return None

    async def _get_cache_pool_info(self) -> Optional[Dict[str, Any]]:
        """Get detailed cache pool information."""
        try:
            # First check if cache is a ZFS pool
            zfs_info = await self._get_pool_info("cache")
            if zfs_info:
                return zfs_info

            # For testing, also check if garbage is available as a ZFS pool
            garbage_info = await self._get_pool_info("garbage")
            if garbage_info:
                _LOGGER.info("Using 'garbage' ZFS pool for testing")
                return garbage_info

            # If not ZFS, try btrfs
            result = await self.execute_command("btrfs filesystem show /mnt/cache")
            if result.exit_status != 0:
                # Try XFS as a fallback
                xfs_result = await self.execute_command("mount | grep '/mnt/cache' | grep 'xfs'")
                if xfs_result.exit_status == 0:
                    # It's an XFS filesystem
                    device = xfs_result.stdout.strip().split()[0]
                    return {
                        "filesystem": "xfs",
                        "devices": [device] if device.startswith("/dev/") else [],
                        "total_devices": 1,
                        "raid_type": "single"
                    }

                # If we get here, also try checking if /mnt/garbage exists and is mounted
                garbage_mount = await self.execute_command("mountpoint -q /mnt/garbage && echo 'mounted'")
                if garbage_mount.exit_status == 0 and garbage_mount.stdout.strip() == 'mounted':
                    _LOGGER.info("Found mounted /mnt/garbage, checking filesystem type")
                    garbage_fs = await self.execute_command("mount | grep '/mnt/garbage' | awk '{print $5}'")
                    if garbage_fs.exit_status == 0 and garbage_fs.stdout.strip() == 'zfs':
                        _LOGGER.info("Using mounted ZFS filesystem at /mnt/garbage for testing")
                        return {
                            "filesystem": "zfs",
                            "devices": [],
                            "total_devices": 1,
                            "raid_type": "zfs",
                            "health": "ONLINE"
                        }
                return None

            pool_info = {
                "filesystem": "btrfs",
                "devices": [],
                "total_devices": 0,
                "raid_type": "single"
            }

            for line in result.stdout.splitlines():
                if "devices:" in line.lower():
                    pool_info["total_devices"] = int(line.split()[0])
                elif "raid" in line.lower():
                    pool_info["raid_type"] = line.split()[0].lower()
                elif "/dev/" in line:
                    device = line.split()[-1]
                    if device.startswith("/dev/"):
                        pool_info["devices"].append(device)

            return pool_info

        except (OSError, ValueError) as err:
            _LOGGER.debug("Error getting cache pool info: %s", err)
            return None

    async def get_disk_temperature_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get temperature statistics for all disks."""
        stats = {}
        try:
            for device, cache_data in self._disk_cache.items():
                smart_data = cache_data.get("smart_data", {})
                if temp := smart_data.get("temperature"):
                    stats[device] = {
                        "current": temp,
                        "max": smart_data.get("max_temperature"),
                        "min": smart_data.get("min_temperature"),
                        "last_update": datetime.now().isoformat(),
                        "status": "active"
                    }
                else:
                    stats[device] = {
                        "status": smart_data.get("status", "unknown"),
                        "last_update": datetime.now().isoformat()
                    }

        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error getting temperature stats: %s", err)
        return stats
