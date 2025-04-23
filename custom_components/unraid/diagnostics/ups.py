"""UPS monitoring for Unraid."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass # type: ignore
from homeassistant.const import EntityCategory # type: ignore

from .base import UnraidBinarySensorBase
from .const import UnraidBinarySensorEntityDescription
from ..coordinator import UnraidDataUpdateCoordinator
# from ..const import DOMAIN
# from ..helpers import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UnraidUPSBinarySensor(UnraidBinarySensorBase):
    """Binary sensor for UPS monitoring."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize UPS binary sensor."""
        # Entity naming not used in this class
        # EntityNaming(
        #     domain=DOMAIN,
        #     hostname=coordinator.hostname,
        #     component="ups"
        # )

        description = UnraidBinarySensorEntityDescription(
            key="ups_status",
            name="UPS Status",
            device_class=BinarySensorDeviceClass.POWER,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:battery-medium",
        )

        super().__init__(coordinator, description)

        _LOGGER.debug(
            "Initialized UPS binary sensor | name: %s",
            self._attr_name
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        try:
            ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info")
            has_ups = bool(ups_info)

            if not has_ups:
                _LOGGER.debug("No UPS info available in coordinator data")

            return self.coordinator.last_update_success and has_ups

        except Exception as err:
            _LOGGER.error("Error checking UPS availability: %s", err)
            return False

    @property
    def is_on(self) -> bool | None:
        """Return true if the UPS is online."""
        try:
            status = self.coordinator.data["system_stats"].get("ups_info", {}).get("STATUS")
            if status is None:
                _LOGGER.debug("No UPS status available")
                return None

            is_online = status.upper() in ["ONLINE", "ON LINE"]
            _LOGGER.debug("UPS status: %s (online: %s)", status, is_online)
            return is_online

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting UPS status: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            ups_info = self.coordinator.data["system_stats"].get("ups_info", {})

            # Base attributes
            attrs = {
                "model": ups_info.get("MODEL", "Unknown"),
                "status": ups_info.get("STATUS", "Unknown"),
            }

            # Store binary sensor data in coordinator for other sensors to use
            if "binary_sensors" not in self.coordinator.data:
                self.coordinator.data["binary_sensors"] = {}

            # Use entity_id as the key
            self.coordinator.data["binary_sensors"][self.entity_id] = {
                "state": self.state,
                "attributes": {},  # Will be populated below
            }

            # Add percentage values with validation
            for key, attr_name in [
                ("BCHARGE", "battery_charge"),
                ("LOADPCT", "load_percentage")
            ]:
                if value := ups_info.get(key):
                    try:
                        # Ensure value is numeric and within range
                        numeric_value = float(value)
                        if 0 <= numeric_value <= 100:
                            attrs[attr_name] = f"{numeric_value}%"
                        else:
                            _LOGGER.warning(
                                "Invalid %s value: %s (expected 0-100)",
                                key,
                                value
                            )
                    except (ValueError, TypeError) as err:
                        _LOGGER.debug(
                            "Error processing %s value: %s",
                            key,
                            err
                        )

            # Add time values
            if runtime := ups_info.get("TIMELEFT"):
                try:
                    # Ensure runtime is numeric and positive
                    runtime_value = float(runtime)
                    if runtime_value >= 0:
                        attrs["runtime_left"] = f"{runtime_value} minutes"
                    else:
                        _LOGGER.warning(
                            "Invalid runtime value: %s (expected >= 0)",
                            runtime
                        )
                except (ValueError, TypeError) as err:
                    _LOGGER.debug(
                        "Error processing runtime value: %s",
                        err
                    )

            # Add power/voltage values with validation
            for key, attr_name, unit in [
                ("NOMPOWER", "nominal_power", "W"),
                ("LINEV", "line_voltage", "V"),
                ("BATTV", "battery_voltage", "V")
            ]:
                if value := ups_info.get(key):
                    try:
                        # Ensure value is numeric and positive
                        numeric_value = float(value)
                        if numeric_value >= 0:
                            attrs[attr_name] = f"{numeric_value}{unit}"
                        else:
                            _LOGGER.warning(
                                "Invalid %s value: %s (expected >= 0)",
                                key,
                                value
                            )
                    except (ValueError, TypeError) as err:
                        _LOGGER.debug(
                            "Error processing %s value: %s",
                            key,
                            err
                        )

            # Additional UPS details if available
            if firmware := ups_info.get("FIRMWARE"):
                attrs["firmware"] = firmware
            if serial := ups_info.get("SERIALNO"):
                attrs["serial_number"] = serial
            if manufacture_date := ups_info.get("MANDATE"):
                attrs["manufacture_date"] = manufacture_date

            _LOGGER.debug("UPS attributes: %s", attrs)

            # Store attributes in coordinator for other sensors to use
            if "binary_sensors" in self.coordinator.data and self.entity_id in self.coordinator.data["binary_sensors"]:
                self.coordinator.data["binary_sensors"][self.entity_id]["attributes"] = attrs.copy()

            return attrs

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting UPS attributes: %s", err)
            return {}

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        if self.is_on is None:
            return "Unknown"
        return "Online" if self.is_on else "Offline"
