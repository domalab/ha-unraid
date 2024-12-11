"""Button platform for Unraid integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.button import ( # type: ignore
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry # type: ignore # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.entity import EntityCategory # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore
from homeassistant.exceptions import HomeAssistantError # type: ignore

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidButtonDescription(ButtonEntityDescription):
    """Class describing Unraid button entities."""

    press_fn: Callable[[Any], Any] | None = None
    icon: str | None = None


BUTTON_TYPES: tuple[UnraidButtonDescription, ...] = (
    UnraidButtonDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        press_fn=lambda api: api.system_reboot(delay=0),
    ),
    UnraidButtonDescription(
        key="shutdown",
        name="Shutdown",
        icon="mdi:power",
        press_fn=lambda api: api.system_shutdown(delay=0),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid button based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.debug("Setting up Unraid buttons for %s", coordinator.hostname)

    async_add_entities(
        UnraidButton(coordinator, description)
        for description in BUTTON_TYPES
    )

class UnraidButton(ButtonEntity):
    """Representation of an Unraid button."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidButtonDescription,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self.entity_description = description
        
        # Set unique_id combining entry_id and button key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        
        # Set name and icon
        self._attr_name = description.name
        if description.icon:
            self._attr_icon = description.icon
            
        # Set device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"Unraid Server ({coordinator.hostname})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if not self.entity_description.press_fn:
                raise HomeAssistantError(f"No press function defined for {self.name}")

            _LOGGER.info(
                "Executing %s command for Unraid instance: %s",
                self.entity_description.key,
                self.coordinator.hostname
            )
            
            await self.entity_description.press_fn(self.coordinator.api)
            
        except Exception as err:
            _LOGGER.error(
                "Failed to execute %s command: %s",
                self.entity_description.key,
                err
            )
            raise HomeAssistantError(f"Failed to execute {self.name} command: {err}") from err