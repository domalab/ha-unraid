"""Helper utilities for Unraid integration."""
from __future__ import annotations

from collections import defaultdict
import datetime
import logging
import re
import math
from dataclasses import dataclass, field
from typing import Set, Tuple, Dict, Optional, Pattern, List, Any
from homeassistant.util import dt as dt_util # type: ignore
from enum import Enum

from .sensors.const import (
    CHIPSET_FAN_PATTERNS,
    CPU_CORE_PATTERN,
    CPU_PECI_PATTERN,
    CPU_TCCD_PATTERN,
    DEFAULT_FAN_PATTERNS,
    DEFAULT_RPM_KEYS,
    FAN_NUMBER_PATTERNS,
    MB_ACPI_PATTERN,
    MB_AUXTIN_PATTERN,
    MB_EC_PATTERN,
    MB_SYSTEM_PATTERN,
    MIN_VALID_RPM,
    MAX_VALID_RPM,
    CPU_KEYWORDS,
    MB_KEYWORDS,
    VALID_CPU_TEMP_RANGE,
    VALID_MB_TEMP_RANGE,
    KNOWN_SENSOR_CHIPS,
)

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

            # Identify chipset
            chipset = None
            chipset_pattern = None
            for chip_key in CHIPSET_FAN_PATTERNS:
                if chip_key in device.lower():
                    chipset = chip_key
                    chipset_pattern = CHIPSET_FAN_PATTERNS[chip_key]
                    break
            
            # Use chipset-specific or default patterns
            patterns = (chipset_pattern.patterns if chipset_pattern 
                    else DEFAULT_FAN_PATTERNS)
            rpm_keys = (chipset_pattern.rpm_keys if chipset_pattern 
                    else DEFAULT_RPM_KEYS)

            # Look for fan readings
            for key, value in readings.items():
                key_lower = key.lower()
                
                if any(pattern in key_lower for pattern in patterns):
                    try:
                        # Extract fan number
                        fan_num = "1"  # Default
                        for pattern in FAN_NUMBER_PATTERNS:
                            if match := re.search(pattern, key_lower):
                                fan_num = match.group(1)
                                break
                        
                        # Get RPM value
                        rpm_val = None
                        if isinstance(value, dict):
                            for rpm_key in rpm_keys:
                                formatted_key = rpm_key.format(fan_num)
                                if formatted_key in value:
                                    rpm_val = float(value[formatted_key])
                                    break
                                elif rpm_key in value:
                                    rpm_val = float(value[rpm_key])
                                    break
                        else:
                            rpm_str = str(value).upper().replace("RPM", "").strip()
                            rpm_val = float(rpm_str)
                        
                        if (rpm_val is not None and 
                            MIN_VALID_RPM <= rpm_val <= MAX_VALID_RPM):
                            
                            base_name = f"{device}_{key_lower}".replace(" ", "_")
                            base_name = re.sub(r'[^a-z0-9_]', '_', base_name)
                            base_name = re.sub(r'_+', '_', base_name).strip('_')
                            
                            display_name = (f"{chipset.upper()} Fan {fan_num}" 
                                        if chipset else f"System Fan {fan_num}")
                            
                            fan_data[base_name] = {
                                "rpm": int(rpm_val),
                                "label": display_name,
                                "device": device,
                                "chipset": chipset or "unknown",
                                "channel": int(fan_num)
                            }
                            
                            _LOGGER.debug(
                                "Added %s fan: %s with %d RPM",
                                chipset or "generic",
                                base_name,
                                int(rpm_val)
                            )
                            
                    except (ValueError, TypeError, KeyError) as err:
                        _LOGGER.debug(
                            "Error parsing fan for chipset %s: %s - %s",
                            chipset or "unknown",
                            value,
                            err
                        )
                        continue

        _LOGGER.debug(
            "Found %d fans across %d chipsets", 
            len(fan_data),
            len(set(f["chipset"] for f in fan_data.values()))
        )
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

