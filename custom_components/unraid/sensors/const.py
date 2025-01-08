"""Constants for Unraid sensors and devices."""
from __future__ import annotations

import re
from typing import Final, Callable, Any, Pattern, Set, List, Dict, Tuple
from dataclasses import dataclass, field

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import ( # type: ignore
    UnitOfTemperature,
    UnitOfPower,
    UnitOfFrequency,
    UnitOfElectricPotential,
    UnitOfTime,
    UnitOfEnergy,
    PERCENTAGE,
)

# Core constants
DOMAIN: Final = "unraid"

# Unit constants for clarity and consistency
UNIT_WATTS: Final = UnitOfPower.WATT
UNIT_HERTZ: Final = UnitOfFrequency.HERTZ
UNIT_CELSIUS: Final = UnitOfTemperature.CELSIUS
UNIT_VOLTS: Final = UnitOfElectricPotential.VOLT

# Polling intervals
FAST_POLL_INTERVAL: Final = 30  # seconds
STANDARD_POLL_INTERVAL: Final = 60  # seconds
SLOW_POLL_INTERVAL: Final = 300  # seconds

# =====================
# Storage Constants
# =====================
DISK_NUMBER_PATTERN: Pattern = re.compile(r'disk(\d+)$')
MOUNT_POINT_PATTERN: Pattern = re.compile(r'/mnt/disk(\d+)$')

# =====================
# Network Constants
# =====================
VALID_INTERFACE_PATTERN: Pattern = re.compile(r'^[a-zA-Z0-9]+$')
EXCLUDED_INTERFACES: Set[str] = {'lo', 'tunl0', 'sit0'}

# =====================
# Temperature Patterns and Thresholds
# =====================

# Temperature ranges and thresholds
VALID_CPU_TEMP_RANGE: Final[Tuple[float, float]] = (-10.0, 105.0)
VALID_MB_TEMP_RANGE: Final[Tuple[float, float]] = (-10.0, 100.0)
TEMP_WARN_THRESHOLD: Final = 60  # °C
TEMP_CRIT_THRESHOLD: Final = 80  # °C

# Keyword sets for dynamic detection
CPU_KEYWORDS: Final[Set[str]] = {
    "cpu", "core", "package", "k10temp", "coretemp", 
    "ccd", "tctl", "tdie", "ryzen", "intel", "amd"
}

MB_KEYWORDS: Final[Set[str]] = {
    "mb", "board", "pch", "systin", "system", "chipset", 
    "northbridge", "southbridge", "acpi", "motherboard"
}

# Minimum difference required between readings to consider a change
TEMP_CHANGE_THRESHOLD: Final = 0.5  # °C

# CPU and Motherboard Dynamic pattern matching
CPU_CORE_PATTERN: Pattern = re.compile(r"^Core\s+(\d+)$", re.IGNORECASE)
CPU_TCCD_PATTERN: Pattern = re.compile(r"^Tccd(\d+)$", re.IGNORECASE)
CPU_PECI_PATTERN: Pattern = re.compile(r"^PECI Agent\s+(\d+)$", re.IGNORECASE)
MB_SYSTEM_PATTERN: Pattern = re.compile(r"^System\s+(\d+)$", re.IGNORECASE)
MB_EC_PATTERN: Pattern = re.compile(r"^EC_TEMP(\d+)$", re.IGNORECASE)
MB_AUXTIN_PATTERN: Pattern = re.compile(r"^AUXTIN(\d+)$", re.IGNORECASE)
MB_ACPI_PATTERN: Pattern = re.compile(r"^acpitz-acpi-(\d+)$", re.IGNORECASE)

# CPU temperature detection patterns
CPU_TEMP_PATTERNS: Final[List[Tuple[str, str]]] = [
    # Intel CPU Package and Core temperatures
    ("Package id 0", "temp1_input"),      # Intel CPU Package - Primary
    ("CPU Package", "temp1_input"),       # Intel Package - Alternative
    ("CPU DTS", "temp1_input"),           # Intel Digital Temperature Sensor
    
    # AMD-specific temperatures
    ("Tctl", "temp1_input"),              # AMD Ryzen CPU - Primary
    ("Tdie", "temp2_input"),              # AMD Ryzen CPU die
    ("k10temp", "temp1_input"),           # AMD K10 CPU
    ("Core Complex Die", "temp1_input"),  # AMD complex die
    
    # Motherboard vendor-specific CPU temperatures
    ("CPU Temperature", "temp1_input"),    # ASUS boards
    ("CPU Socket", "temp2_input"),         # MSI boards
    ("CPU Core", "temp3_input"),           # Gigabyte boards
    
    # Generic CPU temperature sensors
    ("CPU Temp", "temp1_input"),          # pch_cannonlake
    ("CPUTIN", "temp2_input"),            # nct6793
    ("CPU", "temp1_input"),               # Generic CPU temp
    ("CPU Die", "temp1_input"),           # Generic CPU die temp
    ("CPU Die Average", "temp2_input"),   # Average of multiple dies
]

