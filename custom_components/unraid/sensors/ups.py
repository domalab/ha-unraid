"""UPS server power sensor for Unraid integration.

This module provides a sensor for monitoring UPS power consumption
for use with the Home Assistant Energy Dashboard.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
import homeassistant.util.dt as dt_util

from .base import UnraidSensorBase, ValueValidationMixin
from .const import (
    DOMAIN,
    UnraidSensorEntityDescription,
    UPS_METRICS,
)
from ..entity_naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UPSMetricsMixin(ValueValidationMixin):
    """Mixin for UPS metrics handling."""

    def _validate_ups_metric(
        self,
        metric: str,
        value: Any,
    ) -> float | None:
        """Validate UPS metric value."""
        if metric not in UPS_METRICS:
            return None

        try:
            if isinstance(value, str):
                # Clean up value string
                numeric_value = float(''.join(
                    c for c in value if c.isdigit() or c in '.-'
                ))
            else:
                numeric_value = float(value)

            # Get validation range
            metric_info = UPS_METRICS[metric]
            min_value = metric_info["min"]
            max_value = metric_info["max"]

            # Validate range
            return self._validate_value(
                numeric_value,
                min_value=min_value,
                max_value=max_value
            )

        except (ValueError, TypeError) as err:
            _LOGGER.debug(
                "Error validating UPS metric %s value '%s': %s",
                metric,
                value,
                err
            )
            return None

    def _calculate_power(
        self,
        nominal_power: float | None,
        load_percent: float | None
    ) -> float | None:
        """Calculate current power usage."""
        if nominal_power is None or load_percent is None:
            return None

        try:
            power = (nominal_power * load_percent) / 100.0
            if 0 <= power <= nominal_power:
                return round(power, 2)
            return None
        except (TypeError, ValueError, ZeroDivisionError) as err:
            _LOGGER.debug("Error calculating power: %s", err)
            return None

class UnraidUPSServerPowerSensor(UnraidSensorBase, UPSMetricsMixin):
    """UPS server power consumption sensor for Energy Dashboard."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="ups_server_power",
            name="UPS Server Power",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:server",
            suggested_display_precision=1,
            value_fn=self._get_server_power_usage,
        )
        super().__init__(coordinator, description)
        UPSMetricsMixin.__init__(self)

    def _get_server_power_usage(self, data: dict) -> float | None:
        """Get current server power usage from UPS."""
        try:
            ups_info = data.get("system_stats", {}).get("ups_info", {})
            nominal_power = self._validate_ups_metric(
                "NOMPOWER",
                ups_info.get("NOMPOWER")
            )
            load_percent = self._validate_ups_metric(
                "LOADPCT",
                ups_info.get("LOADPCT")
            )

            return self._calculate_power(nominal_power, load_percent)

        except (KeyError, TypeError) as err:
            _LOGGER.debug("Error getting server power usage: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info", {})
            return {
                "model": ups_info.get("MODEL", "Unknown"),
                "nominal_power": f"{ups_info.get('NOMPOWER', '0')}W",
                "load_percentage": f"{ups_info.get('LOADPCT', '0')}%",
                "last_update": dt_util.now().isoformat(),
                "energy_dashboard_compatible": True,
            }
        except (KeyError, TypeError) as err:
            _LOGGER.debug("Error getting server power attributes: %s", err)
            return {}

class UnraidUPSSensors:
    """Helper class to create UPS sensors.

    Only creates the UPS Server Power sensor for Energy Dashboard if NOMPOWER is available.
    """

    def __init__(self, coordinator) -> None:
        """Initialize UPS sensors."""
        self.entities = []

        if coordinator.has_ups:
            # Check if UPS info has NOMPOWER attribute
            _LOGGER.debug("Checking for UPS NOMPOWER attribute")
            ups_info = coordinator.data.get("system_stats", {}).get("ups_info", {})

            if ups_info and "NOMPOWER" in ups_info:
                _LOGGER.info(
                    "Creating UPS Server Power sensor for Energy Dashboard. "
                    "NOMPOWER: %sW",
                    ups_info.get("NOMPOWER")
                )
                self.entities.append(UnraidUPSServerPowerSensor(coordinator))
            else:
                _LOGGER.warning(
                    "NOMPOWER attribute not available in UPS data, "
                    "skipping UPS Server Power sensor"
                )