@dataclass
class TempReading:
    """Temperature reading with metadata."""
    value: float
    source: str
    chip: str
    label: str
    last_update: datetime = None
    is_valid: bool = True

    def __post_init__(self):
        """Initialize timestamp if not provided."""
        if self.last_update is None:
            self.last_update = datetime.now()

def is_valid_temp_range(temp: float, is_cpu: bool = True) -> bool:
    """Check if temperature is within valid range."""
    if not isinstance(temp, (int, float)):
        return False
        
    valid_range = VALID_CPU_TEMP_RANGE if is_cpu else VALID_MB_TEMP_RANGE
    return valid_range[0] <= temp <= valid_range[1]

def parse_temperature(value: str) -> Optional[float]:
    """Parse temperature value from string with comprehensive validation."""
    try:
        # Remove common temperature markers
        cleaned = value.replace('°C', '').replace(' C', '').replace('+', '').strip()
        
        # Convert to float and validate
        if cleaned and not cleaned.isspace():
            temp = float(cleaned)
            return temp if -50 <= temp <= 150 else None
            
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Error parsing temperature value '%s': %s", value, err)
    
    return None

def categorize_sensor(label: str, chip: str, overrides: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Categorize a sensor as 'cpu' or 'mb' based on label and chip name."""
    if not label or not isinstance(label, str):
        return None
        
    # Check overrides first
    if overrides and label in overrides:
        override = overrides[label].lower()
        if override in ('cpu', 'mb'):
            return override
        if override == 'ignore':
            return None
            
    # Convert to lowercase for matching
    label_lower = label.lower()
    chip_lower = chip.lower() if chip else ""
    
    # Check if it's a known sensor chip
    for chip_prefix, valid_labels in KNOWN_SENSOR_CHIPS.items():  # Changed from KNOWN_GOOD_CHIPS
        if chip_lower.startswith(chip_prefix.lower()):
            if any(valid.lower() in label_lower for valid in valid_labels):
                return 'cpu' if any(cpu_key in label_lower for cpu_key in CPU_KEYWORDS) else 'mb'
                
    # Check dynamic patterns
    if (CPU_CORE_PATTERN.match(label) or 
        CPU_TCCD_PATTERN.match(label) or 
        CPU_PECI_PATTERN.match(label)):
        return 'cpu'
        
    if (MB_SYSTEM_PATTERN.match(label) or
        MB_EC_PATTERN.match(label) or
        MB_ACPI_PATTERN.match(label)):
        return 'mb'
        
    # Skip known problematic sensors
    if MB_AUXTIN_PATTERN.match(label):
        _LOGGER.debug("Skipping known problematic AUXTIN sensor: %s", label)
        return None
        
    # Check keywords
    if any(keyword in label_lower or keyword in chip_lower 
        for keyword in CPU_KEYWORDS):
        return 'cpu'
    if any(keyword in label_lower or keyword in chip_lower 
        for keyword in MB_KEYWORDS):
        return 'mb'
        
    # Log unmatched sensor for debugging
    _LOGGER.debug(
        "Unmatched sensor - Label: '%s', Chip: '%s'",
        label,
        chip
    )
    return None

def find_temperature_inputs(
    sensors_data: Dict[str, Any],
    overrides: Optional[Dict[str, str]] = None
) -> Dict[str, Set[TempReading]]:
    """Find all valid temperature inputs in sensors data."""
    temps: Dict[str, Set[TempReading]] = defaultdict(set)
    
    try:
        for chip, readings in sensors_data.items():
            if not isinstance(readings, dict):
                continue
                
            for label, values in readings.items():
                # Handle both nested dict and direct value cases
                if isinstance(values, dict):
                    for key, value in values.items():
                        if 'temp' in key.lower() and 'input' in key.lower():
                            temp = parse_temperature(str(value))
                            if temp is not None:
                                category = categorize_sensor(label, chip, overrides)
                                if category:
                                    is_valid = is_valid_temp_range(
                                        temp, 
                                        is_cpu=(category == 'cpu')
                                    )
                                    temps[category].add(TempReading(
                                        value=temp,
                                        source=key,
                                        chip=chip,
                                        label=label,
                                        is_valid=is_valid
                                    ))
                elif 'temp' in label.lower():
                    temp = parse_temperature(str(values))
                    if temp is not None:
                        category = categorize_sensor(label, chip, overrides)
                        if category:
                            is_valid = is_valid_temp_range(
                                temp,
                                is_cpu=(category == 'cpu')
                            )
                            temps[category].add(TempReading(
                                value=temp,
                                source='direct',
                                chip=chip,
                                label=label,
                                is_valid=is_valid
                            ))
                            
        return dict(temps)
        
    except Exception as err:
        _LOGGER.error(
            "Error finding temperature inputs: %s",
            err,
            exc_info=True
        )
        return {}

def get_core_temp_input(sensor_label: str) -> Optional[str]:
    """Map CPU core labels to temperature input files."""
    if match := CPU_CORE_PATTERN.match(sensor_label):
        core_index = int(match.group(1))
        return f"temp{core_index + 2}_input"  # Core 0 -> temp2_input, etc.
    return None

def get_tccd_temp_input(sensor_label: str) -> Optional[str]:
    """Map AMD CCD temperature labels to input files."""
    if match := CPU_TCCD_PATTERN.match(sensor_label):
        ccd_index = int(match.group(1))
        return f"temp{ccd_index + 3}_input"  # Tccd1 -> temp4_input, etc.
    return None

def get_peci_temp_input(sensor_label: str) -> Optional[str]:
    """Map PECI agent labels to temperature input files."""
    if match := CPU_PECI_PATTERN.match(sensor_label):
        peci_index = int(match.group(1))
        return f"temp{peci_index + 7}_input"  # PECI Agent 0 -> temp7_input
    return None

def get_system_temp_input(sensor_label: str) -> Optional[str]:
    """Map System N labels to temperature input files."""
    if match := MB_SYSTEM_PATTERN.match(sensor_label):
        sys_index = int(match.group(1))
        return f"temp{sys_index + 1}_input"  # System 1 -> temp2_input, etc.
    return None

def get_ec_temp_input(sensor_label: str) -> Optional[str]:
    """Map EC_TEMP[N] labels to temperature input files."""
    if match := MB_EC_PATTERN.match(sensor_label):
        ec_index = int(match.group(1))
        return f"temp{ec_index}_input"  # EC_TEMP1 -> temp1_input, etc.
    return None

def get_auxtin_temp_input(sensor_label: str) -> Optional[str]:
    """Map AUXTIN[N] labels to temperature input files."""
    if match := MB_AUXTIN_PATTERN.match(sensor_label):
        aux_index = int(match.group(1))
        return f"temp{aux_index + 3}_input"  # AUXTIN0 -> temp3_input, etc.
    return None

def get_acpi_temp_input(sensor_label: str) -> Optional[str]:
    """Map ACPI temperature labels to input files."""
    if MB_ACPI_PATTERN.match(sensor_label):
        return "temp1_input"  # acpitz-acpi-0 -> temp1_input
    return None

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
    - Formatted speed (e.g., "125.5 MB/s")
    - Special values (e.g., "Unavailable", "nan B/s", "0")
    """
    try:
        # Clean up the string
        speed_str = speed_str.strip()
        
        # Handle special cases
        if speed_str in ["Unavailable", "nan B/s", "0"]:
            return 0.0
            
        # Try parsing as raw bytes/sec first
        try:
            return float(speed_str)
        except ValueError:
            pass
            
        # Handle formatted speed strings
        speed_str = speed_str.replace('/s', '').strip()
        speed_str = speed_str.replace('MB B', 'MB').replace('GB B', 'GB')
        
        # Split into value and unit
        parts = speed_str.split()
        if len(parts) != 2:
            # Try extracting numbers if units are stuck to value
            import re
            match = re.match(r"(\d+\.?\d*)([A-Za-z]+)", speed_str)
            if match:
                value, unit = match.groups()
            else:
                raise ValueError(f"Invalid speed format: {speed_str}")
        else:
            value, unit = parts
            
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
