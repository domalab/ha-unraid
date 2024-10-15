"""Switch platform for Unraid."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid switch based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    if "docker_containers" not in coordinator.data or "vms" not in coordinator.data:
        return

    switches = []

    if coordinator.data["docker_containers"]:
        for container in coordinator.data["docker_containers"]:
            switches.append(UnraidDockerContainerSwitch(coordinator, container["name"]))

    if coordinator.data["vms"]:
        for vm in coordinator.data["vms"]:
            switches.append(UnraidVMSwitch(coordinator, vm["name"]))

    if switches:
        async_add_entities(switches)

class UnraidSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Unraid switches."""

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
    def entity_registry_enabled_default(self) -> bool:
        return True

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
        """Initialize the switch."""
        super().__init__(coordinator)
        self._container_name = container_name
        self._attr_name = f"Unraid Docker {container_name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_docker_{container_name}"
        self._attr_icon = "mdi:docker"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        for container in self.coordinator.data["docker_containers"]:
            if container["name"] == self._container_name:
                return container["status"].lower() == "running"
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the container on."""
        await self.coordinator.api.start_container(self._container_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the container off."""
        await self.coordinator.api.stop_container(self._container_name)
        await self.coordinator.async_request_refresh()

class UnraidVMSwitch(UnraidSwitchBase):
    """Representation of an Unraid VM switch."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator, vm_name: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._vm_name = vm_name
        self._attr_name = f"Unraid VM {vm_name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_vm_{vm_name}"
        self._attr_icon = "mdi:desktop-classic"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        for vm in self.coordinator.data["vms"]:
            if vm["name"] == self._vm_name:
                return vm["status"].lower() == "running"
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the VM on."""
        await self.coordinator.api.start_vm(self._vm_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the VM off."""
        await self.coordinator.api.stop_vm(self._vm_name)
        await self.coordinator.async_request_refresh()