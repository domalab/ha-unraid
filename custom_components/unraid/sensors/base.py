"""Base sensor implementations for Unraid."""
from __future__ import annotations

import logging
from typing import Any, Protocol
from datetime import datetime, timezone

from homeassistant.components.sensor import ( # type: ignore
    SensorEntity,
)
from homeassistant.const import EntityCategory # type: ignore
from homeassistant.core import callback # type: ignore
from homeassistant.helpers.update_coordinator import ( # type: ignore
    CoordinatorEntity,
)
from homeassistant.helpers.typing import StateType # type: ignore
from homeassistant.helpers.entity import DeviceInfo # type: ignore

from ..const import DOMAIN
from .const import UnraidSensorEntityDescription
from ..naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UnraidDataProtocol(Protocol):
    """Protocol for accessing coordinator data."""

    @property
    def data(self) -> dict[str, Any]:
        """Return coordinator data."""

    @property
    def hostname(self) -> str:
        """Return server hostname."""

    @property
    def last_update_success(self) -> bool:
        """Return if last update was successful."""

class SensorUpdateMixin:
    """Mixin for sensor update handling."""

    def __init__(self) -> None:
        """Initialize the mixin."""
        self._last_update: datetime | None = None
        self._error_count: int = 0
        self._last_value: StateType = None

    def _handle_update_error(self, err: Exception) -> None:
        """Handle update errors with exponential backoff."""
        self._error_count += 1
        if self._error_count <= 3:  # Log first 3 errors
            _LOGGER.error(
                "Error updating sensor %s: %s",
                self.entity_description.key,
                err
            )

    def _reset_error_count(self) -> None:
        """Reset error count on successful update."""
        if self._error_count > 0:
            self._error_count = 0
            _LOGGER.debug(
                "Reset error count for sensor %s after successful update",
                self.entity_description.key
            )

class ValueValidationMixin:
    """Mixin for sensor value validation."""

    def _validate_value(
        self,
        value: StateType,
        min_value: float | None = None,
        max_value: float | None = None
    ) -> StateType | None:
        """Validate sensor value against bounds."""
        if value is None:
            return None

        try:
            if isinstance(value, (int, float)):
                if min_value is not None and value < min_value:
                    _LOGGER.warning(
                        "Value %s below minimum %s for sensor %s",
                        value,
                        min_value,
                        self.entity_description.key
                    )
                    return None
                if max_value is not None and value > max_value:
                    _LOGGER.warning(
                        "Value %s above maximum %s for sensor %s",
                        value,
                        max_value,
                        self.entity_description.key
                    )
                    return None
            return value
        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Value validation error for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None

class UnraidSensorBase(CoordinatorEntity, SensorEntity, SensorUpdateMixin, ValueValidationMixin):
    """Base class for Unraid sensors."""

    entity_description: UnraidSensorEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataProtocol,
        description: UnraidSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        SensorUpdateMixin.__init__(self)

        self.entity_description = description
        self._attr_has_entity_name = True

        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component=description.key.split('_')[0]  # Get first part of key as component
        )

        # Set consistent entity ID
        self._attr_unique_id = naming.get_entity_id(description.key)
        
        # Set name using cleaned hostname
        self._attr_name = f"{naming.clean_hostname()} {description.name}"
        
        _LOGGER.debug("Base Entity initialized | unique_id: %s | name: %s | description.key: %s",
                self._attr_unique_id, self._attr_name, description.key)

        # Optional display settings from description
        if description.suggested_unit_of_measurement:
            self._attr_suggested_unit_of_measurement = description.suggested_unit_of_measurement

        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = description.suggested_display_precision

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=f"Unraid Server ({self.coordinator.hostname})",
            manufacturer="Lime Technology",
            model="Unraid Server",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            if not self.available:
                return None

            value = self.entity_description.value_fn(self.coordinator.data)
            self._last_value = value
            self._reset_error_count()
            return value

        except (KeyError, AttributeError, TypeError, ValueError) as err:
            self._handle_update_error(err)
            return self._last_value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        try:
            return self.entity_description.available_fn(self.coordinator.data)
        except (KeyError, AttributeError, TypeError, ValueError) as err:
            _LOGGER.debug(
                "Error checking availability for %s: %s",
                self.entity_description.key,
                err
            )
            return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._last_update = datetime.now(timezone.utc)
        self.async_write_ha_state()

class UnraidDiagnosticMixin:
    """Mixin for diagnostic sensors."""

    def __init__(self) -> None:
        """Initialize diagnostic mixin."""
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

class UnraidConfigMixin:
    """Mixin for configuration sensors."""

    def __init__(self) -> None:
        """Initialize configuration mixin."""
        self._attr_entity_category = EntityCategory.CONFIG
