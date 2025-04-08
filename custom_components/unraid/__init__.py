"""The Unraid integration."""
from __future__ import annotations

import asyncio
import importlib
import logging
import warnings
from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval  # type: ignore

from homeassistant.config_entries import ConfigEntry  # type: ignore
from homeassistant.const import (  # type: ignore
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant  # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady  # type: ignore
# Repairs will be imported directly where needed
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
)

# Import required modules
from .migrations import async_migrate_with_rollback, async_cleanup_orphaned_entities
from .coordinator import UnraidDataUpdateCoordinator
from .unraid import UnraidAPI
from .api.logging_helper import LogManager
from .repairs import UnraidRepairManager
from . import services
_LOGGER = logging.getLogger(__name__)

# Set up log manager at the module level so it's initialized once
_LOG_MANAGER = LogManager()

# Platform verification dictionary
_PLATFORM_VERIFIED = {platform: False for platform in PLATFORMS}

async def async_setup(hass: HomeAssistant, _: dict) -> bool:
    """Set up the Unraid component."""
    hass.data.setdefault(DOMAIN, {})

    # Configure log filtering
    _LOG_MANAGER.configure()

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    # Ensure logging is configured
    _LOG_MANAGER.configure()

    # Type annotations for better type checking
    coordinator: UnraidDataUpdateCoordinator

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

        # All entities now use the new format (unraid_hostname_component_name) by default

        # Verify all platforms can be imported (non-blocking)
        async def _verify_platform(platform):
            try:
                module_path = f"custom_components.{DOMAIN}.{platform}"
                await hass.async_add_executor_job(importlib.import_module, module_path)
                _PLATFORM_VERIFIED[platform] = True
                _LOGGER.debug("Verified platform %s", platform)
                return None
            except ImportError as err:
                _LOGGER.error("Error importing platform %s: %s", platform, err)
                return platform

        # Verify all platforms in parallel
        missing_platforms = []
        verification_tasks = [_verify_platform(platform) for platform in PLATFORMS]
        results = await asyncio.gather(*verification_tasks)
        missing_platforms = [p for p in results if p is not None]

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
        try:
            # Use a more careful approach to set up platforms
            setup_platforms = []
            for platform in PLATFORMS:
                platform_key = f"{DOMAIN}.{platform}"
                if platform_key in hass.data.get("setup_entities", {}):
                    _LOGGER.debug("Platform %s already set up, skipping", platform)
                else:
                    setup_platforms.append(platform)

            if setup_platforms:
                _LOGGER.debug("Setting up platforms: %s", setup_platforms)
                await hass.config_entries.async_forward_entry_setups(entry, setup_platforms)
            else:
                _LOGGER.debug("All platforms already set up, skipping")
        except Exception as platforms_err:
            _LOGGER.error("Error setting up platforms: %s", platforms_err)

        # Set up services
        await services.async_setup_services(hass)

        # Register additional services for optimization stats
        await services.async_setup_optimization_services(hass)

        # Register update listener for options
        entry.async_on_unload(entry.add_update_listener(update_listener))

        # We'll skip repairs registration for now as it's causing issues
        # The repair issues will still be created, but the flows won't be registered
        _LOGGER.debug("Skipping repairs registration to avoid platform registration issues")

        # Create repair manager
        repair_manager = UnraidRepairManager(hass, coordinator)

        # Schedule periodic issue checks
        async def async_check_issues(_=None):
            """Check for issues periodically."""
            await repair_manager.async_check_for_issues()

        # Initial check
        await async_check_issues()

        # Schedule regular checks
        issue_check_interval = timedelta(minutes=30)
        issue_check_remove = async_track_time_interval(
            hass, async_check_issues, issue_check_interval
        )

        # Register cleanup
        entry.async_on_unload(issue_check_remove)

        # Register cleanup callback
        async def async_unload_coordinator():
            """Unload coordinator resources."""
            _LOGGER.debug("Unloading coordinator resources")
            await coordinator.async_stop()
            # Reset log filter and restore logging levels
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
    unload_ok = True

    try:
        # Use the recommended method to unload platforms
        if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
            unload_ok = False
            _LOGGER.warning("Failed to unload platforms")
    except Exception as platforms_err:
        unload_ok = False
        _LOGGER.error("Error unloading platforms: %s", platforms_err)

    # Remove entry from data
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Ensure coordinator is properly cleaned up
        await coordinator.async_stop()
        # Reset log filter and restore logging levels
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