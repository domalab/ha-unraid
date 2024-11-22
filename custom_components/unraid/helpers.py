"""Helper utilities for Unraid integration."""
from enum import Enum
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
                
        except Exception as err:
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

def get_unraid_disk_mapping(system_stats: dict) -> Dict[str, str]:
    """Get mapping between Unraid disk numbers and Linux device names."""
    mapping: Dict[str, str] = {}
    pools = detect_pools(system_stats)
    
    if "individual_disks" not in system_stats:
        _LOGGER.debug("No disk information found in system stats")
        return mapping
        
    # Process each disk
    for disk in system_stats.get("individual_disks", []):
        try:
            # Parse disk information
            disk_info = DiskInfo(
                name=disk.get("name", ""),
                mount_point=disk.get("mount_point", ""),
                device_path=disk.get("device", ""),
                size=int(disk.get("total", 0)),
                filesystem=disk.get("filesystem", ""),
                is_cache="cache" in disk.get("name", "").lower()
            )
            
            if not disk_info.is_valid:
                continue
                
            # Skip non-array and non-pool disks
            if not (disk_info.name.startswith("disk") or disk_info.is_cache):
                continue

            # Check if disk belongs to a pool
            for pool_name, pool_info in pools.items():
                if disk_info.device_path in pool_info.devices:
                    disk_info.pool_name = pool_name
                    break
                
            # Process based on disk type
            if disk_info.is_pool_member:
                # Handle pool member
                device_num = pools[disk_info.pool_name].devices.index(disk_info.device_path) + 1
                device_type = "nvme" if "nvme" in disk_info.device_path else "disk"
                pool_device_name = f"{disk_info.pool_name}_{device_type}{device_num}"
                mapping[pool_device_name] = disk_info.device_path
                _LOGGER.debug(
                    "Mapped pool device %s to device %s (pool: %s)",
                    pool_device_name,
                    disk_info.device_path,
                    disk_info.pool_name
                )
            elif disk_info.is_cache:
                # Handle legacy cache disk
                if validate_device_path(disk_info.device_path):
                    mapping[disk_info.name] = disk_info.device_path
                    _LOGGER.debug(
                        "Mapped cache disk %s to device %s",
                        disk_info.name,
                        disk_info.device_path
                    )
            else:
                # Handle array disk
                device_name = process_array_disk(disk_info)
                if device_name:
                    mapping[disk_info.name] = device_name
                    _LOGGER.debug(
                        "Mapped array disk %s to device %s",
                        disk_info.name,
                        device_name
                    )
                    
        except Exception as err:
            _LOGGER.warning(
                "Error processing disk %s: %s",
                disk.get("name", "unknown"),
                err
            )
            continue
            
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