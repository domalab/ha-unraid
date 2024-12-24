"""The Unraid integration."""
from __future__ import annotations

import logging
import warnings

from homeassistant.config_entries import ConfigEntry  # type: ignore
from homeassistant.const import (  # type: ignore
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant  # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady  # type: ignore
from cryptography.utils import CryptographyDeprecationWarning # type: ignore

from .const import (
    CONF_DOCKER_INSIGHTS,
    CONF_HOSTNAME,
    DOMAIN,
    PLATFORMS,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    DEFAULT_PORT,
    CONF_HAS_UPS,
)
from .coordinator import UnraidDataUpdateCoordinator
from .unraid import UnraidAPI
from .services import async_setup_services, async_unload_services
from .migrations import async_migrate_entities

# Suppress deprecation warnings for paramiko
warnings.filterwarnings(
    "ignore",
    category=CryptographyDeprecationWarning,
    message="TripleDES has been moved"
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    _LOGGER.debug("Setting up Unraid integration")

    # Migrate data from data to options if necessary
    if CONF_GENERAL_INTERVAL not in entry.options:
        options = dict(entry.options)
        # Convert old check interval (seconds) to new format (minutes)
        old_interval = entry.data.get("check_interval", 300)  # 300 seconds default
        minutes = max(1, old_interval // 60)  # Convert to minutes, minimum 1
        
        options.update({
            CONF_GENERAL_INTERVAL: minutes,
            CONF_DISK_INTERVAL: DEFAULT_DISK_INTERVAL,
            CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
            CONF_HAS_UPS: entry.data.get(CONF_HAS_UPS, False),
        })
        
        hass.config_entries.async_update_entry(entry, options=options)

    try:
        # Create the API instance
        api = UnraidAPI(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            port=entry.options.get(CONF_PORT, DEFAULT_PORT),
        )

        # Initialize disk operations
        await api.disk_operations.initialize()

        # Get hostname during setup if not already stored
        if CONF_HOSTNAME not in entry.data:
            try:
                hostname = await api.get_hostname()
                if hostname:
                    data = dict(entry.data)
                    data[CONF_HOSTNAME] = hostname
                    hass.config_entries.async_update_entry(entry, data=data)
                    _LOGGER.info("Updated configuration with hostname: %s", hostname)
            except Exception as hostname_err:
                _LOGGER.warning("Could not get hostname: %s", hostname_err)

        # Run entity migrations before setting up new entities
        await async_migrate_entities(hass, entry)

        coordinator = UnraidDataUpdateCoordinator(hass, api, entry)
        
        # Initialize coordinator
        await coordinator.async_setup()
        
        # Perform first refresh
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as refresh_err:
            _LOGGER.warning(
                "Initial refresh failed, continuing setup: %s", 
                refresh_err
            )

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Set up services
        await async_setup_services(hass)

        # Add update listener
        entry.async_on_unload(entry.add_update_listener(async_update_listener))
        
        return True

    except Exception as err:
        _LOGGER.error("Failed to set up Unraid integration: %s", err)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Stop coordinator and cleanup connections
    await coordinator.async_unload()
    
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        await async_unload_services(hass)

    return unload_ok

async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    except KeyError:
        _LOGGER.error("Could not find coordinator for config entry %s", entry.entry_id)
        return

    try:
        # Handle UPS status updates
        if CONF_HAS_UPS in entry.options:
            try:
                await coordinator.async_update_ups_status(entry.options[CONF_HAS_UPS])
            except Exception as err:
                _LOGGER.error("Error updating UPS status: %s", err)
        
        # Handle Docker Insights updates
        if CONF_DOCKER_INSIGHTS in entry.options:
            try:
                await coordinator.async_update_docker_insights(entry.options[CONF_DOCKER_INSIGHTS])
            except Exception as err:
                _LOGGER.error("Error updating Docker Insights: %s", err)
        
        # Reload the config entry
        await hass.config_entries.async_reload(entry.entry_id)
        
    except Exception as err:
        _LOGGER.error("Error handling options update: %s", err)

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Update UPS status
    await coordinator.async_update_ups_status(entry.options.get(CONF_HAS_UPS, False))