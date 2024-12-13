"""Helper utilities for Unraid integration."""
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional, Pattern, List, Any
import math
import logging
import re

_LOGGER = logging.getLogger(__name__)

# Keep existing NetworkSpeedUnit class and related functions
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

def get_network_speed_unit(bytes_per_sec: float) -> Tuple[float, str]:
    """Get the most appropriate unit for a given network speed."""
    if bytes_per_sec <= 0:
        return (0.0, NETWORK_UNITS[0].symbol)

    # Convert bytes to bits
    bits_per_sec = bytes_per_sec * 8

    # Find the appropriate unit
    unit_index = min(
        len(NETWORK_UNITS) - 1,
        max(0, math.floor(math.log10(bits_per_sec) / 3))
    )

    selected_unit = NETWORK_UNITS[unit_index]
    converted_value = bits_per_sec / selected_unit.multiplier

    return (round(converted_value, 2), selected_unit.symbol)

def format_bytes(bytes_value: float) -> str:
    """Format bytes into appropriate units."""
    if bytes_value <= 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = min(
        len(units) - 1,
        max(0, math.floor(math.log10(bytes_value) / 3))
    )

    value = bytes_value / (1024 ** unit_index)
    return f"{value:.2f} {units[unit_index]}"

# Updated disk and pool mapping code
DISK_NUMBER_PATTERN: Pattern = re.compile(r'disk(\d+)$')
MOUNT_POINT_PATTERN: Pattern = re.compile(r'/mnt/disk(\d+)$')
VALID_DEVICE_PATTERN: Pattern = re.compile(r'^[a-zA-Z0-9/_-]+$')

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

    return pools

def get_disk_number(disk_name: str) -> Optional[int]:
    """Extract disk number from disk name."""
    if match := DISK_NUMBER_PATTERN.search(disk_name):
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def validate_device_path(device_path: str) -> bool:
    """Validate device path format."""
    if not device_path:
        return False

    # Only validate the format, not existence
    if not VALID_DEVICE_PATTERN.match(device_path):
        _LOGGER.debug("Invalid device path format: %s", device_path)
        return False

    return True

def process_cache_disk(disk_info: DiskInfo) -> Optional[str]:
    """Process cache disk to extract device name."""
    if not validate_device_path(disk_info.device_path):
        return None

    # For cache disks, use the device path directly
    return disk_info.device_path

def process_array_disk(disk_info: DiskInfo) -> Optional[str]:
    """Process array disk to extract device name."""
    if not validate_device_path(disk_info.device_path):
        return None

    # Extract disk number from mount point or name
    disk_num = get_disk_number(disk_info.name)
    if disk_num is None:
        _LOGGER.debug(
            "Could not extract disk number from %s",
            disk_info.name
        )
        return None

    # Verify mount point matches disk number
    mount_match = MOUNT_POINT_PATTERN.search(disk_info.mount_point)
    if not mount_match or int(mount_match.group(1)) != disk_num:
        _LOGGER.debug(
            "Mount point mismatch for disk %s: %s",
            disk_info.name,
            disk_info.mount_point
        )
        return None

    # For array disks, start from sdb
    device = f"sd{chr(ord('b') + disk_num - 1)}"
    return device

def get_unraid_disk_mapping(system_stats: dict) -> Dict[str, Dict[str, Any]]:
    """Get mapping between Unraid disk names, devices, and serial numbers."""
    mapping: Dict[str, Dict[str, Any]] = {}

    # Check for disk data
    individual_disks = system_stats.get("individual_disks", [])
    if not individual_disks:
        _LOGGER.debug("No disk information found in system stats")
        return mapping

    try:
        # Ignore special directories and tmpfs
        ignored_mounts = {
            "disks", "remotes", "addons", "rootshare", 
            "user/0", "dev/shm"
        }

        # Filter out disks we want to ignore
        valid_disks = [
            disk for disk in individual_disks
            if (
                disk.get("name")
                and not any(mount in disk.get("mount_point", "") for mount in ignored_mounts)
                and disk.get("filesystem") != "tmpfs"  # Explicitly ignore tmpfs
            )
        ]

        # First, handle array disks (disk1, disk2, etc.)
        base_device = 'b'  # Start at sdb
        array_disks = sorted(
            [disk for disk in valid_disks if disk.get("name", "").startswith("disk")],
            key=lambda x: int(x["name"].replace("disk", ""))
        )

        # Map array disks
        for disk in array_disks:
            disk_name = disk.get("name")
            if disk_name:
                device = f"sd{base_device}"
                mapping[disk_name] = {
                    "device": device,
                    "serial": disk.get("serial", ""),
                    "name": disk_name
                }
                _LOGGER.debug(
                    "Mapped array disk %s to device %s (serial: %s)",
                    disk_name,
                    device,
                    disk.get("serial", "unknown")
                )
                base_device = chr(ord(base_device) + 1)

        # Handle parity disk
        for disk in valid_disks:
            if disk.get("name") == "parity":
                device = disk.get("device")
                if device:
                    mapping["parity"] = {
                        "device": device,
                        "serial": disk.get("serial", ""),
                        "name": "parity"
                    }
                    _LOGGER.debug(
                        "Mapped parity disk to device %s (serial: %s)",
                        device,
                        disk.get("serial", "unknown")
                    )

        # Then handle cache disk if present
        for disk in valid_disks:
            if disk.get("name") == "cache":
                device = disk.get("device")
                if device:
                    mapping["cache"] = {
                        "device": device,
                        "serial": disk.get("serial", ""),
                        "name": "cache"
                    }
                    _LOGGER.debug(
                        "Mapped cache disk to device %s (serial: %s)",
                        device,
                        disk.get("serial", "unknown")
                    )

        return mapping

    except (KeyError, ValueError, AttributeError) as err:
        _LOGGER.debug("Error creating disk mapping: %s", err)
        return mapping

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
