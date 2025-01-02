"""Constants for the Unraid integration."""
from enum import Enum, IntEnum
from typing import Final
from homeassistant.const import ( # type: ignore
    Platform,
)

# Unraid Server
DOMAIN = "unraid"
DEFAULT_PORT = 22

# Unraid Server Hostname
CONF_HOSTNAME = "hostname"
MAX_HOSTNAME_LENGTH = 32
DEFAULT_NAME = "unraid"  # Fallback name if no hostname

# Update intervals
MIN_UPDATE_INTERVAL = 1          # minutes
MAX_GENERAL_INTERVAL = 60        # minutes
MIN_DISK_INTERVAL = 1           # hours
MAX_DISK_INTERVAL = 24          # hours
DEFAULT_GENERAL_INTERVAL = 5     # minutes
DEFAULT_DISK_INTERVAL = 1        # hours
UPDATE_FAILED_RETRY_DELAY: Final = 30  # seconds
MAX_FAILED_UPDATE_COUNT: Final = 3
MAX_UPDATE_METRICS_HISTORY: Final = 10

# Configuration and options
CONF_GENERAL_INTERVAL = "general_interval"
CONF_DISK_INTERVAL = "disk_interval"
CONF_HAS_UPS = "has_ups"


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

# UPS Configuration
UPS_METRICS = {
    "NOMPOWER": {"min": 0, "max": 10000, "unit": "W"},
    "LOADPCT": {"min": 0, "max": 100, "unit": "%"},
    "CUMONKWHOURS": {"min": 0, "max": 1000000, "unit": "kWh"},
    "LOADAPNT": {"min": 0, "max": 10000, "unit": "VA"},
    "LINEV": {"min": 0, "max": 500, "unit": "V"},
    "POWERFACTOR": {"min": 0, "max": 1, "unit": None},
    "BCHARGE": {"min": 0, "max": 100, "unit": "%"},
    "TIMELEFT": {"min": 0, "max": 1440, "unit": "min"},
    "BATTV": {"min": 0, "max": 60, "unit": "V"},
}

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
