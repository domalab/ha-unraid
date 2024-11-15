"""Services for the Unraid integration."""
from functools import partial
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from typing import Any
import logging
import json
from datetime import datetime

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_EXECUTE_COMMAND = "execute_command"
SERVICE_EXECUTE_IN_CONTAINER = "execute_in_container"
SERVICE_EXECUTE_USER_SCRIPT = "execute_user_script"
SERVICE_STOP_USER_SCRIPT = "stop_user_script"
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

def _format_response(output: str, max_length: int = 1000) -> str:
    """Format command output with length limit and sanitization."""
    if not output:
        return ""
    # Truncate long outputs
    truncated = output[:max_length] + ("..." if len(output) > max_length else "")
    # Basic sanitization of sensitive information
    sanitized = truncated.replace("/boot/config", "REDACTED_PATH")
    return sanitized

async def handle_force_update(hass: HomeAssistant, call: ServiceCall) -> None:
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

async def execute_command(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Execute a command on Unraid."""
    entry_id = call.data["entry_id"]
    command = call.data["command"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.execute_command(command)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": result.exit_status == 0,
            "stdout": _format_response(result.stdout),
            "stderr": _format_response(result.stderr),
            "exit_code": result.exit_status,
            "execution_time": f"{execution_time:.2f}s"
        }
        
        _LOGGER.info(
            "Command executed - Status: %s, Time: %s, Exit Code: %d",
            "Success" if response["success"] else "Failed",
            response["execution_time"],
            response["exit_code"]
        )
        
        if response["stderr"]:
            _LOGGER.warning("Command stderr: %s", response["stderr"])
            
        return response
        
    except Exception as err:
        error_msg = f"Error executing command: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def execute_in_container(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Execute a command in a Docker container."""
    entry_id = call.data["entry_id"]
    container = call.data["container"]
    command = call.data["command"]
    detached = call.data["detached"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.execute_in_container(container, command, detached)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": result.exit_status == 0,
            "stdout": _format_response(result.stdout),
            "stderr": _format_response(result.stderr),
            "exit_code": result.exit_status,
            "execution_time": f"{execution_time:.2f}s",
            "container": container,
            "detached": detached
        }
        
        _LOGGER.info(
            "Container command executed - Container: %s, Status: %s, Time: %s, Exit Code: %d",
            container,
            "Success" if response["success"] else "Failed",
            response["execution_time"],
            response["exit_code"]
        )
        
        if response["stderr"]:
            _LOGGER.warning("Container command stderr: %s", response["stderr"])
            
        return response
        
    except Exception as err:
        error_msg = f"Error executing container command: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def execute_user_script(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Execute a user script."""
    entry_id = call.data["entry_id"]
    script_name = call.data["script_name"]
    background = call.data["background"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.execute_user_script(script_name, background)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": bool(result) or background,
            "output": _format_response(result) if result else "Running in background" if background else "No output",
            "script": script_name,
            "background": background,
            "execution_time": f"{execution_time:.2f}s"
        }
        
        _LOGGER.info(
            "Script executed - Name: %s, Background: %s, Status: %s, Time: %s",
            script_name,
            background,
            "Success" if response["success"] else "Failed",
            response["execution_time"]
        )
        
        return response
        
    except Exception as err:
        error_msg = f"Error executing script: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def stop_user_script(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Stop a user script."""
    entry_id = call.data["entry_id"]
    script_name = call.data["script_name"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.stop_user_script(script_name)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": True,
            "output": _format_response(result) if result else "Script stopped successfully",
            "script": script_name,
            "execution_time": f"{execution_time:.2f}s"
        }
        
        _LOGGER.info(
            "Script stopped - Name: %s, Status: Success, Time: %s",
            script_name,
            response["execution_time"]
        )
        
        return response
        
    except Exception as err:
        error_msg = f"Error stopping script: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def system_reboot(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Reboot the Unraid system."""
    entry_id = call.data["entry_id"]
    delay = call.data["delay"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.system_reboot(delay=delay)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": result,
            "delay": delay,
            "execution_time": f"{execution_time:.2f}s"
        }
        
        _LOGGER.info("System reboot command executed - Status: %s, Delay: %ds, Time: %s",
            "Success" if result else "Failed",
            delay,
            response["execution_time"]
        )
        
        return response
        
    except Exception as err:
        error_msg = f"Error executing system reboot: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def system_shutdown(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Shutdown the Unraid system."""
    entry_id = call.data["entry_id"]
    delay = call.data["delay"]
    
    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()
        
        result = await coordinator.api.system_shutdown(delay=delay)
        execution_time = (datetime.now() - start_time).total_seconds()
        
        response = {
            "success": result,
            "delay": delay,
            "execution_time": f"{execution_time:.2f}s"
        }
        
        _LOGGER.info("System shutdown command executed - Status: %s, Delay: %ds, Time: %s",
            "Success" if result else "Failed",
            delay,
            response["execution_time"]
        )
        
        return response
        
    except Exception as err:
        error_msg = f"Error executing system shutdown: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Unraid integration."""
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        partial(handle_force_update, hass),
        schema=SERVICE_FORCE_UPDATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_COMMAND,
        partial(execute_command, hass),
        schema=SERVICE_EXECUTE_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_IN_CONTAINER,
        partial(execute_in_container, hass),
        schema=SERVICE_EXECUTE_IN_CONTAINER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_USER_SCRIPT,
        partial(execute_user_script, hass),
        schema=SERVICE_EXECUTE_USER_SCRIPT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_USER_SCRIPT,
        partial(stop_user_script, hass),
        schema=SERVICE_STOP_USER_SCRIPT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYSTEM_REBOOT,
        partial(system_reboot, hass),
        schema=SERVICE_SYSTEM_REBOOT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYSTEM_SHUTDOWN,
        partial(system_shutdown, hass),
        schema=SERVICE_SYSTEM_SHUTDOWN_SCHEMA
    )

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Unraid services."""
    hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_COMMAND)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_IN_CONTAINER)
    hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_USER_SCRIPT)
    hass.services.async_remove(DOMAIN, SERVICE_STOP_USER_SCRIPT)
    hass.services.async_remove(DOMAIN, SERVICE_SYSTEM_REBOOT)
    hass.services.async_remove(DOMAIN, SERVICE_SYSTEM_SHUTDOWN)