"""Services for the Unraid integration."""
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_EXECUTE_COMMAND = "execute_command"
SERVICE_EXECUTE_IN_CONTAINER = "execute_in_container"
SERVICE_EXECUTE_USER_SCRIPT = "execute_user_script"
SERVICE_STOP_USER_SCRIPT = "stop_user_script"

SERVICE_FORCE_UPDATE_SCHEMA = vol.Schema({
    vol.Optional("config_entry"): cv.string,
})

SERVICE_EXECUTE_COMMAND_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("command"): cv.string,
})

SERVICE_EXECUTE_IN_CONTAINER_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("container"): cv.string,
    vol.Required("command"): cv.string,
    vol.Optional("detached", default=False): cv.boolean,
})

SERVICE_EXECUTE_USER_SCRIPT_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("script_name"): cv.string,
    vol.Optional("background", default=False): cv.boolean,
})

SERVICE_STOP_USER_SCRIPT_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("script_name"): cv.string,
})

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Unraid integration."""

    async def handle_force_update(call: ServiceCall) -> None:
        """Handle the force update service call."""
        config_entry_id = call.data.get("config_entry")

        if config_entry_id:
            coordinator = hass.data[DOMAIN].get(config_entry_id)
            if coordinator:
                await coordinator.async_request_refresh()
            else:
                raise ValueError(f"No Unraid instance found with config entry ID: {config_entry_id}")
        else:
            for coordinator in hass.data[DOMAIN].values():
                await coordinator.async_request_refresh()

    async def execute_command(call: ServiceCall) -> None:
        """Execute a command on Unraid."""
        entry_id = call.data["entry_id"]
        command = call.data["command"]
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_command(command)
        call.return_value = {"result": result}

    async def execute_in_container(call: ServiceCall) -> None:
        """Execute a command in a Docker container."""
        entry_id = call.data["entry_id"]
        container = call.data["container"]
        command = call.data["command"]
        detached = call.data["detached"]
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_in_container(container, command, detached)
        call.return_value = {"result": result}

    async def execute_user_script(call: ServiceCall) -> None:
        """Execute a user script."""
        entry_id = call.data["entry_id"]
        script_name = call.data["script_name"]
        background = call.data["background"]
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.execute_user_script(script_name, background)
        call.return_value = {"result": result}

    async def stop_user_script(call: ServiceCall) -> None:
        """Stop a user script."""
        entry_id = call.data["entry_id"]
        script_name = call.data["script_name"]
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        result = await coordinator.api.stop_user_script(script_name)
        call.return_value = {"result": result}

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        handle_force_update,
        schema=SERVICE_FORCE_UPDATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_COMMAND,
        execute_command,
        schema=SERVICE_EXECUTE_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_IN_CONTAINER,
        execute_in_container,
        schema=SERVICE_EXECUTE_IN_CONTAINER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_USER_SCRIPT,
        execute_user_script,
        schema=SERVICE_EXECUTE_USER_SCRIPT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_USER_SCRIPT,
        stop_user_script,
        schema=SERVICE_STOP_USER_SCRIPT_SCHEMA
    )

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Unraid services."""
    hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_COMMAND)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_IN_CONTAINER)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_USER_SCRIPT)
    hass.services.async_remove(DOMAIN, SERVICE_STOP_USER_SCRIPT)