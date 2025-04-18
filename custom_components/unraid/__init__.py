"""The Unraid integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Import only what's needed for setup
DOMAIN = "unraid"

# Define platforms to load
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Unraid integration."""
    # This function is called when the integration is loaded via configuration.yaml
    # We don't support configuration.yaml setup, so just return True
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    # Import dependencies lazily to avoid blocking the event loop
    from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
    from homeassistant.exceptions import ConfigEntryNotReady

    # Import local modules lazily
    from .coordinator import UnraidDataUpdateCoordinator
    from .unraid import UnraidAPI
    from .api.logging_helper import LogManager
    from . import services

    # Create a log manager instance here to avoid module-level instantiation
    log_manager = LogManager()
    log_manager.configure()

    # Set up data structures
    hass.data.setdefault(DOMAIN, {})

    try:
        # Extract configuration
        host = entry.data[CONF_HOST]
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        port = entry.data.get(CONF_PORT, 22)

        # Create API client
        api = UnraidAPI(host, username, password, port)

        # Create coordinator
        coordinator = UnraidDataUpdateCoordinator(hass, api, entry)

        # Get initial data
        await coordinator.async_config_entry_first_refresh()

        # Store coordinator in hass.data
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Set up services
        await services.async_setup_services(hass)

        # Register update listener for options
        entry.async_on_unload(entry.add_update_listener(update_listener))

        return True

    except Exception as err:
        _LOGGER.error("Failed to set up Unraid integration: %s", err)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up coordinator
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Reload the integration
    await hass.config_entries.async_reload(entry.entry_id)
