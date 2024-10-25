"""Services for the Unraid integration."""
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_EXECUTE_COMMAND = "execute_command"
SERVICE_EXECUTE_IN_CONTAINER = "execute_in_container"
SERVICE_EXECUTE_USER_SCRIPT = "execute_user_script"
SERVICE_STOP_USER_SCRIPT = "stop_user_script"
SERVICE_ARRAY_STOP = "array_stop"
SERVICE_SYSTEM_REBOOT = "system_reboot"
SERVICE_SYSTEM_SHUTDOWN = "system_shutdown"

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

SERVICE_ARRAY_STOP_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("ignore_lock", default=False): cv.boolean,
})

SERVICE_SYSTEM_REBOOT_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("delay", default=0): vol.All(
        cv.positive_int,
        vol.Range(min=0, max=3600)
    ),
})

SERVICE_SYSTEM_SHUTDOWN_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("delay", default=0): vol.All(
        cv.positive_int,
        vol.Range(min=0, max=3600)
    ),
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

    async def array_stop(call: ServiceCall) -> None:
        """Stop the Unraid array."""
        entry_id = call.data["entry_id"]
        ignore_lock = call.data["ignore_lock"]

        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        try:
            result = await coordinator.api.array_stop(ignore_lock=ignore_lock)
            await coordinator.async_request_refresh()
            call.return_value = {"success": result}
        except HomeAssistantError as err:
            call.return_value = {"success": False, "error": str(err)}

    async def system_reboot(call: ServiceCall) -> None:
        """Reboot the Unraid system."""
        entry_id = call.data["entry_id"]
        delay = call.data["delay"]

        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        try:
            result = await coordinator.api.system_reboot(delay=delay)
            call.return_value = {"success": result}
        except HomeAssistantError as err:
            call.return_value = {"success": False, "error": str(err)}

    async def system_shutdown(call: ServiceCall) -> None:
        """Shutdown the Unraid system."""
        entry_id = call.data["entry_id"]
        delay = call.data["delay"]

        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        try:
            result = await coordinator.api.system_shutdown(delay=delay)
            call.return_value = {"success": result}
        except HomeAssistantError as err:
            call.return_value = {"success": False, "error": str(err)}

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_ARRAY_STOP,
        array_stop,
        schema=SERVICE_ARRAY_STOP_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYSTEM_REBOOT,
        system_reboot,
        schema=SERVICE_SYSTEM_REBOOT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYSTEM_SHUTDOWN,
        system_shutdown,
        schema=SERVICE_SYSTEM_SHUTDOWN_SCHEMA
    )

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Unraid services."""
    hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_COMMAND)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_IN_CONTAINER)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_USER_SCRIPT)
    hass.services.async_remove(DOMAIN, SERVICE_STOP_USER_SCRIPT)
    hass.services.async_remove(DOMAIN, SERVICE_ARRAY_STOP)
    hass.services.async_remove(DOMAIN, SERVICE_SYSTEM_REBOOT)
    hass.services.async_remove(DOMAIN, SERVICE_SYSTEM_SHUTDOWN)