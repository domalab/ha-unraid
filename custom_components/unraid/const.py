"""Constants for the Unraid integration."""
from homeassistant.const import Platform

DOMAIN = "unraid"
DEFAULT_PORT = 22
DEFAULT_CHECK_INTERVAL = 300  # seconds

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

# Configuration and options
CONF_CHECK_INTERVAL = "check_interval"

# Dispatcher signals
SIGNAL_UPDATE_UNRAID = f"{DOMAIN}_update"

# Services
SERVICE_FORCE_UPDATE = "force_update"

# Attributes
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# Units
UNIT_PERCENTAGE = "%"