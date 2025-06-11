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
from homeassistant.const import UnitOfPower, UnitOfEnergy
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
        """Return additional state attributes with user-friendly formatting."""
        try:
            ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info", {})

            # Get raw values
            model = ups_info.get("MODEL", "Unknown")
            nominal_power = ups_info.get("NOMPOWER", "0")
            load_pct = ups_info.get("LOADPCT", "0")
            battery_charge = ups_info.get("BCHARGE", "0")
            battery_runtime = ups_info.get("TIMELEFT", "0")

            attrs = {
                "ups_model": model,
                "rated_power": f"{nominal_power}W",
                "current_load": f"{load_pct}%",
                "last_updated": dt_util.now().isoformat(),
                "energy_dashboard_ready": True,
            }

            # Add battery information if available
            if battery_charge and battery_charge != "0":
                attrs["battery_charge"] = f"{battery_charge}%"

                # Add battery status description
                try:
                    charge_val = float(battery_charge)
                    if charge_val >= 90:
                        attrs["battery_status"] = "Excellent"
                    elif charge_val >= 70:
                        attrs["battery_status"] = "Good"
                    elif charge_val >= 50:
                        attrs["battery_status"] = "Fair"
                    elif charge_val >= 25:
                        attrs["battery_status"] = "Low"
                    else:
                        attrs["battery_status"] = "Critical"
                except (ValueError, TypeError):
                    attrs["battery_status"] = "Unknown"

            # Add runtime information if available
            if battery_runtime and battery_runtime != "0":
                try:
                    runtime_minutes = float(battery_runtime)
                    if runtime_minutes >= 60:
                        hours = int(runtime_minutes // 60)
                        minutes = int(runtime_minutes % 60)
                        attrs["estimated_runtime"] = f"{hours}h {minutes}m"
                    else:
                        attrs["estimated_runtime"] = f"{int(runtime_minutes)}m"
                except (ValueError, TypeError):
                    attrs["estimated_runtime"] = f"{battery_runtime} minutes"

            # Add load status description
            try:
                load_val = float(load_pct)
                if load_val >= 90:
                    attrs["load_status"] = "Very High - Check connected devices"
                elif load_val >= 70:
                    attrs["load_status"] = "High"
                elif load_val >= 50:
                    attrs["load_status"] = "Moderate"
                elif load_val >= 25:
                    attrs["load_status"] = "Light"
                else:
                    attrs["load_status"] = "Very Light"
            except (ValueError, TypeError):
                attrs["load_status"] = "Unknown"

            return attrs

        except (KeyError, TypeError) as err:
            _LOGGER.debug("Error getting server power attributes: %s", err)
            return {}

class UnraidUPSServerEnergySensor(UnraidSensorBase, UPSMetricsMixin):
    """UPS server energy consumption sensor for Energy Dashboard."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="ups_server_energy",
            name="UPS Server Energy",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:lightning-bolt",
            suggested_display_precision=3,
            value_fn=self._get_server_energy_usage,
        )
        super().__init__(coordinator, description)
        UPSMetricsMixin.__init__(self)
        self._last_power: float | None = None
        self._last_update: dt_util.datetime | None = None
        self._total_energy: float = 0.0
        self._initialized: bool = False

    def _get_server_energy_usage(self, data: dict) -> float | None:
        """Get cumulative server energy usage from UPS."""
        try:
            # Initialize from previous state if not done yet
            if not self._initialized:
                self._restore_state()
                self._initialized = True

            ups_info = data.get("system_stats", {}).get("ups_info", {})
            nominal_power = self._validate_ups_metric(
                "NOMPOWER",
                ups_info.get("NOMPOWER")
            )
            load_percent = self._validate_ups_metric(
                "LOADPCT",
                ups_info.get("LOADPCT")
            )

            current_power = self._calculate_power(nominal_power, load_percent)
            current_time = dt_util.now()

            # Only calculate energy if we have valid current power
            if current_power is not None:
                # If we have previous data, calculate energy consumed since last update
                if self._last_power is not None and self._last_update is not None:
                    # Calculate time difference in hours
                    time_diff = (current_time - self._last_update).total_seconds() / 3600.0

                    # Only calculate if time difference is reasonable (minimum 10 seconds, maximum 2 hours)
                    if 0.0028 <= time_diff <= 2.0:  # 10 seconds to 2 hours
                        # Calculate average power during this period
                        avg_power = (current_power + self._last_power) / 2.0

                        # Calculate energy consumed (kWh)
                        energy_consumed = (avg_power * time_diff) / 1000.0  # Convert W*h to kWh

                        # Add to total energy
                        self._total_energy += energy_consumed

                        _LOGGER.debug(
                            "UPS energy calculation: avg_power=%.2fW, time_diff=%.4fh, "
                            "energy_consumed=%.6fkWh, total_energy=%.6fkWh",
                            avg_power, time_diff, energy_consumed, self._total_energy
                        )
                    elif time_diff > 0:
                        # For very small time differences, still accumulate but with minimal energy
                        if time_diff < 0.0028:  # Less than 10 seconds
                            # Use minimum time difference to avoid division by zero but still accumulate
                            min_time_diff = 0.0028  # 10 seconds
                            avg_power = (current_power + self._last_power) / 2.0
                            energy_consumed = (avg_power * min_time_diff) / 1000.0
                            self._total_energy += energy_consumed

                            _LOGGER.debug(
                                "UPS energy calculation (short interval): avg_power=%.2fW, "
                                "actual_time_diff=%.6fh, used_time_diff=%.4fh, "
                                "energy_consumed=%.6fkWh, total_energy=%.6fkWh",
                                avg_power, time_diff, min_time_diff, energy_consumed, self._total_energy
                            )
                        else:
                            _LOGGER.debug(
                                "UPS energy: skipping calculation due to unusual time difference: %.4fh",
                                time_diff
                            )
                    else:
                        _LOGGER.debug(
                            "UPS energy: skipping calculation due to negative time difference: %.6fh",
                            time_diff
                        )

                # Update tracking variables
                self._last_power = current_power
                self._last_update = current_time

            return round(self._total_energy, 3) if self._total_energy > 0 else 0.0

        except (KeyError, TypeError) as err:
            _LOGGER.debug("Error getting server energy usage: %s", err)
            return None

    def _restore_state(self) -> None:
        """Restore previous energy state from Home Assistant registry."""
        try:
            if self.hass and hasattr(self.hass.states, 'get'):
                previous_state = self.hass.states.get(self.entity_id)
                if previous_state and previous_state.state not in ('unknown', 'unavailable'):
                    try:
                        self._total_energy = float(previous_state.state)
                        _LOGGER.debug(
                            "UPS energy sensor restored previous state: %.3f kWh",
                            self._total_energy
                        )
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not restore UPS energy state, starting from 0")
                        self._total_energy = 0.0
                else:
                    _LOGGER.debug("No previous UPS energy state found, starting from 0")
                    self._total_energy = 0.0
        except Exception as err:
            _LOGGER.debug("Error restoring UPS energy state: %s", err)
            self._total_energy = 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info", {})

            # Base attributes with proper capitalization
            attrs = {
                "UPS Model": ups_info.get("MODEL", "Unknown"),
                "Rated Power": f"{ups_info.get('NOMPOWER', '0')}W",
                "Current Power": f"{self._last_power or 0:.1f}W",
                "Last Updated": dt_util.now().isoformat(),
                "Energy Dashboard Ready": True,
            }

            # Add useful UPS status information
            load_pct = ups_info.get("LOADPCT")
            if load_pct:
                attrs["Load"] = f"{load_pct}%"

            battery_charge = ups_info.get("BCHARGE")
            if battery_charge:
                attrs["Battery"] = f"{battery_charge}%"

            runtime = ups_info.get("TIMELEFT")
            if runtime:
                attrs["Runtime"] = f"{runtime} minutes"

            status = ups_info.get("STATUS")
            if status:
                attrs["Status"] = status

            line_voltage = ups_info.get("LINEV")
            if line_voltage:
                attrs["Line Voltage"] = f"{line_voltage}V"

            return attrs

        except (KeyError, TypeError) as err:
            _LOGGER.debug("Error getting server energy attributes: %s", err)
            return {}

class UnraidUPSSensors:
    """Helper class to create UPS sensors.

    Creates both UPS Server Power and Energy sensors for Energy Dashboard if NOMPOWER is available.
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
                    "Creating UPS Server Power and Energy sensors for Energy Dashboard. "
                    "NOMPOWER: %sW",
                    ups_info.get("NOMPOWER")
                )
                # Add power sensor (instantaneous power consumption)
                self.entities.append(UnraidUPSServerPowerSensor(coordinator))
                # Add energy sensor (cumulative energy consumption)
                self.entities.append(UnraidUPSServerEnergySensor(coordinator))
            else:
                _LOGGER.warning(
                    "NOMPOWER attribute not available in UPS data, "
                    "skipping UPS Server sensors"
                )


