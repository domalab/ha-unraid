"""Disk operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import re
from datetime import datetime

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

class DiskState(Enum):
    """Disk power state."""
    ACTIVE = "active"
    STANDBY = "standby"
    UNKNOWN = "unknown"

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
        self._disk_cache: Dict[str, Dict[str, Any]] = {}
        self._smart_thresholds = {
            "Raw_Read_Error_Rate": {"warn": 50, "crit": 30},
            "Reallocated_Sector_Ct": {"warn": 10, "crit": 20},
            "Current_Pending_Sector": {"warn": 1, "crit": 5},
            "Offline_Uncorrectable": {"warn": 1, "crit": 5},
            "Temperature_Celsius": {"warn": 50, "crit": 60},
            "UDMA_CRC_Error_Count": {"warn": 100, "crit": 200},
        }

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

    async def get_disk_model(self, device: str) -> str:
        """Get disk model with enhanced error handling."""
        try:
            if device in self._disk_cache:
                smart_data = self._disk_cache[device].get("smart_data", {})
                if model := smart_data.get("model"):
                    return model

            result = await self.execute_command(f"smartctl -i /dev/{device}")
            if result.exit_status != 0:
                raise OSError(f"smartctl failed with exit code {result.exit_status}")

            for line in result.stdout.splitlines():
                if "Device Model:" in line:
                    return line.split("Device Model:", 1)[1].strip()
                elif "Product:" in line:
                    return line.split("Product:", 1)[1].strip()
                elif "Model Number:" in line:
                    return line.split("Model Number:", 1)[1].strip()

            return "Unknown"

        except (OSError, ValueError) as err:
            _LOGGER.debug("Error getting model for %s: %s", device, err)
            return "Unknown"

    async def get_disk_spin_down_settings(self) -> dict[str, int]:
        """Fetch disk spin down delay settings with validation."""
        try:
            settings = await self.execute_command("cat /boot/config/disk.cfg")
            if settings.exit_status != 0:
                raise OSError("Failed to read disk config")

            default_delay = 0
            disk_delays = {}

            for line in settings.stdout.splitlines():
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
        """Get detailed array sync status."""
        try:
            result = await self.execute_command("mdcmd status")
            if result.exit_status != 0:
                return None

            sync_info = {}
            for line in result.stdout.splitlines():
                if '=' not in line:
                    continue

                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                if key == "mdResyncPos":
                    sync_info["position"] = int(value)
                elif key == "mdResyncSize":
                    sync_info["total_size"] = int(value)
                elif key == "mdResyncAction":
                    sync_info["action"] = value
                elif key == "mdResyncSpeed":
                    sync_info["speed"] = int(value)
                elif key == "mdResyncCorr":
                    sync_info["errors"] = int(value)

            if sync_info:
                if sync_info.get("total_size", 0) > 0:
                    progress = (sync_info["position"] / sync_info["total_size"]) * 100
                    sync_info["progress"] = round(progress, 2)

                if sync_info.get("speed", 0) > 0:
                    remaining_bytes = sync_info["total_size"] - sync_info["position"]
                    remaining_seconds = remaining_bytes / (sync_info["speed"] * 1024)
                    sync_info["estimated_time"] = round(remaining_seconds)

                return sync_info

            return None

        except (ValueError, TypeError, OSError) as err:
            _LOGGER.debug("Error getting sync status: %s", err)
            return None

    async def get_individual_disk_usage(self) -> List[Dict[str, Any]]:
        """Get usage information for individual disks."""
        try:
            result = await self.execute_command(
                "df -B1 /mnt/disk* /mnt/cache 2>/dev/null | "
                "awk 'NR>1 {print $6,$2,$3,$4}'"
            )

            if result.exit_status != 0:
                _LOGGER.error("Failed to get disk usage: %s", result.stderr)
                return []

            disks = []
            for line in result.stdout.splitlines():
                try:
                    mount_point, total, used, free = line.split()
                    disk_name = mount_point.replace('/mnt/', '')

                    disks.append({
                        "name": disk_name,
                        "mount_point": mount_point,
                        "total": int(total),
                        "used": int(used),
                        "free": int(free),
                        "percentage": round((int(used) / int(total) * 100), 1) if int(total) > 0 else 0,
                    })

                except (ValueError, IndexError) as err:
                    _LOGGER.debug("Error parsing disk usage line '%s': %s", line, err)
                    continue

            return disks

        except (OSError, ValueError) as err:
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
