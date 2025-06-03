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
                    "Array State": self._format_array_state(array_data),
                    "Last Updated": dt_util.now().isoformat(),
                }

            # Otherwise, extract all the attributes with user-friendly formatting
            return {
                "Array State": self._format_array_state(array_data.get("state", "unknown")),
                "Parity Synchronized": self._format_boolean(array_data.get("synced", False)),
                "Current Operation": self._format_sync_action(array_data.get("sync_action")),
                "Operation Progress": self._format_sync_progress(array_data.get("sync_progress", 0)),
                "Operation Errors": self._format_sync_errors(array_data.get("sync_errors", 0)),
                "Total Disks": self._format_disk_count(array_data.get("num_disks", 0)),
                "Disabled Disks": self._format_disabled_disks(array_data.get("num_disabled", 0)),
                "Invalid Disks": self._format_invalid_disks(array_data.get("num_invalid", 0)),
                "Missing Disks": self._format_missing_disks(array_data.get("num_missing", 0)),
                "Last Updated": dt_util.now().isoformat(),
            }
        except Exception as err:
            _LOGGER.debug("Error getting array attributes: %s", err)
            return {}

    def _format_array_state(self, state: str) -> str:
        """Format array state to user-friendly description."""
        if not state:
            return "Unknown"

        state_upper = state.upper()
        state_mappings = {
            "STARTED": "Array Running",
            "STOPPED": "Array Stopped",
            "STARTING": "Array Starting",
            "STOPPING": "Array Stopping",
            "UNKNOWN": "Status Unknown",
            "ERROR": "Array Error"
        }
        return state_mappings.get(state_upper, state.title())

    def _format_boolean(self, value: bool) -> str:
        """Format boolean values to Yes/No."""
        return "Yes" if value else "No"

    def _format_sync_action(self, action: str) -> str:
        """Format sync action to user-friendly description."""
        if not action or action == "IDLE":
            return "None"

        action_mappings = {
            "check P": "Parity Check",
            "check": "Parity Check",
            "recon P": "Parity Rebuild",
            "recon": "Data Rebuild",
            "clear": "Disk Clear",
            "sync": "Synchronizing"
        }
        return action_mappings.get(action, action.title())

    def _format_sync_progress(self, progress: float) -> str:
        """Format sync progress with percentage."""
        if progress == 0:
            return "Not Running"
        return f"{progress:.1f}%"

    def _format_sync_errors(self, errors: int) -> str:
        """Format sync errors count."""
        if errors == 0:
            return "None"
        elif errors == 1:
            return "1 Error"
        else:
            return f"{errors} Errors"

    def _format_disk_count(self, count: int) -> str:
        """Format disk count."""
        if count == 0:
            return "No Disks"
        elif count == 1:
            return "1 Disk"
        else:
            return f"{count} Disks"

    def _format_disabled_disks(self, count: int) -> str:
        """Format disabled disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Failed/Offline)"
        else:
            return f"{count} Disks (Failed/Offline)"

    def _format_invalid_disks(self, count: int) -> str:
        """Format invalid disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Wrong/Unrecognized)"
        else:
            return f"{count} Disks (Wrong/Unrecognized)"

    def _format_missing_disks(self, count: int) -> str:
        """Format missing disk count with explanation."""
        if count == 0:
            return "None"
        elif count == 1:
            return "1 Disk (Not Present)"
        else:
            return f"{count} Disks (Not Present)"
