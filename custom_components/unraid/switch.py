"""Switch platform for Unraid."""
from __future__ import annotations

from typing import Any, Dict, Callable
import logging
from dataclasses import dataclass, field

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant, callback # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore

from .const import (
    DOMAIN,
)

from .entity_naming import EntityNaming
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidSwitchEntityDescription(SwitchEntityDescription):
    """Describes Unraid switch entity."""
    value_fn: Callable[[dict[str, Any]], bool | None] = field(default=lambda x: None)
    turn_on_fn: Callable[[Any], None] = field(default=lambda x: None)
    turn_off_fn: Callable[[Any], None] = field(default=lambda x: None)

class UnraidSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Base entity for Unraid switches."""

    entity_description: UnraidSwitchEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description

        # Initialize entity naming helper
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component=description.key.split('_')[0]  # Get first part of key as component
        )

        # Set consistent entity ID
        self._attr_unique_id = naming.get_entity_id(description.key)

        # Keep the name simple and human-readable
        self._attr_name = f"{description.name}"

        _LOGGER.debug("Entity initialized | unique_id: %s | name: %s",
            self._attr_unique_id, self._attr_name)

        # All switches belong to main server device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"{coordinator.hostname.title()}",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except Exception as err:
            _LOGGER.debug(
                "Error getting state for %s: %s",
                self.entity_description.key,
                err
            )
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

class UnraidDockerContainerSwitch(UnraidSwitchEntity):
    """Representation of an Unraid Docker container switch."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        container_name: str
    ) -> None:
        """Initialize the Docker container switch."""
        self._container_name = container_name
        super().__init__(
            coordinator,
            UnraidSwitchEntityDescription(
                key=f"docker_{container_name}",
                name=f"{container_name}",
                icon="mdi:docker",
                value_fn=self._get_container_state,
            )
        )

    def _get_container_state(self, data: dict) -> bool:
        """Get container state."""
        for container in data["docker_containers"]:
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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the container on."""
        await self.coordinator.api.start_container(self._container_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the container off."""
        await self.coordinator.api.stop_container(self._container_name)
        await self.coordinator.async_request_refresh()

class UnraidVMSwitch(UnraidSwitchEntity):
    """Representation of an Unraid VM switch."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        vm_name: str
    ) -> None:
        """Initialize the VM switch."""
        self._vm_name = vm_name
        self._last_known_state = None

        # Create a safe entity ID from VM name with collision detection
        from .utils import normalize_name
        safe_name = normalize_name(vm_name)
        # Ensure it doesn't start with a number (Home Assistant requirement)
        if safe_name and safe_name[0].isdigit():
            safe_name = f"vm_{safe_name}"

        # Handle entity ID collisions by checking existing VMs
        safe_name = self._ensure_unique_entity_id(safe_name, vm_name, coordinator)

        super().__init__(
            coordinator,
            UnraidSwitchEntityDescription(
                key=f"vm_{safe_name}",
                name=f"{vm_name}",
                value_fn=self._get_vm_state,
            )
        )
        self._attr_entity_registry_enabled_default = True

        # Get OS type for specific model info
        self._get_os_type_info(vm_name, coordinator)

    def _ensure_unique_entity_id(self, base_name: str, vm_name: str, coordinator) -> str:
        """Ensure the entity ID is unique by checking for collisions with existing VMs.

        Args:
            base_name: The normalized base name for the entity ID
            vm_name: The original VM name
            coordinator: The coordinator containing VM data

        Returns:
            A unique entity ID that won't collide with existing VMs
        """
        from .utils import normalize_name

        # Get all existing VM names from coordinator data
        existing_vms = coordinator.data.get("vms", [])
        existing_normalized_names = set()

        for vm in existing_vms:
            existing_vm_name = vm.get("name", "")
            if existing_vm_name and existing_vm_name != vm_name:  # Don't include current VM
                existing_normalized = normalize_name(existing_vm_name)
                if existing_normalized and existing_normalized[0].isdigit():
                    existing_normalized = f"vm_{existing_normalized}"
                existing_normalized_names.add(existing_normalized)

        # If no collision, return the base name
        if base_name not in existing_normalized_names:
            return base_name

        # Handle collision by adding a suffix based on original VM name characteristics
        # Strategy: Use distinguishing characteristics from the original name

        # Try to create a unique suffix based on the original name
        import re

        # Extract unique characteristics from the original VM name
        # 1. Check for different separators (dash vs space vs underscore)
        if '-' in vm_name and ' ' not in vm_name:
            suffix = "dash"
        elif ' ' in vm_name and '-' not in vm_name:
            suffix = "space"
        elif '_' in vm_name:
            suffix = "underscore"
        else:
            # 2. Use position-based numbering or character-based differentiation
            # Extract any numbers or special patterns
            numbers = re.findall(r'\d+', vm_name)
            if numbers:
                suffix = f"n{numbers[-1]}"  # Use last number found
            else:
                # 3. Use length or hash-based suffix as last resort
                suffix = f"len{len(vm_name)}"

        candidate_name = f"{base_name}_{suffix}"

        # If still collision, fall back to incremental numbering
        counter = 2
        while candidate_name in existing_normalized_names:
            candidate_name = f"{base_name}_{suffix}_{counter}"
            counter += 1

        return candidate_name

    def _get_os_type_info(self, vm_name: str, coordinator) -> None:
        """Get OS type for specific model info."""
        for vm in coordinator.data.get("vms", []):
            if vm["name"] == vm_name and "os_type" in vm:
                self._attr_device_info["model"] = f"{vm['os_type'].capitalize()} Virtual Machine"
                break

    def _get_vm_state(self, data: dict) -> bool:
        """Get VM state."""
        for vm in data.get("vms", []):
            if vm["name"] == self._vm_name:
                state = vm["status"].lower()
                self._last_known_state = state
                return state == "running"
        return False

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

        vms_enabled = "vms" in self.coordinator.data and isinstance(self.coordinator.data["vms"], list)
        return vms_enabled and any(vm["name"] == self._vm_name for vm in self.coordinator.data.get("vms", []))

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the VM on."""
        await self.coordinator.api.start_vm(self._vm_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the VM off."""
        await self.coordinator.api.stop_vm(self._vm_name)
        await self.coordinator.async_request_refresh()

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid switch based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = []

    # Add Docker container switches
    if "docker_containers" in coordinator.data:  # This checks base Docker container data, not docker_insights
        _LOGGER.debug("Setting up Docker container switches")
        switches.extend([
            UnraidDockerContainerSwitch(
                coordinator=coordinator,
                container_name=container["name"]
            )
            for container in coordinator.data["docker_containers"]
        ])
    else:
        _LOGGER.debug("No Docker containers found for switches")

    # Add VM switches
    if "vms" in coordinator.data:
        _LOGGER.debug("Setting up VM switches")
        switches.extend([
            UnraidVMSwitch(
                coordinator=coordinator,
                vm_name=vm["name"]
            )
            for vm in coordinator.data["vms"]
        ])
    else:
        _LOGGER.debug("No VMs found for switches")

    if switches:
        async_add_entities(switches)