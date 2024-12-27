"""Helper utilities for Unraid integration."""
import logging
import re
import math
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional, Pattern, List, Any
from homeassistant.util import dt as dt_util # type: ignore

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
    """Get device path and serial number for a disk with consistent fallbacks."""
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
                for disk in system_stats.get("individual_disks", []):
                    if disk.get("name") == disk_name:
                        # Get device if not already found
                        if not device:
                            device = disk.get("device")
                        
                        # Try serial from different possible locations
                        if not serial:
                            serial = (
                                disk.get("serial")
                                or disk.get("smart_data", {}).get("serial_number")
                            )
                        break

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

        return device, serial

    except Exception as err:
        _LOGGER.error(
            "Error getting disk identifiers for %s: %s",
            disk_name, err,
            exc_info=True
        )
        return None, None

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

def extract_fans_data(sensors_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Extract fan RPM data from sensors output."""
    fan_data = {}
    
    try:
        for device, readings in sensors_data.items():
            if not isinstance(readings, dict):
                continue

            # Look for entries with "Array Fan" in the key
            for key, value in readings.items():
                if "array fan" in key.lower() and "rpm" in str(value).lower():
                    try:
                        # Extract RPM value
                        rpm_str = str(value).upper().replace("RPM", "").strip()
                        rpm_val = int(float(rpm_str))
                        
                        # Get fan number if present
                        fan_num = "1"  # Default if no number found
                        if "#" in key:
                            fan_num = key.split("#")[-1].strip()
                            
                        # Generate clean fan key
                        base_name = f"{device}_array_fan_{fan_num}".lower()
                        base_name = re.sub(r'[^a-z0-9_]', '_', base_name)
                        base_name = re.sub(r'_+', '_', base_name).strip('_')
                        
                        if rpm_val >= 0 and rpm_val < 10000:  # Validate RPM value
                            fan_data[base_name] = {
                                "rpm": rpm_val,
                                "label": f"System Fan {fan_num}",
                                "device": device
                            }
                            _LOGGER.debug(
                                "Added fan: %s with %d RPM",
                                base_name,
                                rpm_val
                            )
                    except (ValueError, TypeError) as err:
                        _LOGGER.debug(
                            "Error parsing fan RPM value '%s': %s",
                            value,
                            err
                        )
                        continue

        _LOGGER.debug("Found %d fans: %s", len(fan_data), list(fan_data.keys()))
        return fan_data
        
    except Exception as err:
        _LOGGER.error("Error extracting fan data: %s", err, exc_info=True)
        return {}

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
        """Get common storage attributes with unified calculation."""
        try:
            # Use centralized percentage calculation
            usage = self._calculate_usage_percentage(total, used)
            percentage = 0.0 if usage is None else usage
            
            attrs = {
                "total_size": format_bytes(total),
                "used_space": format_bytes(used),
                "free_space": format_bytes(free),
                "percentage": percentage,
                "power_state": "standby" if is_standby else "active",
                "last_update": dt_util.utcnow().isoformat()
            }

            if mount_point:
                attrs["mount_point"] = mount_point
            if device:
                attrs["device"] = device

            return attrs

        except Exception as err:
            _LOGGER.error("Error creating storage attributes: %s", err)
            return {
                "total_size": "unknown",
                "used_space": "unknown",
                "free_space": "unknown",
                "percentage": 0.0,
                "last_update": dt_util.utcnow().isoformat()
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