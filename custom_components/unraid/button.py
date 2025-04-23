"""Button platform for Unraid integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.button import ( # type: ignore
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.entity import EntityCategory # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore
from homeassistant.exceptions import HomeAssistantError # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator
from .entity_naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidButtonDescription(ButtonEntityDescription):
    """Class describing Unraid button entities."""

    press_fn: Callable[[Any], Any] | None = None
    icon: str | None = None
    entity_registry_enabled_default: bool = False

@dataclass
class UnraidScriptButtonDescription(ButtonEntityDescription):
    """Class describing Unraid script button entities."""
    script_name: str = ""
    background: bool = False

BUTTON_TYPES: tuple[UnraidButtonDescription, ...] = (
    UnraidButtonDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        press_fn=lambda api: api.system_reboot(delay=0),
        entity_registry_enabled_default=True,
    ),
    UnraidButtonDescription(
        key="shutdown",
        name="Shutdown",
        icon="mdi:power",
        press_fn=lambda api: api.system_shutdown(delay=0),
        entity_registry_enabled_default=True,
    ),
)

def get_script_buttons(coordinator: UnraidDataUpdateCoordinator) -> list[ButtonEntity]:
    """Get button entities for user scripts."""
    buttons = []

    if not coordinator.data:
        _LOGGER.warning("No data available from coordinator")
        return buttons

    scripts = coordinator.data.get("user_scripts", [])
    if not scripts:
        _LOGGER.debug("No user scripts found")
        return buttons

    for script in scripts:
        # Create foreground button if supported
        if not script.get("background_only", False):
            buttons.append(
                UnraidScriptButton(
                    coordinator,
                    UnraidScriptButtonDescription(
                        key=f"{script['name']}_run",
                        name=f"{script['name']}",
                        script_name=script["name"],
                        background=False,
                        icon="mdi:script-text-play",
                    ),
                )
            )

        # Create background button if supported
        if not script.get("foreground_only", False):
            buttons.append(
                UnraidScriptButton(
                    coordinator,
                    UnraidScriptButtonDescription(
                        key=f"{script['name']}_background",
                        name=f"{script['name']} (Background)",
                        script_name=script["name"],
                        background=True,
                        icon="mdi:script-text-play-outline",
                    ),
                )
            )

    return buttons

def truncate_output(output: str, max_length: int = 1000) -> str:
    """Truncate output to a reasonable size and add notice if truncated."""
    if not output:
        return ""
    if len(output) > max_length:
        truncated = output[:max_length]
        return f"{truncated}... (Output truncated, full length: {len(output)} bytes)"
    return output

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid button based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.debug("Setting up Unraid buttons for %s", coordinator.hostname)

    # Add system buttons (reboot/shutdown)
    entities = [
        UnraidButton(coordinator, description)
        for description in BUTTON_TYPES
    ]

    # Add script buttons
    try:
        script_buttons = get_script_buttons(coordinator)
        entities.extend(script_buttons)
    except Exception as err:
        _LOGGER.error("Error setting up script buttons: %s", err)

    async_add_entities(entities)

class UnraidButton(ButtonEntity):
    """Representation of an Unraid button."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidButtonDescription,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self.entity_description = description

        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component=description.key.split('_')[0]  # Get first part of key as component
        )

        # Set unique_id and name using naming utility
        self._attr_unique_id = naming.get_entity_id(description.key)
        self._attr_name = f"{description.name}"

        # Set name and icon
        if description.icon:
            self._attr_icon = description.icon

        # Set device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"{coordinator.hostname.title()}",
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

class UnraidScriptButton(ButtonEntity):
    """Representation of an Unraid script button."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False  # Disabled by default

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidScriptButtonDescription,
    ) -> None:
        """Initialize the button."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="script"
        )

        self._attr_extra_state_attributes = {}  # Instance-level attribute
        self.coordinator = coordinator
        self.entity_description: UnraidScriptButtonDescription = description

        # Set unique_id and name using naming utility
        self._attr_unique_id = naming.get_entity_id(description.key)
        self._attr_name = f"{description.name}"

        # Set icon if provided
        if description.icon:
            self._attr_icon = description.icon

        # Set device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"{coordinator.hostname.title()}",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            script_name = self.entity_description.script_name
            background = self.entity_description.background

            _LOGGER.info(
                "Executing script %s in %s mode on Unraid instance: %s",
                script_name,
                "background" if background else "foreground",
                self.coordinator.hostname,
            )

            # Update running state and add execution info
            self._attr_extra_state_attributes.update({
                "running": True,
                "last_executed_at": dt_util.now().isoformat(),
                "execution_type": "background" if background else "foreground",
                "status": "running"
            })
            self.async_write_ha_state()

            # Execute script
            result = await self.coordinator.api.execute_user_script(
                script_name,
                background=background
            )

            # For background scripts, keep running state true
            is_running = background

            # Update completion state with truncated output
            self._attr_extra_state_attributes.update({
                "running": is_running,
                "status": "running" if is_running else "completed",
                "last_result": truncate_output(result) if result else "No output",
                "completed_at": dt_util.now().isoformat() if not is_running else None
            })
            self.async_write_ha_state()

            # Request a coordinator update to refresh script states
            await self.coordinator.async_request_refresh()

        except Exception as err:
            # Get the script name safely
            try:
                script_name = self.entity_description.script_name
            except AttributeError:
                script_name = "unknown"

            # Create error message
            error_msg = f"Failed to execute script {script_name}: {str(err)}"

            # Update state attributes
            self._attr_extra_state_attributes.update({
                "running": False,
                "status": "error",
                "error": str(err),
                "error_at": dt_util.now().isoformat()
            })
            self.async_write_ha_state()

            _LOGGER.error(error_msg)
            raise HomeAssistantError(error_msg) from err