# Motherboard temperature patterns
MOTHERBOARD_TEMP_PATTERNS: Final[List[Tuple[str, str]]] = [
    # ACPI and main board temperatures
    ("acpitz-acpi-0", "temp1_input"),     # ACPI interface temperature
    ("MB Temp", "temp1_input"),           # Direct MB temp
    ("Board Temp", "temp1_input"),        # Generic board temp
    ("Motherboard", "temp1_input"),       # Generic MB temp
    ("SYSTIN", "temp1_input"),            # System board temp input
    
    # Chipset temperatures
    ("PCH Temp", "temp3_input"),          # Intel PCH temperature
    ("PCH_CHIP_CPU_MAX_TEMP", "temp1_input"), # Intel PCH max temp
    ("PCH_CHIP_TEMP", "temp2_input"),     # Intel PCH current temp
    ("SB Temperature", "temp3_input"),    # Southbridge temperature
    ("NB Temperature", "temp4_input"),    # Northbridge temperature
    ("X570 Chipset", "temp1_input"),      # AMD X570 chipset
    ("B550 Chipset", "temp1_input"),      # AMD B550 chipset
    
    # Sensor chip specific temperatures
    ("ITE8686", "temp2_input"),           # ITE sensor common temp
    ("Nuvoton NCT6798D", "temp3_input"),  # Nuvoton sensor board temp
]

# Define known good sensor chips and their temperature input keys
KNOWN_SENSOR_CHIPS: Final[Dict[str, List[str]]] = {
    "coretemp-isa": ["Package id 0", "Core 0"],
    "k10temp-pci": ["Tctl", "Tdie"],
    "nct6791-isa": ["SYSTIN", "CPUTIN"],
    "it8688-isa": ["CPU Temperature", "System 1"],
}

# =====================
# Fan Control Constants
# =====================

@dataclass
class ChipsetFanPattern:
    """Pattern definition for chipset fan detection."""
    patterns: List[str]
    rpm_keys: List[str]
    description: str

# Chipset-specific fan patterns
CHIPSET_FAN_PATTERNS: Dict[str, ChipsetFanPattern] = {
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
    )
}

FAN_NUMBER_PATTERNS: List[str] = [
    r'fan(\d+)',
    r'#(\d+)',
    r'\s(\d+)',
    r'channel\s*(\d+)',
    r'(\d+)$'
]

DEFAULT_FAN_PATTERNS: List[str] = ["fan", "sys_fan", "chassis_fan"]
DEFAULT_RPM_KEYS: List[str] = ["fan{}_input", "fan_input", "speed"]

MIN_VALID_RPM: int = 0
MAX_VALID_RPM: int = 10000

# =====================
# UPS Constants
# =====================

# UPS metric validation ranges
UPS_METRICS: Final[Dict[str, dict]] = {
    "NOMPOWER": {"min": 0, "max": 10000, "unit": UNIT_WATTS},
    "LOADPCT": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "BCHARGE": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "LINEV": {"min": 0, "max": 500, "unit": UNIT_VOLTS},
    "BATTV": {"min": 0, "max": 60, "unit": UNIT_VOLTS},
    "TIMELEFT": {"min": 0, "max": 1440, "unit": UnitOfTime.MINUTES},
    "ITEMP": {"min": 0, "max": 60, "unit": UNIT_CELSIUS},
    "CUMONKWHOURS": {"min": 0, "max": 1000000, "unit": UnitOfEnergy.KILO_WATT_HOUR},
}

# UPS model patterns for power calculation
UPS_MODEL_PATTERNS: Final[Dict[str, float]] = {
    r'smart-ups.*?(\d{3,4})': 1.0,       # Smart-UPS models use direct VA rating
    r'back-ups.*?(\d{3,4})': 0.9,        # Back-UPS models typically 90% of VA
    r'back-ups pro.*?(\d{3,4})': 0.95,   # Back-UPS Pro models ~95% of VA
    r'smart-ups\s*x.*?(\d{3,4})': 1.0,   # Smart-UPS X series
    r'smart-ups\s*xl.*?(\d{3,4})': 1.0,  # Smart-UPS XL series
    r'smart-ups\s*rt.*?(\d{3,4})': 1.0,  # Smart-UPS RT series
    r'symmetra.*?(\d{3,4})': 1.0,        # Symmetra models
    r'sua\d{3,4}': 1.0,                  # Smart-UPS alternative model format
    r'smx\d{3,4}': 1.0,                  # Smart-UPS SMX model format
    r'smt\d{3,4}': 1.0,                  # Smart-UPS SMT model format
}

# UPS thresholds and defaults
UPS_DEFAULT_POWER_FACTOR: Final = 0.9
UPS_TEMP_WARN_THRESHOLD: Final = 45  # °C
UPS_TEMP_CRIT_THRESHOLD: Final = 60  # °C
UPS_BATTERY_LOW_THRESHOLD: Final = 50  # %
UPS_BATTERY_CRITICAL_THRESHOLD: Final = 20  # %
UPS_LOAD_HIGH_THRESHOLD: Final = 80  # %
UPS_LOAD_CRITICAL_THRESHOLD: Final = 95  # %

# =====================
# Entity Description
# =====================

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""

    key: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    name: str | None = None
    native_unit_of_measurement: str | None = None
    icon: str | None = None
    entity_category: str | None = None
    value_fn: Callable[[dict[str, Any]], Any] = field(default=lambda _: None)
    should_poll: bool = field(default=False)
    available_fn: Callable[[dict[str, Any]], bool] = field(default=lambda _: True)
    suggested_unit_of_measurement: str | None = field(default=None)
    suggested_display_precision: int | None = field(default=None)
    translation_key: str | None = field(default=None)

    def __post_init__(self) -> None:
        """Post initialization hook."""
        super().__init__(
            key=self.key,
            device_class=self.device_class,
            state_class=self.state_class,
            name=self.name,
            native_unit_of_measurement=self.native_unit_of_measurement,
            icon=self.icon,
            entity_category=self.entity_category,
        )