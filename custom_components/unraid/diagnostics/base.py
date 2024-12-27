"""Base binary sensor implementations for Unraid."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import ( # type: ignore
    BinarySensorEntity,
)
from homeassistant.core import callback # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore
from homeassistant.helpers.entity import DeviceInfo # type: ignore

from ..const import DOMAIN
from .const import UnraidBinarySensorEntityDescription
from ..naming import EntityNaming
from ..coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

class UnraidBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Unraid binary sensors."""

    entity_description: UnraidBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_has_entity_name = True

        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component=description.key.split('_')[0]
        )

        self._attr_unique_id = naming.get_entity_id(description.key)
        self._attr_name = f"{naming.clean_hostname()} {description.name}"

        _LOGGER.debug(
            "Binary Sensor initialized | unique_id: %s | name: %s | description.key: %s",
            self._attr_unique_id,
            self._attr_name,
            description.key
        )

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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except KeyError as err:
            _LOGGER.debug(
                "Missing key in data for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except TypeError as err:
            _LOGGER.debug(
                "Type error processing sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except AttributeError as err:
            _LOGGER.debug(
                "Attribute error for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()