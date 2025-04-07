"""The Unraid integration."""
from __future__ import annotations

import logging
import warnings
import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry  # type: ignore
from homeassistant.const import (  # type: ignore
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant  # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady  # type: ignore
from cryptography.utils import CryptographyDeprecationWarning  # type: ignore

# Suppress deprecation warnings for paramiko
warnings.filterwarnings(
    "ignore",
    category=CryptographyDeprecationWarning,
    message="TripleDES has been moved"
)

from .const import (
    CONF_HOSTNAME,
    DOMAIN,
    PLATFORMS,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    DEFAULT_PORT,
    CONF_HAS_UPS,
    MIGRATION_VERSION,
    ENTITY_NAMING_VERSION,
    CONF_ENTITY_FORMAT,
    DEFAULT_ENTITY_FORMAT
)

# Pre-import all modules at the module level to avoid blocking calls
from .migrations import async_migrate_with_rollback, async_cleanup_orphaned_entities, migrate_entity_id_format
from .coordinator import UnraidDataUpdateCoordinator
from .unraid import UnraidAPI
from .api.logging_helper import setup_logging_filters, restore_logging_levels
from .api.log_filter import LogManager
from . import services

# Pre-import all platform modules
_LOGGER = logging.getLogger(__name__)

# Set up log manager at the module level so it's initialized once
_LOG_MANAGER = LogManager()

# Pre-import all platform modules
_PLATFORM_IMPORTS = {}

# Import all platform modules at module load time
for platform in PLATFORMS:
    try:
        module_path = f"custom_components.{DOMAIN}.{platform}"
        _PLATFORM_IMPORTS[platform] = __import__(module_path, fromlist=["_"])
        _LOGGER.debug("Pre-imported platform %s", platform)
    except ImportError as err:
        _LOGGER.warning("Error pre-importing platform %s: %s", platform, err)
        # Don't raise error here, we'll check if imports succeeded during setup

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Unraid component."""
    hass.data.setdefault(DOMAIN, {})

    # Configure log filtering
    _LOG_MANAGER.configure()

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    # Set up logging filters to reduce verbosity
    setup_logging_filters()

    _LOGGER.info("Setting up Unraid integration, cleaning up any previous entities")

    try:
        # First step: Force cleanup of any existing entities
        # This is critical to prevent duplicates
        try:
            # Run the cleanup before doing anything else
            removed_count = await async_cleanup_orphaned_entities(hass, entry)
            _LOGGER.info("Entity cleanup completed, removed %s entities", removed_count)
        except Exception as cleanup_err:
            _LOGGER.error("Error during entity cleanup: %s", cleanup_err)
            # Continue despite cleanup errors

        # Now perform any necessary migrations
        if entry.version < MIGRATION_VERSION:
            if not await async_migrate_with_rollback(hass, entry):
                _LOGGER.warning("Migration process failed, but continuing with setup")

        # Always use entity format version 2
        try:
            _LOGGER.warning("Starting entity ID migration process")
            # Always use entity format version 2
            entity_format = 2
            _LOGGER.warning("Using entity format: %s", entity_format)

            if await migrate_entity_id_format(hass, entry, entity_format):
                _LOGGER.warning("Entity ID migration completed successfully")
            else:
                _LOGGER.warning("Entity ID migration failed, but continuing with setup")
        except Exception as migration_err:
            _LOGGER.error("Error during entity ID migration: %s", migration_err)

        # Verify all platforms were imported successfully
        missing_platforms = [p for p in PLATFORMS if p not in _PLATFORM_IMPORTS]
        if missing_platforms:
            _LOGGER.error("Missing required platform modules: %s", missing_platforms)
            raise ConfigEntryNotReady(f"Missing platform modules: {missing_platforms}")

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

        # Store the coordinator
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        # Set up all platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Set up services
        await services.async_setup_services(hass)

        # Register additional services for optimization stats
        await services.async_setup_optimization_services(hass)

        # Register update listener for options
        entry.async_on_unload(entry.add_update_listener(update_listener))

        # Register cleanup callback
        async def async_unload_coordinator():
            """Unload coordinator resources."""
            _LOGGER.debug("Unloading coordinator resources")
            await coordinator.async_stop()
            # Restore logging levels on unload
            restore_logging_levels()
            # Reset log filter
            _LOG_MANAGER.reset()

        entry.async_on_unload(async_unload_coordinator)

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

        _LOGGER.info("Unraid integration setup completed successfully")
        return True

    except Exception as err:
        _LOGGER.error("Failed to set up Unraid integration: %s", err)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove entry from data
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Ensure coordinator is properly cleaned up
        await coordinator.async_stop()
        # Restore logging levels
        restore_logging_levels()
        # Reset log filter
        _LOG_MANAGER.reset()

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Reload the integration
    await hass.config_entries.async_reload(entry.entry_id)

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Update UPS status
    await coordinator.async_update_ups_status(entry.options.get(CONF_HAS_UPS, False))