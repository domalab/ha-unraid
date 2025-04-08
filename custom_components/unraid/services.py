"""Services for the Unraid integration.

This module handles the registration and unregistration of all Unraid integration services.
It includes comprehensive error handling, service state tracking, and proper cleanup routines.
All services are typed and documented according to Home Assistant best practices.
"""

from functools import partial
from homeassistant.core import HomeAssistant, ServiceCall # type: ignore
from homeassistant.helpers import config_validation as cv # type: ignore
from homeassistant.exceptions import HomeAssistantError # type: ignore
import voluptuous as vol # type: ignore
from typing import Any, Set
import logging
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

# Docker container services
SERVICE_DOCKER_PAUSE = "docker_pause"
SERVICE_DOCKER_RESUME = "docker_resume"
SERVICE_DOCKER_RESTART = "docker_restart"

# VM services
SERVICE_VM_PAUSE = "vm_pause"
SERVICE_VM_RESUME = "vm_resume"
SERVICE_VM_RESTART = "vm_restart"
SERVICE_VM_HIBERNATE = "vm_hibernate"
SERVICE_VM_FORCE_STOP = "vm_force_stop"

# New optimization services
SERVICE_GET_OPTIMIZATION_STATS = "get_optimization_stats"
SERVICE_CLEAR_CACHE = "clear_cache"
SERVICE_FORCE_SENSOR_UPDATE = "force_sensor_update"

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

# Schemas for optimization services
SERVICE_GET_OPTIMIZATION_STATS_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
})

SERVICE_CLEAR_CACHE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("prefix", default=""): cv.string,
})

SERVICE_FORCE_SENSOR_UPDATE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("sensor_id"): cv.string,
})

# Docker container service schemas
SERVICE_DOCKER_PAUSE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("container"): cv.string,
})

SERVICE_DOCKER_RESUME_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("container"): cv.string,
})

SERVICE_DOCKER_RESTART_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("container"): cv.string,
})

# VM service schemas
SERVICE_VM_PAUSE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("vm"): cv.string,
})

SERVICE_VM_RESUME_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("vm"): cv.string,
})

SERVICE_VM_RESTART_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("vm"): cv.string,
})

SERVICE_VM_HIBERNATE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("vm"): cv.string,
})

SERVICE_VM_FORCE_STOP_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("vm"): cv.string,
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

# New optimization service handlers

async def get_optimization_stats(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Get optimization statistics."""
    entry_id = call.data["entry_id"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]

        # Get cache and sensor stats
        cache_stats = coordinator.get_cache_stats()
        sensor_stats = coordinator.get_sensor_stats()

        response = {
            "cache": cache_stats,
            "sensors": sensor_stats,
            "timestamp": datetime.now().isoformat()
        }

        return response

    except Exception as err:
        error_msg = f"Error getting optimization stats: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def clear_cache(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Clear the cache, optionally with a specific prefix."""
    entry_id = call.data["entry_id"]
    prefix = call.data.get("prefix", "")

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]

        if prefix:
            # Clear cache items with the given prefix
            count = coordinator._cache_manager.invalidate_by_prefix(prefix)
            response = {
                "success": True,
                "items_cleared": count,
                "prefix": prefix
            }
            _LOGGER.info("Cache cleared for prefix '%s': %d items removed", prefix, count)
        else:
            # Clear entire cache
            coordinator._cache_manager.clear()
            response = {
                "success": True,
                "message": "Entire cache cleared"
            }
            _LOGGER.info("Entire cache cleared")

        return response

    except Exception as err:
        error_msg = f"Error clearing cache: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def force_sensor_update(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Force update of a specific sensor."""
    entry_id = call.data["entry_id"]
    sensor_id = call.data["sensor_id"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]

        # Request update for the specific sensor
        coordinator.request_sensor_update(sensor_id)

        # Trigger an update
        await coordinator.async_request_refresh()

        response = {
            "success": True,
            "sensor_id": sensor_id,
            "message": f"Update requested for sensor {sensor_id}"
        }

        _LOGGER.info("Force update requested for sensor: %s", sensor_id)
        return response

    except Exception as err:
        error_msg = f"Error forcing sensor update: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

