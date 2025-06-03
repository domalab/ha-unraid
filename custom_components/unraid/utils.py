"""Utility functions for Unraid integration."""
from __future__ import annotations

import re
import math
import logging
import datetime
from typing import Tuple, Dict, Any, Set, List, Optional
from collections import defaultdict
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    """Normalize a name for use in entity IDs."""
    # Convert to lowercase and replace invalid characters with underscores
    normalized = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    # Remove consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    return normalized.strip('_')

def validate_entity_name(name: str) -> bool:
    """Validate entity name follows conventions."""
    return bool(re.match(r'^[a-z0-9_]+$', name))

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

def get_network_speed_unit(bytes_per_sec: float) -> Tuple[float, str]:
    """Get the most appropriate unit for a given network speed."""
    if bytes_per_sec <= 0:
        return (0.0, "bit/s")

    # Convert bytes to bits
    bits_per_sec = bytes_per_sec * 8

    # Define network units
    units = [
        (1, "bit/s"),
        (1000, "kbit/s"),
        (1000000, "Mbit/s"),
        (1000000000, "Gbit/s"),
    ]

    # Find the appropriate unit
    unit_index = min(
        len(units) - 1,
        max(0, math.floor(math.log10(bits_per_sec) / 3))
    )

    multiplier, symbol = units[unit_index]
    converted_value = bits_per_sec / multiplier

    return (round(converted_value, 2), symbol)


# Temperature-related constants
CPU_CORE_PATTERN = re.compile(r"^Core\s+(\d+)$", re.IGNORECASE)
CPU_TCCD_PATTERN = re.compile(r"^Tccd(\d+)$", re.IGNORECASE)
CPU_PECI_PATTERN = re.compile(r"^PECI Agent\s+(\d+)$", re.IGNORECASE)
MB_SYSTEM_PATTERN = re.compile(r"^System\s+(\d+)$", re.IGNORECASE)
MB_EC_PATTERN = re.compile(r"^EC_TEMP(\d+)$", re.IGNORECASE)
MB_AUXTIN_PATTERN = re.compile(r"^AUXTIN(\d+)$", re.IGNORECASE)
MB_ACPI_PATTERN = re.compile(r"^acpitz-acpi-(\d+)$", re.IGNORECASE)

# Temperature ranges
VALID_CPU_TEMP_RANGE: Tuple[float, float] = (-10.0, 120.0)
VALID_MB_TEMP_RANGE: Tuple[float, float] = (-10.0, 100.0)

# CPU and MB keywords for temperature categorization
CPU_KEYWORDS: Set[str] = {
    "cpu", "core", "package", "k10temp", "coretemp",
    "ccd", "tctl", "tdie", "ryzen", "intel", "amd"
}

MB_KEYWORDS: Set[str] = {
    "mb", "board", "pch", "systin", "system", "chipset",
    "northbridge", "southbridge", "acpi", "motherboard"
}

# Define known good sensor chips and their temperature input keys
KNOWN_SENSOR_CHIPS: Dict[str, List[str]] = {
    "coretemp-isa": ["Package id 0", "Core 0"],
    "k10temp-pci": ["Tctl", "Tdie"],
    "nct6791-isa": ["SYSTIN", "CPUTIN"],
    "it8688-isa": ["CPU Temperature", "System 1"],
}

@dataclass(frozen=True)
class TempReading:
    """Temperature reading with metadata."""
    value: float
    source: str
    chip: str
    label: str
    last_update: datetime.datetime = field(default_factory=datetime.datetime.now)  # set default before its frozen
    is_valid: bool = True

def is_valid_temp_range(temp: float, is_cpu: bool = True) -> bool:
    """Check if temperature is within valid range."""
    if not isinstance(temp, (int, float)):
        return False

    valid_range = VALID_CPU_TEMP_RANGE if is_cpu else VALID_MB_TEMP_RANGE
    return valid_range[0] <= temp <= valid_range[1]

def parse_temperature(value: str) -> Optional[float]:
    """Parse temperature value from string with comprehensive validation."""
    try:
        # Handle None input
        if value is None:
            return None

        # Remove common temperature markers
        cleaned = value.replace('°C', '').replace(' C', '').replace('C', '').replace('+', '').strip()

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
    for chip_prefix, valid_labels in KNOWN_SENSOR_CHIPS.items():
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

