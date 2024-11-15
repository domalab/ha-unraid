"""Switch platform for Unraid."""
from __future__ import annotations

from typing import Any, Dict
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid switch based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = []

    if "docker_containers" in coordinator.data:
        switches.extend([
            UnraidDockerContainerSwitch(coordinator, container["name"])
            for container in coordinator.data["docker_containers"]
        ])

    if "vms" in coordinator.data:
        switches.extend([
            UnraidVMSwitch(coordinator, vm["name"])
            for vm in coordinator.data["vms"]
        ])

    if switches:
        async_add_entities(switches)

class UnraidSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Unraid switches."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, name: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{name}"

    @property
    def device_info(self):
        """Return device information about this Unraid server."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": f"Unraid Server ({self.coordinator.config_entry.data['host']})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

class UnraidDockerContainerSwitch(UnraidSwitchBase):
    """Representation of an Unraid Docker container switch."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, container_name: str) -> None:
        """Initialize the Docker container switch."""
        super().__init__(coordinator, f"docker_{container_name}")
        self._container_name = container_name
        self._attr_name = f"Unraid Docker {container_name}"
        self._attr_icon = "mdi:docker"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        for container in self.coordinator.data["docker_containers"]:
            if container["name"] == self._container_name:
                return container["state"] == "running"
        return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        for container in self.coordinator.data["docker_containers"]:
            if container["name"] == self._container_name:
                return {
                    "container_id": container["id"],
                    "status": container["status"],
                    "image": container["image"]
                }
        return {}

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the container on."""
        await self.coordinator.api.start_container(self._container_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the container off."""
        await self.coordinator.api.stop_container(self._container_name)
        await self.coordinator.async_request_refresh()

class UnraidVMSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Unraid VM switch."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, vm_name: str) -> None:
        """Initialize the VM switch."""
        super().__init__(coordinator)
        self._vm_name = vm_name
        # Remove any leading numbers and spaces for the entity ID
        cleaned_name = ''.join(c for c in vm_name if not c.isdigit()).strip()
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_vm_{cleaned_name}"
        self._attr_name = f"Unraid VM {vm_name}"
        self._attr_entity_registry_enabled_default = True
        self._attr_has_entity_name = True
        self._last_known_state = None

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": f"Unraid Server ({self.coordinator.config_entry.data['host']})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }

    @property
    def icon(self) -> str:
        """Return the icon based on OS type."""
        for vm in self.coordinator.data.get("vms", []):
            if vm["name"] == self._vm_name:
                if vm.get("os_type") == "windows":
                    return "mdi:microsoft-windows"
                elif vm.get("os_type") == "linux":
                    return "mdi:linux"
                return "mdi:desktop-tower"
        return "mdi:desktop-tower"

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        if not self.coordinator.last_update_success:
            return False
        return any(vm["name"] == self._vm_name for vm in self.coordinator.data.get("vms", []))

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        for vm in self.coordinator.data.get("vms", []):
            if vm["name"] == self._vm_name:
                state = vm["status"].lower()
                self._last_known_state = state
                return state == "running"
        return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "status": "unknown",
            "os_type": "unknown",
        }
        
        for vm in self.coordinator.data.get("vms", []):
            if vm["name"] == self._vm_name:
                attrs.update({
                    "status": vm.get("status", "unknown"),
                    "os_type": vm.get("os_type", "unknown"),
                })
                break
                
        return attrs

    async def _safe_vm_operation(self, operation: str, func) -> None:
        """Safely execute a VM operation with proper error handling."""
        try:
            _LOGGER.debug("Attempting to %s VM '%s'", operation, self._vm_name)
            success = await func(self._vm_name)
            
            if not success:
                error_msg = f"Failed to {operation} VM '{self._vm_name}'"
                if self._last_known_state:
                    error_msg += f" (Last known state: {self._last_known_state})"
                _LOGGER.error(error_msg)
                raise HomeAssistantError(error_msg)
                
            # Force a refresh after the operation
            await self.coordinator.async_request_refresh()
            
        except Exception as err:
            error_msg = f"Error during {operation} operation for VM '{self._vm_name}': {str(err)}"
            _LOGGER.error(error_msg)
            raise HomeAssistantError(error_msg) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the VM on."""
        await self._safe_vm_operation("start", self.coordinator.api.start_vm)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the VM off."""
        await self._safe_vm_operation("stop", self.coordinator.api.stop_vm)