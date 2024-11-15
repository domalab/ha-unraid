"""Constants for the Unraid integration."""
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Final
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)

DOMAIN = "unraid"
DEFAULT_PORT = 22

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
]

# Dispatcher signals
SIGNAL_UPDATE_UNRAID = f"{DOMAIN}_update"

# Services
SERVICE_FORCE_UPDATE = "force_update"

# Attributes
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# Units
UNIT_PERCENTAGE = "%"

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

class SpinDownDelay(IntEnum):
    """Unraid disk spin down delay settings."""
    NEVER = 0
    MINUTES_15 = 15
    MINUTES_30 = 30 
    MINUTES_45 = 45
    HOUR_1 = 60
    HOURS_2 = 120
    HOURS_3 = 180
    HOURS_4 = 240
    HOURS_5 = 300
    HOURS_6 = 360
    HOURS_7 = 420
    HOURS_8 = 480
    HOURS_9 = 540

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

# Disk Status Constants
class DiskStatus(str, Enum):
    """Disk status enum."""
    ACTIVE = "active"
    STANDBY = "standby"
    UNKNOWN = "unknown"

class DiskHealth(str, Enum):
    """Disk health status enum."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "Unknown"