def get_temp_input(sensor_label: str) -> Optional[str]:
    """Map sensor labels to temperature input files.

    This consolidated function replaces multiple individual mapping functions
    by handling all sensor types in a single function with pattern matching.

    Args:
        sensor_label: The sensor label to map

    Returns:
        The corresponding temperature input file name or None if no match
    """
    # CPU Core temperature mapping
    if match := CPU_CORE_PATTERN.match(sensor_label):
        core_index = int(match.group(1))
        return f"temp{core_index + 2}_input"  # Core 0 -> temp2_input, etc.

    # AMD CCD temperature mapping
    elif match := CPU_TCCD_PATTERN.match(sensor_label):
        ccd_index = int(match.group(1))
        return f"temp{ccd_index + 3}_input"  # Tccd1 -> temp4_input, etc.

    # PECI agent temperature mapping
    elif match := CPU_PECI_PATTERN.match(sensor_label):
        peci_index = int(match.group(1))
        return f"temp{peci_index + 7}_input"  # PECI Agent 0 -> temp7_input

    # System temperature mapping
    elif match := MB_SYSTEM_PATTERN.match(sensor_label):
        sys_index = int(match.group(1))
        return f"temp{sys_index + 1}_input"  # System 1 -> temp2_input, etc.

    # EC temperature mapping
    elif match := MB_EC_PATTERN.match(sensor_label):
        ec_index = int(match.group(1))
        return f"temp{ec_index}_input"  # EC_TEMP1 -> temp1_input, etc.

    # AUXTIN temperature mapping
    elif match := MB_AUXTIN_PATTERN.match(sensor_label):
        aux_index = int(match.group(1))
        return f"temp{aux_index + 3}_input"  # AUXTIN0 -> temp3_input, etc.

    # ACPI temperature mapping
    elif MB_ACPI_PATTERN.match(sensor_label):
        return "temp1_input"  # acpitz-acpi-0 -> temp1_input

    return None



