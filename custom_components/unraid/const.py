"""Constants for the Unraid integration."""
from enum import Enum, IntEnum
from typing import Final, Dict
from homeassistant.const import ( # type: ignore
    Platform,
    PERCENTAGE,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfTime,
    UnitOfEnergy,
)

# Unraid Server
DOMAIN = "unraid"
DEFAULT_PORT = 22

# Migration version
MIGRATION_VERSION = 2

# Unraid Server Hostname
CONF_HOSTNAME = "hostname"
MAX_HOSTNAME_LENGTH = 32
DEFAULT_NAME = "unraid"  # Fallback name if no hostname

# Update intervals
MIN_UPDATE_INTERVAL = 1          # minutes
MAX_GENERAL_INTERVAL = 60        # minutes

# Disk update intervals
MIN_DISK_INTERVAL_MINUTES = 5    # minutes
MAX_DISK_INTERVAL_HOURS = 24     # hours
DEFAULT_GENERAL_INTERVAL = 5     # minutes
DEFAULT_DISK_INTERVAL = 60       # minutes (1 hour)

# General update interval options in minutes
GENERAL_INTERVAL_OPTIONS = [
    1,    # 1 minute
    2,    # 2 minutes
    3,    # 3 minutes
    5,    # 5 minutes
    10,   # 10 minutes
    15,   # 15 minutes
    30,   # 30 minutes
    60    # 60 minutes (1 hour)
]

# Disk update interval options in minutes
DISK_INTERVAL_OPTIONS = [
    5,    # 5 minutes
    10,   # 10 minutes
    15,   # 15 minutes
    30,   # 30 minutes
    45,   # 45 minutes
    60,   # 1 hour
    120,  # 2 hours
    180,  # 3 hours
    240,  # 4 hours
    300,  # 5 hours
    360,  # 6 hours
    480,  # 8 hours
    720,  # 12 hours
    1440  # 24 hours
]

UPDATE_FAILED_RETRY_DELAY: Final = 30  # seconds
MAX_FAILED_UPDATE_COUNT: Final = 3
MAX_UPDATE_METRICS_HISTORY: Final = 10

# Configuration and options
CONF_GENERAL_INTERVAL = "general_interval"
CONF_DISK_INTERVAL = "disk_interval"
CONF_HAS_UPS = "has_ups"
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"


# Platforms
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Signals
SIGNAL_UPDATE_UNRAID = f"{DOMAIN}_update"

# Services
SERVICE_FORCE_UPDATE = "force_update"

# Config Entry Attributes
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# Units
UNIT_PERCENTAGE = "%"

# CPU Temperature monitoring thresholds (Celsius)
TEMP_WARN_THRESHOLD: Final = 80  # Temperature above which warning state is triggered
TEMP_CRIT_THRESHOLD: Final = 90  # Temperature above which critical state is triggered

# UPS metric validation ranges
UPS_METRICS: Final[Dict[str, dict]] = {
    "NOMPOWER": {"min": 0, "max": 10000, "unit": UnitOfPower.WATT},
    "LOADPCT": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "BCHARGE": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "LINEV": {"min": 0, "max": 500, "unit": UnitOfElectricPotential.VOLT},
    "BATTV": {"min": 0, "max": 60, "unit": UnitOfElectricPotential.VOLT},
    "TIMELEFT": {"min": 0, "max": 1440, "unit": UnitOfTime.MINUTES},
    "ITEMP": {"min": 0, "max": 60, "unit": "°C"},
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

# UPS default values and thresholds
UPS_DEFAULT_POWER_FACTOR: Final = 0.9
UPS_TEMP_WARN_THRESHOLD: Final = 45  # °C
UPS_TEMP_CRIT_THRESHOLD: Final = 60  # °C
UPS_BATTERY_LOW_THRESHOLD: Final = 50  # %
UPS_BATTERY_CRITICAL_THRESHOLD: Final = 20  # %
UPS_LOAD_HIGH_THRESHOLD: Final = 80  # %
UPS_LOAD_CRITICAL_THRESHOLD: Final = 95  # %

# SpinDownDelay class
class SpinDownDelay(IntEnum):
    """Unraid disk spin down delay settings."""
    NEVER = 0  # Default in Unraid
    MINUTES_15 = 15
    MINUTES_30 = 30
    MINUTES_45 = 45
    HOUR_1 = 1
    HOURS_2 = 2
    HOURS_3 = 3
    HOURS_4 = 4
    HOURS_5 = 5
    HOURS_6 = 6
    HOURS_7 = 7
    HOURS_8 = 8
    HOURS_9 = 9

    @classmethod
    def _missing_(cls, value: object) -> "SpinDownDelay":
        """Handle invalid values by mapping to closest valid option."""
        try:
            # Convert value to int for comparison
            val = int(str(value))
            valid_values = sorted([m.value for m in cls])
            # Find closest valid value
            closest = min(valid_values, key=lambda x: abs(x - val))
            return cls(closest)
        except (ValueError, TypeError):
            return cls.NEVER

    def to_human_readable(self) -> str:
        """Convert spin down delay to human readable format."""
        try:
            if self == self.NEVER:
                return "Never"
            if self.value < 60:
                return f"{self.value} minutes"
            return f"{self.value // 60} hours"
        except ValueError:
            return f"Unknown ({self.value})"

    def to_seconds(self) -> int:
        """Convert delay to seconds for calculations."""
        if self == self.NEVER:
            return 0
        return self.value * 60  # Convert minutes to seconds

# DiskStatus class
class DiskStatus(str, Enum):
    """Disk status enum."""
    ACTIVE = "active"
    STANDBY = "standby"
    UNKNOWN = "unknown"

# DiskHealth class
class DiskHealth(str, Enum):
    """Disk health status enum."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "Unknown"

# Device identifier patterns
DEVICE_ID_SERVER = "{}_server_{}"  # DOMAIN, entry_id
DEVICE_ID_DOCKER = "{}_docker_{}_{}"  # DOMAIN, container_name, entry_id
DEVICE_ID_VM = "{}_vm_{}_{}"  # DOMAIN, vm_name, entry_id
DEVICE_ID_DISK = "{}_disk_{}_{}"  # DOMAIN, disk_name, entry_id
DEVICE_ID_UPS = "{}_ups_{}"  # DOMAIN, entry_id

# Device info defaults
DEVICE_INFO_SERVER = {
    "manufacturer": "Lime Technology",
    "model": "Unraid Server",
}

DEVICE_INFO_DOCKER = {
    "manufacturer": "Docker",
    "model": "Container Engine",
}

DEVICE_INFO_VM = {
    "manufacturer": "Unraid",
    "model": "Virtual Machine",
}