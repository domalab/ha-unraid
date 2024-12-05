"""Sensor platform for Unraid."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore

from .const import DOMAIN
from .sensors import (
    UnraidSystemSensors,
    UnraidStorageSensors,
    UnraidNetworkSensors,
    UnraidDockerSensors,
    UnraidUPSSensors,
)
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        # Create all sensor entities
        entities = []

        # System sensors (CPU, RAM, etc.)
        entities.extend(UnraidSystemSensors(coordinator).entities)
        _LOGGER.debug("Added system sensors")

        # Storage sensors (Array, Disks, Cache)
        entities.extend(UnraidStorageSensors(coordinator).entities)
        _LOGGER.debug("Added storage sensors")

        # Network sensors
        network_sensors = UnraidNetworkSensors(coordinator).entities
        if network_sensors:
            entities.extend(network_sensors)
            _LOGGER.debug("Added network sensors for active interfaces")

        # Docker sensors (if enabled)
        if coordinator.docker_insights:
            docker_sensors = UnraidDockerSensors(coordinator).entities
            if docker_sensors:
                entities.extend(docker_sensors)
                _LOGGER.debug("Added Docker sensors")

        # UPS sensors (if available)
        if coordinator.has_ups:
            ups_sensors = UnraidUPSSensors(coordinator).entities
            if ups_sensors:
                entities.extend(ups_sensors)
                _LOGGER.debug("Added UPS sensors")

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