def extract_fans_data(sensors_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Extract fan RPM data from sensors output."""
    fan_data = {}

    try:
        # Log available sensor data for debugging
        _LOGGER.debug(
            "Processing sensor data for fan extraction: %d devices",
            len(sensors_data)
        )

        # Enhanced diagnostic logging for troubleshooting
        if _LOGGER.isEnabledFor(logging.DEBUG):
            device_names = list(sensors_data.keys())
            _LOGGER.debug("Available sensor devices: %s", device_names)

            # Log potential fan-related keys for diagnosis
            for device, readings in sensors_data.items():
                if isinstance(readings, dict):
                    fan_related_keys = [k for k in readings.keys()
                                      if any(term in k.lower() for term in
                                           ['fan', 'rpm', 'cooling', 'tach', 'pwm'])]
                    if fan_related_keys:
                        _LOGGER.debug("Device %s has potential fan keys: %s",
                                    device, fan_related_keys)

        # Define constants needed for fan extraction
        MIN_VALID_RPM = 0
        MAX_VALID_RPM = 10000
        DEFAULT_FAN_PATTERNS = ["fan", "sys_fan", "chassis_fan"]
        DEFAULT_RPM_KEYS = ["fan{}_input", "fan_input", "speed"]
        FAN_NUMBER_PATTERNS = [
            r'fan(\d+)',
            r'#(\d+)',
            r'\s(\d+)',
            r'channel\s*(\d+)',
            r'(\d+)$'
        ]

        # Define chipset fan patterns
        class ChipsetFanPattern:
            def __init__(self, patterns, rpm_keys, description):
                self.patterns = patterns
                self.rpm_keys = rpm_keys
                self.description = description

        CHIPSET_FAN_PATTERNS = {
            "nct67": ChipsetFanPattern(
                patterns=["fan", "sys_fan", "chassis_fan", "array_fan"],
                rpm_keys=["fan{}_input", "fan_input"],
                description="Nuvoton NCT67xx series"
            ),
            "it87": ChipsetFanPattern(
                patterns=["fan", "system_fan", "power_fan", "cpu_fan"],
                rpm_keys=["fan{}_input", "speed"],
                description="ITE IT87xx series"
            ),
            "w83795": ChipsetFanPattern(
                patterns=["fan", "fanin", "sys_fan"],
                rpm_keys=["fan{}_input", "speed"],
                description="Winbond W83795G/ADG"
            ),
            "f71882": ChipsetFanPattern(
                patterns=["fan", "fan_in"],
                rpm_keys=["fan{}_input"],
                description="Fintek F71882FG"
            ),
            "nzxt": ChipsetFanPattern(
                patterns=["fan", "channel"],
                rpm_keys=["fan{}_input", "speed"],
                description="NZXT Smart Device"
            ),
            "k10temp": ChipsetFanPattern(
                patterns=["fan", "cpu_fan"],
                rpm_keys=["fan{}_input"],
                description="AMD K10 temperature sensor"
            ),
            "coretemp": ChipsetFanPattern(
                patterns=["fan", "cpu_fan"],
                rpm_keys=["fan{}_input"],
                description="Intel Core temperature sensor"
            ),
            # Additional chipset patterns for better hardware support
            "asus": ChipsetFanPattern(
                patterns=["fan", "asus_fan", "cpu_fan", "chassis_fan"],
                rpm_keys=["fan{}_input", "speed", "rpm"],
                description="ASUS motherboard sensors"
            ),
            "msi": ChipsetFanPattern(
                patterns=["fan", "msi_fan", "cooling"],
                rpm_keys=["fan{}_input", "speed", "rpm"],
                description="MSI motherboard sensors"
            ),
            "gigabyte": ChipsetFanPattern(
                patterns=["fan", "sys_fan", "cpu_fan"],
                rpm_keys=["fan{}_input", "speed"],
                description="Gigabyte motherboard sensors"
            ),
            "asrock": ChipsetFanPattern(
                patterns=["fan", "system_fan", "cpu_fan"],
                rpm_keys=["fan{}_input", "speed"],
                description="ASRock motherboard sensors"
            ),
            # Server and enterprise patterns
            "ipmi": ChipsetFanPattern(
                patterns=["fan", "cooling", "tach"],
                rpm_keys=["fan{}_input", "speed", "rpm", "tach"],
                description="IPMI/BMC sensors"
            ),
            "dell": ChipsetFanPattern(
                patterns=["fan", "cooling", "system_fan"],
                rpm_keys=["fan{}_input", "speed", "rpm"],
                description="Dell server sensors"
            ),
            "hp": ChipsetFanPattern(
                patterns=["fan", "cooling", "system_fan"],
                rpm_keys=["fan{}_input", "speed", "rpm"],
                description="HP server sensors"
            )
        }

        for device, readings in sensors_data.items():
            if not isinstance(readings, dict):
                continue

            # Identify chipset with more detailed logging
            chipset = None
            chipset_pattern = None
            device_lower = device.lower()

            for chip_key in CHIPSET_FAN_PATTERNS:
                if chip_key in device_lower:
                    chipset = chip_key
                    chipset_pattern = CHIPSET_FAN_PATTERNS[chip_key]
                    _LOGGER.debug(
                        "Matched chipset %s for device %s",
                        chipset,
                        device
                    )
                    break

            # Use chipset-specific or default patterns
            patterns = (chipset_pattern.patterns if chipset_pattern
                    else DEFAULT_FAN_PATTERNS)
            rpm_keys = (chipset_pattern.rpm_keys if chipset_pattern
                    else DEFAULT_RPM_KEYS)

            # Look for fan readings with better pattern matching
            for key, value in readings.items():
                key_lower = key.lower()

                # Improve pattern matching to be more inclusive
                pattern_matched = False
                matched_pattern = None

                for pattern in patterns:
                    if pattern in key_lower:
                        pattern_matched = True
                        matched_pattern = pattern
                        break

                # Special case for system_fan which might be missed
                if not pattern_matched and ("fan" in key_lower or "cooling" in key_lower):
                    pattern_matched = True
                    matched_pattern = "fan"

                # Fallback detection for non-standard patterns
                if not pattern_matched:
                    fallback_patterns = ["tach", "pwm", "rpm", "speed"]
                    for fallback in fallback_patterns:
                        if fallback in key_lower and any(char.isdigit() for char in key_lower):
                            pattern_matched = True
                            matched_pattern = fallback
                            _LOGGER.debug("Using fallback pattern '%s' for key '%s'", fallback, key)
                            break

                if pattern_matched:
                    try:
                        # Extract fan number with more flexible matching
                        fan_num = "1"  # Default
                        for pattern in FAN_NUMBER_PATTERNS:
                            if match := re.search(pattern, key_lower):
                                fan_num = match.group(1)
                                break

                        # If no number found in key, try to extract from device name
                        if fan_num == "1" and "fan" in device_lower:
                            for pattern in FAN_NUMBER_PATTERNS:
                                if match := re.search(pattern, device_lower):
                                    fan_num = match.group(1)
                                    break

                        # Get RPM value with improved parsing
                        rpm_val = None
                        if isinstance(value, dict):
                            # Try all possible rpm keys
                            for rpm_key in rpm_keys:
                                formatted_key = rpm_key.format(fan_num)
                                if formatted_key in value:
                                    try:
                                        rpm_val = float(value[formatted_key])
                                        break
                                    except (ValueError, TypeError):
                                        continue
                                elif rpm_key in value:
                                    try:
                                        rpm_val = float(value[rpm_key])
                                        break
                                    except (ValueError, TypeError):
                                        continue
                        else:
                            # Handle string representations with better cleanup
                            rpm_str = str(value).upper()
                            rpm_str = rpm_str.replace("RPM", "").strip()
                            # Remove any non-numeric characters except decimal point
                            rpm_str = re.sub(r'[^0-9.]', '', rpm_str)
                            if rpm_str:
                                try:
                                    rpm_val = float(rpm_str)
                                except (ValueError, TypeError):
                                    rpm_val = None

                        if (rpm_val is not None and
                            MIN_VALID_RPM <= rpm_val <= MAX_VALID_RPM):

                            # Create a unique, sanitized base name
                            # Include the matched pattern for better identification
                            base_name = f"{device}_{matched_pattern}_{fan_num}".replace(" ", "_")
                            base_name = re.sub(r'[^a-z0-9_]', '_', base_name.lower())
                            base_name = re.sub(r'_+', '_', base_name).strip('_')

                            # Create a more user-friendly display name
                            if "cpu" in key_lower or "processor" in key_lower:
                                display_name = f"CPU Fan {fan_num}"
                            elif "system" in key_lower or "sys" in key_lower:
                                display_name = f"System Fan {fan_num}"
                            elif "chassis" in key_lower:
                                display_name = f"Chassis Fan {fan_num}"
                            elif "power" in key_lower or "psu" in key_lower:
                                display_name = f"Power Supply Fan {fan_num}"
                            elif chipset:
                                display_name = f"{chipset.upper()} Fan {fan_num}"
                            else:
                                display_name = f"Fan {fan_num}"

                            fan_data[base_name] = {
                                "rpm": int(rpm_val),
                                "label": display_name,
                                "device": device,
                                "chipset": chipset or "unknown",
                                "channel": int(fan_num),
                                "sensor_key": key  # Store original key for debugging
                            }

                            _LOGGER.debug(
                                "Added %s fan: %s with %d RPM (from %s.%s)",
                                chipset or "generic",
                                display_name,
                                int(rpm_val),
                                device,
                                key
                            )

                    except (ValueError, TypeError, KeyError) as err:
                        _LOGGER.debug(
                            "Error parsing fan for device %s, key %s: %s - %s",
                            device,
                            key,
                            value,
                            err
                        )
                        continue

        # Logging detailed summary
        if fan_data:
            chipsets = set(f["chipset"] for f in fan_data.values())
            _LOGGER.debug(
                "Found %d fans across %d chipsets: %s",
                len(fan_data),
                len(chipsets),
                ", ".join(sorted(chipsets))
            )

            # Log fan names for easier troubleshooting
            fan_names = sorted(f["label"] for f in fan_data.values())
            _LOGGER.debug("Detected fans: %s", ", ".join(fan_names))
        else:
            _LOGGER.warning("No fans detected in sensors data")

        return fan_data

    except Exception as err:
        _LOGGER.error("Error extracting fan data: %s", err, exc_info=True)
        return {}
