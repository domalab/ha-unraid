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
from cryptography.utils import CryptographyDeprecationWarning  # type: ignore
from homeassistant.helpers.importlib import async_import_module  # type: ignore

from .const import (
    CONF_HOSTNAME,
    DOMAIN,
    PLATFORMS,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    DEFAULT_PORT,
    CONF_HAS_UPS,
)

# Suppress deprecation warnings for paramiko
warnings.filterwarnings(
    "ignore",
    category=CryptographyDeprecationWarning,
    message="TripleDES has been moved"
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Unraid component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    _LOGGER.debug("Setting up Unraid integration")

    try:
        # Import required modules asynchronously
        modules = {}
        for module_name in ["unraid", "coordinator", "services", "migrations"]:
            try:
                modules[module_name] = await async_import_module(
                    hass, f"custom_components.{DOMAIN}.{module_name}"
                )
            except ImportError as err:
                _LOGGER.error("Error importing module %s: %s", module_name, err)
                raise ConfigEntryNotReady from err

        # Import platform modules
        for platform in PLATFORMS:
            try:
                await async_import_module(
                    hass, f"custom_components.{DOMAIN}.{platform}"
                )
            except ImportError as err:
                _LOGGER.error("Error importing platform %s: %s", platform, err)
                raise ConfigEntryNotReady from err

        # Migrate data from data to options if necessary
        if CONF_GENERAL_INTERVAL not in entry.options:
            options = dict(entry.options)
            old_interval = entry.data.get("check_interval", 300)
            minutes = max(1, old_interval // 60)
            
            options.update({
                CONF_GENERAL_INTERVAL: minutes,
                CONF_DISK_INTERVAL: DEFAULT_DISK_INTERVAL,
                CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                CONF_HAS_UPS: entry.data.get(CONF_HAS_UPS, False),
            })
            
            hass.config_entries.async_update_entry(entry, options=options)

        # Create API instance using imported module
        api = modules["unraid"].UnraidAPI(
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
        await modules["migrations"].async_migrate_entities(hass, entry)

        # Create coordinator using imported module
        coordinator = modules["coordinator"].UnraidDataUpdateCoordinator(hass, api, entry)
        
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
        
        # Set up services using imported module
        await modules["services"].async_setup_services(hass)

        # Add update listener
        entry.async_on_unload(entry.add_update_listener(async_update_listener))
        
        return True

    except Exception as err:
        _LOGGER.error("Failed to set up Unraid integration: %s", err)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Stop coordinator and cleanup connections
    await coordinator.async_unload()
    
    # Import services module for unloading
    try:
        services_module = await async_import_module(
            hass, f"custom_components.{DOMAIN}.services"
        )
        
        # Unload platforms
        if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
            hass.data[DOMAIN].pop(entry.entry_id)
            await services_module.async_unload_services(hass)
            return unload_ok
        
        return False
        
    except ImportError as err:
        _LOGGER.error("Error importing services module for unload: %s", err)
        return False

async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
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
        
        # Reload the config entry
        await hass.config_entries.async_reload(entry.entry_id)
        
    except Exception as err:
        _LOGGER.error("Error handling options update: %s", err)

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Update UPS status
    await coordinator.async_update_ups_status(entry.options.get(CONF_HAS_UPS, False))