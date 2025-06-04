"""Disk operations for Unraid."""
from __future__ import annotations

import asyncio
import logging
import aiofiles # type: ignore
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
import re
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
        # Clear any cached MD device paths to force re-resolution
        self._state_manager.clear_md_cache()
        _LOGGER.debug("Created SmartDataManager and DiskStateManager, cleared MD cache")

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

    async def collect_disk_info(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Collect information about disks using batched commands.

        This method is designed to respect disk standby states by:
        1. First collecting basic disk information without SMART data
        2. Only collecting SMART data for disks that are already in ACTIVE state
        3. Never waking up disks that are in STANDBY mode
        """
        _LOGGER.debug("Collecting disk information with standby-aware batched command")
        disks = []

        try:
            # Get array status for mapping md devices to physical devices
            array_info_result = await self.execute_command("mdcmd status")
            array_info = array_info_result.stdout if array_info_result.exit_status == 0 else ""

            # Get all disk information in a single command, but without SMART data first
            # This prevents waking up disks in standby mode
            cmd = (
                # Get disk usage for standard Unraid mounts
                "echo '===DISK_USAGE==='; "
                "df -P -B1 /mnt/disk[0-9]* /mnt/cache* /mnt/user* 2>/dev/null | grep -v '^Filesystem' | awk '{print $6,$2,$3,$4}'; "
                # Get mount points and devices (including ZFS and other custom mounts)
                "echo '===MOUNT_INFO==='; "
                "mount | grep -E '/mnt/' | awk '{print $1,$3,$5}'; "
                # Get disk serial numbers
                "echo '===DISK_SERIALS==='; "
                "lsblk -o NAME,SERIAL | grep -v '^NAME'; "
                # Get all block devices with transport info for USB detection
                "echo '===BLOCK_DEVICES==='; "
                "lsblk -o NAME,TRAN,TYPE,SIZE,MODEL,VENDOR | grep -v '^NAME'; "
                # Add ZFS support
                "echo '===ZFS_POOLS==='; "
                "if command -v zpool >/dev/null 2>&1; then zpool list -H -o name,size,alloc,free,capacity,health; else echo 'zfs_not_installed'; fi; "
                # Get ZFS pool device mappings
                "echo '===ZFS_DEVICES==='; "
                "if command -v zpool >/dev/null 2>&1; then zpool status -P | grep -E '^[[:space:]]+/dev/' | awk '{print $1}'; else echo 'zfs_not_installed'; fi"
            )

            result = await self.execute_command(cmd)

            if result.exit_status == 0:
                # Split the output into sections
                sections = result.stdout.split('===DISK_USAGE===')[1].split('===MOUNT_INFO===')
                disk_usage_output = sections[0].strip()

                sections = sections[1].split('===DISK_SERIALS===')
                mount_info_output = sections[0].strip()

                sections = sections[1].split('===BLOCK_DEVICES===')
                disk_serials_output = sections[0].strip()

                sections = sections[1].split('===ZFS_POOLS===')
                block_devices_output = sections[0].strip()

                sections = sections[1].split('===ZFS_DEVICES===')
                zfs_pools_output = sections[0].strip()
                zfs_devices_output = sections[1].strip()

                # Parse disk serial numbers
                device_to_serial = {}
                for line in disk_serials_output.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        device_name = parts[0].strip()
                        serial = parts[1].strip()
                        if serial and serial != "":
                            device_to_serial[device_name] = serial
                            _LOGGER.debug(f"Found serial for {device_name}: {serial}")

                # Parse block devices information for USB detection
                block_devices = {}
                for line in block_devices_output.splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        device_name = parts[0].strip()
                        transport = parts[1].strip() if parts[1] != '-' else 'unknown'
                        device_type = parts[2].strip()
                        size = parts[3].strip() if len(parts) > 3 else 'unknown'
                        model = parts[4].strip() if len(parts) > 4 else 'unknown'
                        vendor = parts[5].strip() if len(parts) > 5 else 'unknown'

                        block_devices[device_name] = {
                            'transport': transport,
                            'type': device_type,
                            'size': size,
                            'model': model,
                            'vendor': vendor
                        }
                        _LOGGER.debug(f"Found block device {device_name}: transport={transport}, type={device_type}")

                # Parse ZFS device mappings
                zfs_devices = set()
                if zfs_devices_output != 'zfs_not_installed':
                    for line in zfs_devices_output.splitlines():
                        device_path = line.strip()
                        if device_path.startswith('/dev/'):
                            zfs_devices.add(device_path)
                            _LOGGER.debug(f"Found ZFS device: {device_path}")

                # We don't collect SMART data in the initial batch to avoid waking up disks

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

                # No need to initialize SMART data dictionary as we'll collect it per active disk

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
                        for zfs_pool_name in zfs_pools.keys():
                            if zfs_pool_name == disk_name:
                                is_zfs_pool = True
                                _LOGGER.debug(f"Detected {disk_name} as ZFS pool")

                        # Get current disk state
                        state = await self._state_manager.get_disk_state(disk_name)
                        _LOGGER.debug("Disk %s state from DiskStateManager: %s", disk_name, state.value)

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

                            # Get disk serial number if available
                            if device_path and device_path.startswith("/dev/"):
                                # Extract the device name without /dev/ prefix
                                device_name = device_path.replace("/dev/", "")
                                # Check if we have serial number in the device_to_serial mapping
                                if device_name in device_to_serial:
                                    disk_info["serial"] = device_to_serial[device_name]

                        # Only collect SMART data if disk is active to avoid waking up standby disks
                        if state == DiskState.ACTIVE and device_path:
                            # Get SMART data for this specific active disk
                            smart_data = await self._smart_manager.get_smart_data(device_path)
                            if smart_data:
                                disk_info.update({
                                    "smart_status": "Passed" if smart_data.get("smart_status") else "Failed",
                                    "temperature": smart_data.get("temperature"),
                                    "power_on_hours": smart_data.get("power_on_hours"),
                                    "smart_data": smart_data
                                })

                        disks.append(disk_info)
                    except (ValueError, IndexError) as err:
                        _LOGGER.debug("Error parsing disk line '%s': %s", line, err)

                # Add individual ZFS devices to monitoring (for USB storage drives in ZFS pools)
                for zfs_device_path in zfs_devices:
                    # Check if this device is already being monitored
                    device_already_monitored = any(
                        disk.get("device") == zfs_device_path for disk in disks
                    )

                    if not device_already_monitored:
                        # Extract device name for block device lookup
                        device_name = zfs_device_path.replace("/dev/", "")

                        # For partitions (e.g., sda1), also check the parent device (sda)
                        parent_device_name = device_name
                        if device_name[-1].isdigit():
                            # Remove partition number to get parent device
                            parent_device_name = re.sub(r'\d+$', '', device_name)

                        # Check if this is a USB device (check both partition and parent device)
                        device_info = None
                        if device_name in block_devices:
                            device_info = block_devices[device_name]
                        elif parent_device_name in block_devices:
                            device_info = block_devices[parent_device_name]
                            device_name = parent_device_name  # Use parent device for monitoring

                        if device_info:
                            transport = device_info.get('transport', 'unknown')

                            if transport == 'usb':
                                _LOGGER.info(f"Found USB storage device in ZFS pool: {zfs_device_path}")

                                # Get current disk state - assume active for ZFS devices
                                state = DiskState.ACTIVE

                                # Create a disk entry for this USB storage device
                                # Use the parent device path for SMART monitoring
                                monitoring_device_path = f"/dev/{device_name}"

                                # Parse the device size from block device info
                                device_size_str = device_info.get('size', '0')
                                device_total_bytes = self._parse_size_string(device_size_str)

                                # Try to get ZFS pool usage information for this device
                                pool_used_bytes = 0
                                pool_free_bytes = device_total_bytes
                                pool_percentage = 0

                                # Find which ZFS pool this device belongs to
                                device_pool_name = None
                                for pool_name, pool_data in zfs_pools.items():
                                    # Check if this device is part of this pool by checking ZFS device list
                                    if zfs_device_path in zfs_devices:
                                        # Get pool usage data
                                        pool_total_bytes = self._parse_size_string(pool_data.get('size', '0'))
                                        pool_used_bytes = self._parse_size_string(pool_data.get('alloc', '0'))
                                        pool_free_bytes = self._parse_size_string(pool_data.get('free', '0'))
                                        pool_percentage = int(pool_data.get('capacity', '0'))
                                        device_pool_name = pool_name
                                        _LOGGER.debug(f"USB device {device_name} is part of ZFS pool {pool_name}: {device_size_str} total, pool usage {pool_percentage}%")
                                        break

                                # Use pool name for entity naming instead of device name for better UX
                                entity_name = device_pool_name if device_pool_name else f"zfs_{device_name}"

                                disk_info = {
                                    "name": entity_name,  # Use pool name for cleaner entity naming
                                    "mount_point": f"ZFS device ({zfs_device_path})" + (f" in pool '{device_pool_name}'" if device_pool_name else ""),
                                    "total": device_total_bytes,  # Individual device capacity
                                    "used": pool_used_bytes,      # Pool usage (shared across pool devices)
                                    "free": pool_free_bytes,      # Pool free space (shared across pool devices)
                                    "percentage": pool_percentage, # Pool usage percentage
                                    "state": state.value,
                                    "smart_data": {},
                                    "smart_status": "Unknown",
                                    "temperature": None,
                                    "device": monitoring_device_path,
                                    "filesystem": "zfs",
                                    "transport": transport,
                                    "device_type": device_info.get('type', 'disk'),
                                    "model": device_info.get('model', 'Unknown'),
                                    "vendor": device_info.get('vendor', 'Unknown'),
                                    "size": device_size_str,
                                    "pool_name": device_pool_name,  # Track which pool this device belongs to
                                    "physical_device": device_name,  # Track the actual physical device for SMART monitoring
                                    "zfs_device_path": zfs_device_path  # Track the ZFS device path
                                }

                                # Get disk serial number if available
                                if device_name in device_to_serial:
                                    disk_info["serial"] = device_to_serial[device_name]

                                # Collect SMART data for USB storage devices
                                smart_data = await self._smart_manager.get_smart_data(monitoring_device_path)
                                if smart_data:
                                    disk_info.update({
                                        "smart_status": "Passed" if smart_data.get("smart_status") else "Failed",
                                        "temperature": smart_data.get("temperature"),
                                        "power_on_hours": smart_data.get("power_on_hours"),
                                        "smart_data": smart_data
                                    })

                                disks.append(disk_info)
                                _LOGGER.info(f"Added USB storage device {zfs_device_path} to monitoring as '{entity_name}' (pool: {device_pool_name})")

                # Add ZFS pools information to the result
                if zfs_pools and zfs_pools != 'zfs_not_installed':
                    _LOGGER.debug(f"Adding ZFS pools information: {list(zfs_pools.keys())}")

                    # Check which ZFS pools already have device-level entities
                    existing_disk_names = {disk.get('name') for disk in disks}
                    zfs_device_pools = set()

                    # Track which pools have individual device entities
                    for disk in disks:
                        pool_name = disk.get('pool_name')
                        if pool_name:
                            zfs_device_pools.add(pool_name)
                            _LOGGER.debug(f"Found device-level entity for ZFS pool: {pool_name}")

                    # Add pool-level entities for all ZFS pools to provide pool usage sensors
                    # Note: Binary sensor entities are consolidated, but usage sensors are valuable
                    for pool_name in zfs_pools.keys():
                        # Always create pool entities for usage sensors, even if device-level entities exist
                        # The binary sensor consolidation happens at the entity level, not here
                            # Get pool device information to determine if it's single or multi-device
                            try:
                                devices_result = await self.execute_command(f"zpool list -v {pool_name} | grep -E '^\\s+\\w+' | awk '{{print $1}}'")
                                pool_devices = []
                                if devices_result.exit_status == 0:
                                    pool_devices = [dev.strip() for dev in devices_result.stdout.strip().splitlines() if dev.strip()]

                                # Always create pool entities for usage sensors, but mark single-device pools
                                # The binary sensor consolidation happens at the entity level, not here
                                pool_type = "single-device" if len(pool_devices) <= 1 else "multi-device"
                                _LOGGER.debug(f"Creating pool entity for {pool_type} ZFS pool '{pool_name}' ({len(pool_devices)} devices)")

                                # Create pool entity for multi-device pools or pools without device entities
                                mount_point = f"/mnt/{pool_name}"

                                # Parse ZFS pool data from command output
                                zpool_cmd = f"zpool list -H -o name,size,alloc,free,capacity,health {pool_name}"
                                zpool_result = await self.execute_command(zpool_cmd)

                                if zpool_result.exit_status == 0 and zpool_result.stdout.strip():
                                    parts = zpool_result.stdout.strip().split('\t')
                                    if len(parts) >= 6:
                                        # Extract values
                                        size_str = parts[1]
                                        alloc_str = parts[2]
                                        free_str = parts[3]
                                        capacity_str = parts[4].rstrip('%')
                                        health_str = parts[5]

                                        # Parse size values
                                        total_bytes = self._parse_size_string(size_str)
                                        used_bytes = self._parse_size_string(alloc_str)
                                        free_bytes = self._parse_size_string(free_str)

                                        # Get current disk state - ZFS pools are always active
                                        state = DiskState.ACTIVE

                                        # Create disk info for the ZFS pool
                                        disk_info = {
                                            "name": pool_name,
                                            "mount_point": mount_point,
                                            "total": total_bytes,
                                            "used": used_bytes,
                                            "free": free_bytes,
                                            "percentage": int(capacity_str),
                                            "state": state.value,
                                            "smart_data": {},
                                            "smart_status": "Unknown",
                                            "temperature": None,
                                            "device": None,
                                            "filesystem": "zfs",
                                            "health": health_str,
                                            "pool_devices": pool_devices,
                                            "device_count": len(pool_devices)
                                        }

                                        disks.append(disk_info)
                                        _LOGGER.info(f"Added multi-device ZFS pool {pool_name} to individual_disks ({len(pool_devices)} devices)")
                            except (ValueError, TypeError, IndexError) as err:
                                _LOGGER.warning(f"Error adding ZFS pool {pool_name} to individual_disks: {err}")

                    # Add ZFS pools to system stats
                    system_stats = {"zfs_pools": zfs_pools}
                    return disks, system_stats

                return disks, {}
            else:
                # Handle cases where exit_status might be None
                exit_status = getattr(result, 'exit_status', None)
                if exit_status is not None:
                    _LOGGER.warning("Batched disk info command failed with exit status %d", exit_status)
                else:
                    _LOGGER.warning("Batched disk info command failed with unknown exit status (result: %s)", result)
                return [], {}

        except Exception as err:
            _LOGGER.error("Error collecting disk information with batched command: %s", err)
            return [], {}

    def _parse_size_string(self, size_str: str) -> int:
        """Parse size strings like 1.5T, 500G, etc. to bytes."""
        try:
            if not size_str or size_str == '-':
                return 0

            # Handle decimal points in the value
            if size_str[-1].isalpha():
                size_value = float(size_str[:-1])
                size_unit = size_str[-1].upper()
            else:
                size_value = float(size_str)
                size_unit = 'B'

            # Convert to bytes based on unit
            if size_unit == 'T':
                return int(size_value * 1024 * 1024 * 1024 * 1024)
            elif size_unit == 'G':
                return int(size_value * 1024 * 1024 * 1024)
            elif size_unit == 'M':
                return int(size_value * 1024 * 1024)
            elif size_unit == 'K':
                return int(size_value * 1024)
            else:
                return int(size_value)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(f"Error parsing size string '{size_str}': {err}")
            return 0

    async def get_individual_disk_usage(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Get usage information for individual disks."""
        try:
            # Use the optimized batched command approach that respects disk standby state
            _LOGGER.debug("Fetching individual disk usage with standby-aware approach")
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
                    # Extract only the values we need
                    pool_name = parts[0]
                    capacity = parts[4]
                    health = parts[5]
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