# Docker container service handlers
async def docker_pause(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Pause a Docker container."""
    entry_id = call.data["entry_id"]
    container = call.data["container"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.pause_container(container)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "container": container,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "Container pause command executed - Container: %s, Status: %s, Time: %s",
            container,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error pausing container {container}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def docker_resume(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Resume a paused Docker container."""
    entry_id = call.data["entry_id"]
    container = call.data["container"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.resume_container(container)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "container": container,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "Container resume command executed - Container: %s, Status: %s, Time: %s",
            container,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error resuming container {container}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def docker_restart(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Restart a Docker container."""
    entry_id = call.data["entry_id"]
    container = call.data["container"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.restart_container(container)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "container": container,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "Container restart command executed - Container: %s, Status: %s, Time: %s",
            container,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error restarting container {container}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

# VM service handlers
async def vm_pause(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Pause a virtual machine."""
    entry_id = call.data["entry_id"]
    vm = call.data["vm"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.pause_vm(vm)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "vm": vm,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "VM pause command executed - VM: %s, Status: %s, Time: %s",
            vm,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error pausing VM {vm}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def vm_resume(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Resume a paused virtual machine."""
    entry_id = call.data["entry_id"]
    vm = call.data["vm"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.resume_vm(vm)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "vm": vm,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "VM resume command executed - VM: %s, Status: %s, Time: %s",
            vm,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error resuming VM {vm}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def vm_restart(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Restart a virtual machine."""
    entry_id = call.data["entry_id"]
    vm = call.data["vm"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.restart_vm(vm)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "vm": vm,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "VM restart command executed - VM: %s, Status: %s, Time: %s",
            vm,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error restarting VM {vm}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def vm_hibernate(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Hibernate a virtual machine."""
    entry_id = call.data["entry_id"]
    vm = call.data["vm"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.hibernate_vm(vm)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "vm": vm,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "VM hibernate command executed - VM: %s, Status: %s, Time: %s",
            vm,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error hibernating VM {vm}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

async def vm_force_stop(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Force stop a virtual machine."""
    entry_id = call.data["entry_id"]
    vm = call.data["vm"]

    try:
        coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        start_time = datetime.now()

        result = await coordinator.api.force_stop_vm(vm)
        execution_time = (datetime.now() - start_time).total_seconds()

        response = {
            "success": result,
            "vm": vm,
            "execution_time": f"{execution_time:.2f}s"
        }

        _LOGGER.info(
            "VM force stop command executed - VM: %s, Status: %s, Time: %s",
            vm,
            "Success" if result else "Failed",
            response["execution_time"]
        )

        return response

    except Exception as err:
        error_msg = f"Error force stopping VM {vm}: {str(err)}"
        _LOGGER.error(error_msg)
        raise HomeAssistantError(error_msg) from err

_REGISTERED_SERVICES: Set[str] = set()

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Unraid integration."""

    # Define service mappings
    services = {
        SERVICE_FORCE_UPDATE: (handle_force_update, SERVICE_FORCE_UPDATE_SCHEMA),
        SERVICE_EXECUTE_COMMAND: (execute_command, SERVICE_EXECUTE_COMMAND_SCHEMA),
        SERVICE_EXECUTE_IN_CONTAINER: (execute_in_container, SERVICE_EXECUTE_IN_CONTAINER_SCHEMA),
        SERVICE_EXECUTE_USER_SCRIPT: (execute_user_script, SERVICE_EXECUTE_USER_SCRIPT_SCHEMA),
        SERVICE_STOP_USER_SCRIPT: (stop_user_script, SERVICE_STOP_USER_SCRIPT_SCHEMA),
        SERVICE_SYSTEM_REBOOT: (system_reboot, SERVICE_SYSTEM_REBOOT_SCHEMA),
        SERVICE_SYSTEM_SHUTDOWN: (system_shutdown, SERVICE_SYSTEM_SHUTDOWN_SCHEMA),

        # Docker container services
        SERVICE_DOCKER_PAUSE: (docker_pause, SERVICE_DOCKER_PAUSE_SCHEMA),
        SERVICE_DOCKER_RESUME: (docker_resume, SERVICE_DOCKER_RESUME_SCHEMA),
        SERVICE_DOCKER_RESTART: (docker_restart, SERVICE_DOCKER_RESTART_SCHEMA),

        # VM services
        SERVICE_VM_PAUSE: (vm_pause, SERVICE_VM_PAUSE_SCHEMA),
        SERVICE_VM_RESUME: (vm_resume, SERVICE_VM_RESUME_SCHEMA),
        SERVICE_VM_RESTART: (vm_restart, SERVICE_VM_RESTART_SCHEMA),
        SERVICE_VM_HIBERNATE: (vm_hibernate, SERVICE_VM_HIBERNATE_SCHEMA),
        SERVICE_VM_FORCE_STOP: (vm_force_stop, SERVICE_VM_FORCE_STOP_SCHEMA),
    }

    # Register each service
    for service_name, (handler, schema) in services.items():
        if service_name not in _REGISTERED_SERVICES:
            hass.services.async_register(
                DOMAIN,
                service_name,
                partial(handler, hass),
                schema=schema
            )
            _REGISTERED_SERVICES.add(service_name)
            _LOGGER.debug("Registered service: %s", service_name)

async def async_setup_optimization_services(hass: HomeAssistant) -> None:
    """Set up optimization services for Unraid integration."""

    # Define optimization service mappings
    services = {
        SERVICE_GET_OPTIMIZATION_STATS: (get_optimization_stats, SERVICE_GET_OPTIMIZATION_STATS_SCHEMA),
        SERVICE_CLEAR_CACHE: (clear_cache, SERVICE_CLEAR_CACHE_SCHEMA),
        SERVICE_FORCE_SENSOR_UPDATE: (force_sensor_update, SERVICE_FORCE_SENSOR_UPDATE_SCHEMA),
    }

    # Register each service
    for service_name, (handler, schema) in services.items():
        if service_name not in _REGISTERED_SERVICES:
            hass.services.async_register(
                DOMAIN,
                service_name,
                partial(handler, hass),
                schema=schema
            )
            _REGISTERED_SERVICES.add(service_name)
            _LOGGER.debug("Registered optimization service: %s", service_name)

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Unraid services."""
    # Only attempt to remove services we know we registered
    for service in _REGISTERED_SERVICES.copy():
        try:
            hass.services.async_remove(DOMAIN, service)
            _REGISTERED_SERVICES.remove(service)
            _LOGGER.debug("Unregistered service: %s", service)
        except Exception as err:
            _LOGGER.debug("Error removing service %s: %s", service, err)