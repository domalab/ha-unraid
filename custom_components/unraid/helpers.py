"""Helper utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional, Pattern, List, Any
from homeassistant.util import dt as dt_util # type: ignore
from enum import Enum

from .utils import format_bytes



_LOGGER = logging.getLogger(__name__)

@dataclass
class NetworkSpeedUnit:
    """Network unit representation."""
    multiplier: int
    symbol: str

NETWORK_UNITS = [
    NetworkSpeedUnit(1, "bit/s"),
    NetworkSpeedUnit(1000, "kbit/s"),
    NetworkSpeedUnit(1000000, "Mbit/s"),
    NetworkSpeedUnit(1000000000, "Gbit/s"),
]


def get_cpu_info(system_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Get CPU information from system stats."""
    result = {
        "usage": 0.0,
        "cores": 0,
        "model": "Unknown",
        "frequency": 0.0,
    }

    # Get CPU usage
    if "cpu_usage" in system_stats:
        result["usage"] = system_stats["cpu_usage"]

    # Get CPU cores
    if "cpu_cores" in system_stats:
        result["cores"] = system_stats["cpu_cores"]

    # Get CPU model
    if "cpu_model" in system_stats:
        result["model"] = system_stats["cpu_model"]

    # Get CPU frequency
    if "cpu_frequency" in system_stats:
        result["frequency"] = system_stats["cpu_frequency"]

    return result


