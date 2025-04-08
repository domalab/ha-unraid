"""Sensor platform for Unraid."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator
from .sensors.factory import SensorFactory
from .sensors.registry import register_all_sensors

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        # Register all sensor types
        register_all_sensors()

        # Create all sensor entities using the factory
        entities = SensorFactory.create_all_sensors(coordinator)

        if entities:
            async_add_entities(entities)
            _LOGGER.info(
                "Successfully added %d sensors for Unraid %s",
                len(entities),
                coordinator.hostname
            )
        else:
            _LOGGER.warning(
                "No sensors were created for Unraid %s",
                coordinator.hostname
            )

    except Exception as err:
        _LOGGER.error(
            "Error setting up Unraid sensors: %s",
            err,
            exc_info=True
        )