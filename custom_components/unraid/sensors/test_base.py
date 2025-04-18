"""Base sensor implementations for Unraid tests."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


class UnraidTestSensor(CoordinatorEntity, SensorEntity):
    """Base class for Unraid test sensors."""

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return getattr(self.coordinator, "available", True)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_has_entity_name = True

        # Add last_update_success and available for compatibility with tests
        if not hasattr(coordinator, "last_update_success"):
            coordinator.last_update_success = True
        self._available = getattr(coordinator, "available", True)