def get_memory_info(system_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Get memory information from system stats."""
    result = {
        "total": 0,
        "used": 0,
        "free": 0,
        "percentage": 0.0,
    }

    # Get memory usage
    memory_usage = system_stats.get("memory_usage", {})
    if memory_usage:
        result["total"] = memory_usage.get("total", 0)
        result["used"] = memory_usage.get("used", 0)
        result["free"] = memory_usage.get("free", 0)
        result["percentage"] = memory_usage.get("percentage", 0.0)

    return result



# Updated disk and pool mapping code
DISK_NUMBER_PATTERN: Pattern = re.compile(r'disk(\d+)$')
MOUNT_POINT_PATTERN: Pattern = re.compile(r'/mnt/disk(\d+)$')


@dataclass
class DiskInfo:
    """Structured container for disk information."""
    name: str
    mount_point: str
    device_path: str
    size: int = 0
    pool_name: Optional[str] = None
    filesystem: Optional[str] = None
    is_cache: bool = False

    @property
    def is_valid(self) -> bool:
        """Check if disk information is valid."""
        return bool(self.name and self.mount_point and self.device_path)

    @property
    def is_array_disk(self) -> bool:
        """Check if disk is an array disk."""
        return bool(re.match(r'^disk\d+$', self.name))

    @property
    def is_pool_member(self) -> bool:
        """Check if disk is part of a pool."""
        return bool(self.pool_name)

    @property
    def device_type(self) -> str:
        """Get the type of device."""
        if self.is_array_disk:
            return "array"
        elif self.is_pool_member:
            return "pool"
        elif "nvme" in self.device_path:
            return "nvme"
        else:
            return "unknown"

@dataclass
class PoolInfo:
    """Information about an Unraid storage pool."""
    name: str
    mount_point: str
    filesystem: str
    devices: List[str] = field(default_factory=list)
    total_size: int = 0
    used_size: int = 0

    @property
    def is_valid(self) -> bool:
        """Check if pool information is valid."""
        return bool(self.name and self.mount_point and self.filesystem)

def detect_pools(system_stats: dict) -> Dict[str, PoolInfo]:
    """Detect all storage pools in the Unraid system."""
    pools: Dict[str, PoolInfo] = {}
    mount_pattern = re.compile(r'/mnt/([^/]+)')

    # First pass: Identify potential pools from mount points
    for disk in system_stats.get("individual_disks", []):
        try:
            mount_point = disk.get("mount_point", "")
            if not mount_point:
                continue

            # Check for pool mount points
            if match := mount_pattern.match(mount_point):
                pool_name = match.group(1)

                # Skip array mounts (user, disk1, disk2, etc)
                if pool_name in ('user', 'disks') or re.match(r'disk\d+$', pool_name):
                    continue

                # Log detailed information about detected pool
                _LOGGER.info(
                    "Detected potential pool: %s, mount: %s, filesystem: %s",
                    pool_name,
                    mount_point,
                    disk.get("filesystem", "unknown")
                )

                # Create or update pool info
                if pool_name not in pools:
                    pools[pool_name] = PoolInfo(
                        name=pool_name,
                        mount_point=mount_point,
                        filesystem=disk.get("filesystem", "unknown")
                    )

                # Add device to pool
                device = disk.get("device", "")
                if device:
                    pools[pool_name].devices.append(device)

                # Update pool sizes
                pools[pool_name].total_size += int(disk.get("total", 0))
                pools[pool_name].used_size += int(disk.get("used", 0))

        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error processing disk for pools: %s - %s",
                disk.get("name", "unknown"),
                err
            )
            continue

    # Second pass: Check disk mappings for pools that might not be in individual_disks
    disk_mappings = system_stats.get("disk_mappings", {})
    for disk_name, disk_info in disk_mappings.items():
        try:
            # Skip already processed pools and standard array disks
            if disk_name in pools or disk_name in ('user', 'disks') or re.match(r'disk\d+$', disk_name) or disk_name in ('parity', 'parity2', 'flash'):
                continue

            # Check if this is a pool (has filesystem and is mounted)
            filesystem = disk_info.get("filesystem", "")
            # Special handling for ZFS pools
            if filesystem == "zfs" or disk_name in system_stats.get("zfs_pools", {}):
                filesystem = "zfs"
                _LOGGER.info(
                    "Detected ZFS pool: %s",
                    disk_name
                )

            if filesystem and filesystem not in ("", "unknown"):
                _LOGGER.info(
                    "Detected pool from disk mappings: %s, filesystem: %s",
                    disk_name,
                    filesystem
                )

                # Find corresponding disk in individual_disks
                disk_data = None
                for disk in system_stats.get("individual_disks", []):
                    if disk.get("name") == disk_name:
                        disk_data = disk
                        break

                if not disk_data:
                    # Create a minimal disk entry if not found
                    mount_point = f"/mnt/{disk_name}"
                    pools[disk_name] = PoolInfo(
                        name=disk_name,
                        mount_point=mount_point,
                        filesystem=filesystem
                    )

                    # Add device to pool
                    device = disk_info.get("device", "")
                    if device:
                        pools[disk_name].devices.append(device)

                    # Use size information from disk_info if available
                    if "fsSize" in disk_info and "fsUsed" in disk_info:
                        try:
                            pools[disk_name].total_size = int(disk_info.get("fsSize", 0))
                            pools[disk_name].used_size = int(disk_info.get("fsUsed", 0))
                        except (ValueError, TypeError):
                            _LOGGER.warning("Could not parse size info for pool %s", disk_name)
        except Exception as err:
            _LOGGER.warning(
                "Error processing pool from disk mappings: %s - %s",
                disk_name,
                err
            )

    # Log summary of detected pools
    for name, pool in pools.items():
        _LOGGER.info(
            "Detected pool: %s, filesystem: %s, mount: %s, size: %s, used: %s",
            name,
            pool.filesystem,
            pool.mount_point,
            format_bytes(pool.total_size),
            format_bytes(pool.used_size)
        )

    return pools

def get_disk_number(disk_name: str) -> Optional[int]:
    """Extract disk number from disk name with validation."""
    try:
        if not disk_name.startswith("disk"):
            return None
        if match := DISK_NUMBER_PATTERN.match(disk_name):
            return int(match.group(1))
        return None
    except (ValueError, AttributeError) as err:
        _LOGGER.debug("Error extracting disk number from %s: %s", disk_name, err)
        return None

def get_disk_identifiers(coordinator_data: dict, disk_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Get device path and serial number for a disk with consistent fallbacks.

    Note: This function should eventually be migrated to use the DiskMapper class
    in api/disk_mapper.py, which provides more comprehensive disk mapping functionality.
    """
    device = None
    serial = None

    try:
        # First try disk mappings (from disks.ini)
        if disk_mappings := coordinator_data.get("disk_mappings", {}):
            if disk_info := disk_mappings.get(disk_name):
                device = disk_info.get("device")
                serial = disk_info.get("serial")
                _LOGGER.debug(
                    "Found disk info in mappings for %s - device: %s, serial: %s",
                    disk_name, device, serial
                )

        # Then try system stats
        if not (device and serial):
            if system_stats := coordinator_data.get("system_stats", {}):
                # First check in individual_disks
                for disk in system_stats.get("individual_disks", []):
                    if disk.get("name") == disk_name:
                        # Get device if not already found
                        if not device:
                            device = disk.get("device")

                        # Try serial from different possible locations
                        if not serial:
                            # First try direct serial field
                            serial = disk.get("serial")

                            # Then try smart_data.serial_number
                            if not serial and "smart_data" in disk:
                                smart_data = disk.get("smart_data", {})
                                serial = smart_data.get("serial_number")

                                # For NVMe drives, check nvme_smart_health_information_log
                                if not serial and "nvme_smart_health_information_log" in smart_data:
                                    nvme_data = smart_data.get("nvme_smart_health_information_log", {})
                                    serial = nvme_data.get("serial_number")

                            # If still no serial, check if we can get it from the device
                            if not serial and device and device.startswith("/dev/"):
                                _LOGGER.debug("No serial found in disk data, will try to get it from lsblk")
                        break

                # Check if this is a pool
                if not device:
                    pool_info = get_pool_info(system_stats)
                    if disk_name in pool_info:
                        # For pools, use the pool name as the device if no device is specified
                        device = pool_info[disk_name].get("devices", [])[0] if pool_info[disk_name].get("devices") else disk_name
                        _LOGGER.debug(
                            "Using pool device for %s: %s",
                            disk_name, device
                        )

        # Special handling for array disks if device still not found
        if not device and disk_name.startswith("disk"):
            if disk_num := get_disk_number(disk_name):
                device = f"sd{chr(ord('b') + disk_num - 1)}"
                _LOGGER.debug(
                    "Falling back to calculated device for %s: %s",
                    disk_name, device
                )

        # Special handling for cache disk
        elif not device and disk_name == "cache":
            device = "nvme0n1"
            _LOGGER.debug("Using default NVMe device for cache")

        # No special handling for ZFS pools - ZFS support has been removed

        return device, serial

    except Exception as err:
        _LOGGER.error(
            "Error getting disk identifiers for %s: %s",
            disk_name, err,
            exc_info=True
        )
        return None, None



def get_pool_info(system_stats: dict) -> Dict[str, Dict[str, Any]]:
    """Get detailed information about all storage pools."""
    pools = detect_pools(system_stats)
    pool_info = {}

    for name, pool in pools.items():
        pool_info[name] = {
            "name": name,
            "mount_point": pool.mount_point,
            "filesystem": pool.filesystem,
            "devices": pool.devices,
            "total_size": pool.total_size,
            "used_size": pool.used_size,
            "free_size": pool.total_size - pool.used_size,
            "usage_percent": (pool.used_size / pool.total_size * 100) if pool.total_size > 0 else 0
        }

    return pool_info

# extract_fans_data function has been moved to utils.py to avoid circular imports

def is_solid_state_drive(disk_data: dict) -> bool:
    """Determine if a disk is a solid state drive (NVME or SSD)."""
    try:
        # Guard against None or invalid disk_data
        if not disk_data or not isinstance(disk_data, dict):
            _LOGGER.debug("Invalid disk_data provided to is_solid_state_drive: %s", disk_data)
            return False

        # Check device path for nvme
        device = disk_data.get("device")
        if device and isinstance(device, str) and "nvme" in device.lower():
            return True

        # Check if it's a cache device
        if disk_data.get("name") == "cache":
            return True

        # Check smart data for rotation rate (0 indicates SSD)
        smart_data = disk_data.get("smart_data", {})
        if isinstance(smart_data, dict):
            rotation_rate = smart_data.get("rotation_rate")
            if rotation_rate == 0:
                return True

        return False

    except (AttributeError, TypeError, ValueError) as err:
        _LOGGER.debug(
            "Error checking if disk is SSD: %s - Error: %s",
            disk_data.get("name", "unknown"),
            err
        )
        return False



class DiskDataHelperMixin:
    """Mixin providing common disk data handling methods."""

    def _calculate_usage_percentage(self, total: int, used: int) -> Optional[float]:
        """Calculate storage usage percentage with error handling."""
        try:
            if total > 0:
                return round((used / total) * 100, 1)
            return 0.0
        except (TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Error calculating usage percentage: %s", err)
            return None

    def _get_storage_attributes(
        self,
        total: int,
        used: int,
        free: int,
        mount_point: Optional[str] = None,
        device: Optional[str] = None,
        is_standby: bool = False
    ) -> Dict[str, Any]:
        """Get common storage attributes with user-friendly formatting."""
        try:
            # Use centralized percentage calculation
            usage = self._calculate_usage_percentage(total, used)
            percentage = 0.0 if usage is None else usage

            attrs = {
                "Total Capacity": format_bytes(total),
                "Space Used": format_bytes(used),
                "Space Available": format_bytes(free),
                "Usage Percentage": f"{percentage:.1f}%",
                "Power State": "Standby (Spun Down)" if is_standby else "Active",
                "Last Updated": dt_util.utcnow().isoformat()
            }

            # Add mount point with user-friendly label
            if mount_point:
                attrs["Mount Location"] = mount_point

            # Add device with user-friendly label
            if device:
                attrs["Device Path"] = device

            # Add capacity utilization description
            if percentage is not None:
                if percentage >= 95:
                    attrs["Capacity Status"] = "Critical - Nearly Full"
                elif percentage >= 85:
                    attrs["Capacity Status"] = "Warning - High Usage"
                elif percentage >= 70:
                    attrs["Capacity Status"] = "Moderate Usage"
                else:
                    attrs["Capacity Status"] = "Normal"
            else:
                attrs["Capacity Status"] = "Unknown"

            return attrs

        except Exception as err:
            _LOGGER.error("Error creating storage attributes: %s", err)
            return {
                "Total Capacity": "Unknown",
                "Space Used": "Unknown",
                "Space Available": "Unknown",
                "Usage Percentage": "0.0%",
                "Power State": "Unknown",
                "Capacity Status": "Unknown",
                "Last Updated": dt_util.utcnow().isoformat()
            }

    def _get_temperature_str(
        self,
        temp_value: Optional[int],
        is_standby: bool = False
    ) -> str:
        """Get temperature string with standardized standby handling."""
        if is_standby:
            return "N/A (Standby)"
        if temp_value is None:
            return "N/A"
        return f"{temp_value}°C"

class SpeedUnit(Enum):
    """Speed units with their multipliers."""
    BYTES = (1, "B")
    KILOBYTES = (1024, "KB")
    MEGABYTES = (1024 * 1024, "MB")
    GIGABYTES = (1024 * 1024 * 1024, "GB")

    def __init__(self, multiplier: int, symbol: str):
        self.multiplier = multiplier
        self.symbol = symbol

    @classmethod
    def from_symbol(cls, symbol: str) -> "SpeedUnit":
        """Get unit from symbol."""
        for unit in cls:
            if unit.symbol == symbol.upper():
                return unit
        raise ValueError(f"Unknown speed unit: {symbol}")

def parse_speed_string(speed_str: str) -> float:
    """Parse speed string and return value in bytes per second.

    Handles multiple formats:
    - Raw bytes/sec (e.g., "124194045")
    - Formatted speed (e.g., "125.5 MB/s", "84,8 MB/s")
    - Special values (e.g., "Unavailable", "nan B/s", "0")
    - European number format with comma decimal separator
    """
    try:
        # Clean up the string
        speed_str = speed_str.strip()

        # Handle special cases
        if speed_str in ["Unavailable", "nan B/s", "0"]:
            return 0.0

        # Try parsing as raw bytes/sec first (handle European format)
        try:
            # Handle European number format for raw bytes
            raw_value = speed_str.replace(',', '.') if ',' in speed_str and '.' not in speed_str else speed_str
            return float(raw_value)
        except ValueError:
            pass

        # Handle formatted speed strings
        speed_str = speed_str.replace('/s', '').strip()
        speed_str = speed_str.replace('MB B', 'MB').replace('GB B', 'GB')

        # Split into value and unit
        parts = speed_str.split()
        if len(parts) != 2:
            # Try extracting numbers if units are stuck to value
            # Updated regex to handle both dot and comma decimal separators
            import re
            match = re.match(r"(\d+[.,]?\d*)([A-Za-z]+)", speed_str)
            if match:
                value, unit = match.groups()
            else:
                raise ValueError(f"Invalid speed format: {speed_str}")
        else:
            value, unit = parts

        # Convert European number format (comma decimal) to standard format (dot decimal)
        if ',' in value and '.' not in value:
            value = value.replace(',', '.')

        # Convert value to float
        speed = float(value)

        # Handle case where unit might have extra text
        unit = unit.replace('B/s', 'B').replace('B', '').strip() + 'B'

        # Get unit multiplier
        unit_enum = SpeedUnit.from_symbol(unit)
        return speed * unit_enum.multiplier

    except (ValueError, IndexError) as err:
        if "Unavailable" in str(err):
            return 0.0
        raise ValueError(f"Could not parse speed string '{speed_str}': {err}")
