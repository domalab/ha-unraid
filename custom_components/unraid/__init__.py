"""The Unraid integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import UnraidDataUpdateCoordinator
from .unraid import UnraidAPI

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    api = UnraidAPI(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=entry.data[CONF_PORT],
    )

    try:
        await api.connect()
    except Exception as err:
        await api.disconnect()
        raise ConfigEntryNotReady from err

    coordinator = UnraidDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.start_ping_task()  # Start the ping task

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.stop_ping_task()  # Stop the ping task

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.disconnect()

    return unload_ok

def register_services(hass: HomeAssistant):
    """Register services for Unraid."""

    async def execute_command(call: ServiceCall):
        """Execute a command on Unraid."""
        entry_id = call.data.get("entry_id")
        command = call.data.get("command")
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_command(command)
        return {"result": result}

    async def execute_in_container(call: ServiceCall):
        """Execute a command in a Docker container."""
        entry_id = call.data.get("entry_id")
        container = call.data.get("container")
        command = call.data.get("command")
        detached = call.data.get("detached", False)
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_in_container(container, command, detached)
        return {"result": result}

    async def execute_user_script(call: ServiceCall):
        """Execute a user script."""
        entry_id = call.data.get("entry_id")
        script_name = call.data.get("script_name")
        background = call.data.get("background", False)
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_user_script(script_name, background)
        return {"result": result}

    async def stop_user_script(call: ServiceCall):
        """Stop a user script."""
        entry_id = call.data.get("entry_id")
        script_name = call.data.get("script_name")
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.stop_user_script(script_name)
        return {"result": result}

    hass.services.async_register(DOMAIN, "execute_command", execute_command)
    hass.services.async_register(DOMAIN, "execute_in_container", execute_in_container)
    hass.services.async_register(DOMAIN, "execute_user_script", execute_user_script)
    hass.services.async_register(DOMAIN, "stop_user_script", stop_user_script)