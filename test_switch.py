"""Tests for the Unraid switch platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.unraid.switch import (
    async_setup_entry,
    UnraidDockerContainerSwitch,
    UnraidVMSwitch,
)
from custom_components.unraid.const import DOMAIN 