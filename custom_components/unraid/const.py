"""Constants for the Unraid integration."""
from homeassistant.const import Platform

DOMAIN = "unraid"
DEFAULT_PORT = 22
DEFAULT_PING_INTERVAL = 60
DEFAULT_CHECK_INTERVAL = 300
UPDATE_CHECK_INTERVAL = "Container Update Check Interval"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]