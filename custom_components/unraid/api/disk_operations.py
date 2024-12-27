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
from .disk_mapping import parse_disk_config, parse_disks_ini
from .smart_operations import SmartDataManager
from .disk_state import DiskState, DiskStateManager

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

    async def get_disk_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive disk mappings including serials."""
        try:
            async with self._disk_lock:
                # Get all data sources in parallel
                command_results = await asyncio.gather(
                    self.execute_command("cat /var/local/emhttp/disks.ini"),
                    self.execute_command("cat /boot/config/disk.cfg"),
                    return_exceptions=True
                )

                mappings = {}
                
                # Parse disks.ini first (primary source)
                if not isinstance(command_results[0], Exception) and command_results[0].exit_status == 0:
                    disks_ini_mappings = await parse_disks_ini(self.execute_command)
                    for disk_name, disk_info in disks_ini_mappings.items():
                        mappings[disk_name] = {
                            "name": disk_name,
                            "device": disk_info.get("device", ""),
                            "serial": disk_info.get("id", ""),  # Serial is in the 'id' field
                            "status": disk_info.get("status", "unknown"),
                            "filesystem": disk_info.get("fsType", ""),
                            "spindown_delay": "-1"  # Default, will be updated from disk.cfg
                        }

                # Add spindown delays from disk.cfg if needed
                if not isinstance(command_results[1], Exception) and command_results[1].exit_status == 0:
                    disk_cfg = parse_disk_config(command_results[1].stdout)
                    # Update spindown delays in mappings
                    for disk_name, config in disk_cfg.items():
                        if disk_name in mappings:
                            mappings[disk_name].update({
                                "spindown_delay": config.get("spindown_delay", "-1")
                            })

                if not mappings:
                    _LOGGER.warning("No disk mappings found from any source")
                else:
                    _LOGGER.debug("Found disk mappings: %s", mappings)

                return mappings

        except Exception as err:
            _LOGGER.error("Error getting disk mappings: %s", err)
            return {}

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

    async def get_disk_model(self, device: str) -> str:
        """Get disk model with enhanced error handling."""
        try:
            smart_data = await self._smart_manager.get_smart_data(device)
            if smart_data:
                return smart_data.get("model_name", "Unknown")
            return "Unknown"
        except Exception as err:
            _LOGGER.debug("Error getting model for %s: %s", device, err)
            return "Unknown"

    async def get_disk_spin_down_settings(self) -> dict[str, int]:
        """Fetch disk spin down delay settings with validation."""
        try:
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
                        default_delay = int(value)
                    elif line.startswith("diskSpindownDelay."):
                        disk_num = line.split(".")[1].split("=")[0]
                        value = line.split("=")[1].strip().strip('"')
                        delay = int(value)

                        if not disk_num.isdigit():
                            continue

                        disk_name = f"disk{disk_num}"
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

        except (OSError, ValueError) as err:
            _LOGGER.error("Error getting spin down settings: %s", err)
            return {"default": 0}

    async def get_array_usage(self) -> Dict[str, Any]:
        """Fetch Array usage with enhanced error handling and status reporting."""
        try:
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

                total, used, free = map(int, output.split())
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

            except (ValueError, TypeError) as err:
                _LOGGER.error("Error parsing array usage: %s", err)
                response["status"] = "error"
                response["errors"] = [str(err)]
                return response

        except (OSError, ValueError) as err:
            _LOGGER.error("Error getting array usage: %s", err)
            return {
                "status": "error",
                "percentage": 0,
                "total": 0,
                "used": 0,
                "free": 0,
                "errors": [str(err)]
            }

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

    async def get_individual_disk_usage(self) -> List[Dict[str, Any]]:
        """Get usage information for individual disks."""
        try:
            disks = []
            # Get usage for mounted disks with improved filtering
            # Note: Removed grep since we'll filter in code
            usage_result = await self.execute_command(
                "df -B1 /mnt/disk* /mnt/cache /mnt/* 2>/dev/null | "
                "awk 'NR>1 {print $6,$2,$3,$4}'"
            )

            if usage_result.exit_status == 0:
                for line in usage_result.stdout.splitlines():
                    try:
                        mount_point, total, used, free = line.split()
                        disk_name = mount_point.replace('/mnt/', '')
                        
                        # Skip invalid or system disks while allowing custom pools
                        if not is_valid_disk_name(disk_name):
                            _LOGGER.debug("Skipping invalid disk name: %s", disk_name)
                            continue
                        
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
                            "smart_data": {},  # Will be populated by update_disk_status
                            "smart_status": "Unknown",
                            "temperature": None,
                            "device": None,
                        }
                        
                        # Update disk status with SMART data if disk is active
                        if state == DiskState.ACTIVE:
                            disk_info = await self.update_disk_status(disk_info)
                        
                        disks.append(disk_info)

                    except (ValueError, IndexError) as err:
                        _LOGGER.debug("Error parsing disk usage line '%s': %s", line, err)
                        continue

                return disks

            return []

        except Exception as err:
            _LOGGER.error("Error getting disk usage: %s", err)
            return []

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

    async def _get_cache_pool_info(self) -> Optional[Dict[str, Any]]:
        """Get detailed cache pool information."""
        try:
            result = await self.execute_command("btrfs filesystem show /mnt/cache")
            if result.exit_status != 0:
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
