"""Array status binary sensor for Unraid."""
from __future__ import annotations

import logging

from homeassistant.const import EntityCategory
import homeassistant.util.dt as dt_util

from .base import UnraidBinarySensorBase
from .const import UnraidBinarySensorEntityDescription
from ..coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

class UnraidArrayStatusBinarySensor(UnraidBinarySensorBase):
    """Binary sensor for array status monitoring."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize array status binary sensor."""
        description = UnraidBinarySensorEntityDescription(
            key="array_status",
            name="Array Status",
            device_class=None,  # Remove device_class to use custom state strings
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:harddisk-plus",
        )

        super().__init__(coordinator, description)

        _LOGGER.debug(
            "Initialized Array Status binary sensor | name: %s",
            self._attr_name
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if the array is started/running."""
        try:
            # Try to get array_state first (from batched command)
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            # Get state from the data
            if isinstance(array_data, dict):
                state = array_data.get("state", "unknown").lower()
            elif isinstance(array_data, str):
                state = array_data.lower()
            else:
                state = "unknown"

            # Return True if array is started
            return state == "started"

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting array status: %s", err)
            return None

    @property
    def state(self) -> str:
        """Return the state of the binary sensor as a string."""
        if self.is_on is True:
            return "Started"
        elif self.is_on is False:
            return "Stopped"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return additional state attributes."""
        try:
            # Try to get array_state first (from batched command)
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            # If array_data is a string, just return the raw state
            if isinstance(array_data, str):
                return {
                    "raw_state": array_data,
                    "last_update": dt_util.now().isoformat(),
                }

            # Otherwise, extract all the attributes
            return {
                "raw_state": array_data.get("state", "unknown"),
                "synced": array_data.get("synced", False),
                "sync_action": array_data.get("sync_action"),
                "sync_progress": array_data.get("sync_progress", 0),
                "sync_errors": array_data.get("sync_errors", 0),
                "num_disks": array_data.get("num_disks", 0),
                "num_disabled": array_data.get("num_disabled", 0),
                "num_invalid": array_data.get("num_invalid", 0),
                "num_missing": array_data.get("num_missing", 0),
                "last_update": dt_util.now().isoformat(),
            }
        except Exception as err:
            _LOGGER.debug("Error getting array attributes: %s", err)
            return {}
