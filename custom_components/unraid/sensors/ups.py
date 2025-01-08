"""UPS-related sensors for Unraid."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
import re
from typing import Any, Dict

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import ( # type: ignore
    PERCENTAGE,
    UnitOfPower,
    UnitOfEnergy,
)
from homeassistant.core import callback # type: ignore
from homeassistant.helpers.restore_state import RestoreEntity # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidSensorBase, ValueValidationMixin
from .const import (
    DOMAIN, 
    UnraidSensorEntityDescription,
    UPS_METRICS,
    UPS_MODEL_PATTERNS,
)
from ..naming import EntityNaming

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

class UnraidUPSCurrentPowerSensor(UnraidSensorBase, UPSMetricsMixin):
    """UPS current power sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ups"
        )

        description = UnraidSensorEntityDescription(
            key="ups_current_consumption",
            name=f"{naming.get_entity_name('ups', 'ups')} Current Consumption",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:power-plug",
            suggested_display_precision=1,
            value_fn=self._get_power_usage,
        )
        super().__init__(coordinator, description)
        UPSMetricsMixin.__init__(self)
        self._last_energy = 0.0
        self._last_update = dt_util.now()

    def _get_power_usage(self, data: dict) -> float | None:
        """Get current UPS power usage."""
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
            _LOGGER.debug("Error getting UPS power usage: %s", err)
            return None

class UnraidUPSEnergyConsumption(UnraidSensorBase, UPSMetricsMixin, RestoreEntity):
    """UPS energy consumption sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ups"
        )

        description = UnraidSensorEntityDescription(
            key="ups_total_consumption",
            name=f"{naming.get_entity_name('ups', 'ups')} Total Consumption",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:flash",
            suggested_display_precision=3,
            value_fn=self._get_energy_consumption,
        )
        super().__init__(coordinator, description)
        UPSMetricsMixin.__init__(self)
        self._accumulated_energy = 0.0
        self._last_update = datetime.now(timezone.utc)
        self._last_power = None
        self._last_reset = None
        self._last_calculation_time = None
        self._error_count = 0
        self._last_power_value = None
        self._power_source = "direct"

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                restored_value = float(last_state.state)
                # Validate restored value
                if restored_value < 0:
                    _LOGGER.warning(
                        "Invalid negative energy value restored: %f",
                        restored_value
                    )
                    self._reset_energy_counter()
                else:
                    self._accumulated_energy = restored_value
                    _LOGGER.debug(
                        "Restored energy consumption: %.3f kWh",
                        self._accumulated_energy
                    )

                # Restore attributes if available
                if last_reset := last_state.attributes.get("last_reset"):
                    try:
                        if last_reset != "Never":
                            self._last_reset = datetime.fromisoformat(last_reset)
                    except ValueError:
                        _LOGGER.debug("Could not parse last_reset timestamp")
                        
                if last_calculation := last_state.attributes.get("last_calculation"):
                    try:
                        self._last_calculation_time = datetime.fromisoformat(last_calculation)
                    except ValueError:
                        _LOGGER.debug("Could not parse last_calculation timestamp")
                        
                if power_source := last_state.attributes.get("power_source"):
                    self._power_source = power_source
                    
                if last_power := last_state.attributes.get("last_power"):
                    try:
                        self._last_power = float(last_power)
                    except (TypeError, ValueError):
                        _LOGGER.debug("Could not restore last_power value")

            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Could not restore previous energy state: %s",
                    err
                )
                self._reset_energy_counter()

    def _validate_derived_power(self, va_rating: int, factor: float) -> float | None:
        """Validate derived power values."""
        try:
            power = va_rating * factor
            if 0 < power <= 10000:  # Reasonable range for UPS power
                return power
            _LOGGER.warning("Derived power %sW outside reasonable range", power)
            return None
        except (TypeError, ValueError, ZeroDivisionError) as err:
            _LOGGER.error("Error validating derived power: %s", err)
            return None

    def _validate_energy_increment(
        self,
        energy_increment: float,
        hours: float,
        avg_power: float
    ) -> bool:
        """Validate energy increment is within reasonable bounds."""
        try:
            # Check for physically impossible values
            if energy_increment < 0:
                _LOGGER.warning("Negative energy increment calculated: %f kWh", energy_increment)
                return False
                
            # Check for unreasonably large values
            # Max theoretical value: full power (10kW) for the entire period
            max_theoretical = (10 * hours)  # kWh
            if energy_increment > max_theoretical:
                _LOGGER.warning(
                    "Energy increment too large: %f kWh (max theoretical: %f kWh)",
                    energy_increment,
                    max_theoretical
                )
                return False
                
            # Check for unreasonable power implications
            implied_power = (energy_increment / hours) * 1000  # Convert back to watts
            if abs(implied_power - avg_power) > (avg_power * 0.1):  # 10% tolerance
                _LOGGER.warning(
                    "Energy increment implies unreasonable power: %f W (expected: %f W)",
                    implied_power,
                    avg_power
                )
                return False
                
            return True
            
        except (ValueError, ZeroDivisionError) as err:
            _LOGGER.error("Error validating energy increment: %s", err)
            return False

    def _get_nominal_power(self, ups_info: dict) -> float | None:
        """Get nominal power either directly or derived from model."""
        try:
            # First try direct NOMPOWER
            if "NOMPOWER" in ups_info:
                nominal_power = self._validate_ups_metric(
                    "NOMPOWER",
                    ups_info.get("NOMPOWER")
                )
                if nominal_power is not None:
                    self._last_power_value = nominal_power
                    self._power_source = "direct"
                    return nominal_power

            # Try to derive from model if no NOMPOWER
            model = ups_info.get("MODEL", "").strip().lower()
            if not model:
                return self._last_power_value

            # Try each model pattern
            for pattern, factor in UPS_MODEL_PATTERNS.items():
                if match := re.search(pattern, model):
                    va_rating = int(match.group(1))
                    nominal_power = self._validate_derived_power(va_rating, factor)
                    if nominal_power:
                        _LOGGER.debug(
                            "Derived power for model %s: %sVA * %s = %sW",
                            model,
                            va_rating,
                            factor,
                            nominal_power
                        )
                        self._last_power_value = nominal_power
                        self._power_source = "derived"
                        return nominal_power

            if self._last_power_value is not None:
                return self._last_power_value

            _LOGGER.warning(
                "Could not determine power rating for UPS model: %s",
                model
            )
            return None

        except Exception as err:
            _LOGGER.error("Error calculating nominal power: %s", err)
            return self._last_power_value

    def _get_energy_consumption(self, data: dict) -> float | None:
        """Calculate energy consumption."""
        try:
            ups_info = data.get("system_stats", {}).get("ups_info", {})
            if not ups_info:
                _LOGGER.debug("No UPS info available")
                return self._accumulated_energy

            # Get required values with validation
            nominal_power = self._get_nominal_power(ups_info)
            load_percent = self._validate_ups_metric(
                "LOADPCT",
                ups_info.get("LOADPCT")
            )

            if nominal_power is None or load_percent is None:
                _LOGGER.debug("Missing required values for energy calculation")
                return self._accumulated_energy

            # Calculate current power
            current_power = (nominal_power * load_percent) / 100.0
            current_time = datetime.now(timezone.utc)

            if self._last_power is not None and self._last_calculation_time is not None:
                hours = (current_time - self._last_calculation_time).total_seconds() / 3600

                if hours > 24:
                    _LOGGER.warning(
                        "Large time gap detected (%s hours), resetting energy counter",
                        round(hours, 2)
                    )
                    self._reset_energy_counter()
                    return 0.0
                elif hours > 1:
                    # For gaps between 1-24 hours, log a warning but continue
                    _LOGGER.warning(
                        "Time gap detected (%s hours) - energy calculation may be less accurate",
                        round(hours, 2)
                    )

                # Calculate average power over the period
                avg_power = (current_power + self._last_power) / 2
                energy_increment = (avg_power * hours) / 1000  # Convert to kWh

                # Validate the calculated increment
                if not self._validate_energy_increment(energy_increment, hours, avg_power):
                    _LOGGER.warning("Skipping invalid energy increment")
                    return self._accumulated_energy

                _LOGGER.debug(
                    "Energy calculation - Avg Power: %.2fW, Time: %.4fh, "
                    "Increment: %.4fkWh, Total: %.4fkWh",
                    avg_power,
                    hours,
                    energy_increment,
                    self._accumulated_energy + energy_increment
                )

                self._accumulated_energy += energy_increment

            # Update tracking values
            self._last_power = current_power
            self._last_calculation_time = current_time
            self._last_update = current_time
            self._error_count = 0

            return round(self._accumulated_energy, 3)

        except Exception as err:
            self._error_count += 1
            if self._error_count <= 3:
                _LOGGER.error("Error calculating UPS energy: %s", err)
            return self._accumulated_energy

    def _reset_energy_counter(self) -> None:
        """Reset the energy counter."""
        self._accumulated_energy = 0.0
        self._last_power = None
        self._last_calculation_time = None
        self._last_reset = datetime.now(timezone.utc)

    def _get_time_since_last_calculation(self) -> float | None:
        """Get time since last energy calculation in hours."""
        if self._last_calculation_time:
            return (datetime.now(timezone.utc) - self._last_calculation_time).total_seconds() / 3600
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        try:
            ups_info = (
                self.coordinator.data.get("system_stats", {})
                .get("ups_info", {})
            )
            
            # Format timestamps safely
            last_reset_str = (self._last_reset.isoformat() 
                            if self._last_reset is not None 
                            else "Never")
            last_calculation_str = (self._last_calculation_time.isoformat() 
                                if self._last_calculation_time is not None 
                                else None)

            attrs = {
                "last_reset": last_reset_str,
                "last_calculation": last_calculation_str,
                "nominal_power": f"{ups_info.get('NOMPOWER', '0')}W",
                "line_voltage": f"{ups_info.get('LINEV', '0')}V",
                "last_transfer_reason": ups_info.get('LASTXFER', 'Unknown'),
                "battery_voltage": f"{ups_info.get('BATTV', '0')}V",
                "battery_charge": f"{ups_info.get('BCHARGE', '0')}%",
                "time_on_battery": f"{ups_info.get('TONBATT', '0')}seconds",
                "power_source": self._power_source,
            }
            
            if self._last_calculation_time:
                time_since = self._get_time_since_last_calculation()
                if time_since is not None:
                    attrs["calculation_age"] = f"{time_since:.1f}h"

            # Add UPS model and power derivation info
            if model := ups_info.get("MODEL"):
                attrs["ups_model"] = model
                if self._power_source == "derived":
                    nominal_power = self._get_nominal_power(ups_info)
                    if nominal_power:
                        attrs["derived_power"] = f"{nominal_power}W"
                        attrs["power_derivation"] = "Calculated from model rating"

            if self._error_count > 0:
                attrs["error_count"] = self._error_count
                
            if self._last_power is not None:
                attrs["last_power"] = self._last_power

            return attrs

        except (KeyError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting UPS attributes: %s", err)
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        if self.coordinator.last_update_success:
            self._error_count = 0

class UnraidUPSLoadPercentage(UnraidSensorBase, UPSMetricsMixin):
    """UPS load percentage sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ups"
        )

        description = UnraidSensorEntityDescription(
            key="ups_load_percentage",
            name=f"{naming.get_entity_name('ups', 'ups')} Current Load",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:gauge",
            suggested_display_precision=1,
            value_fn=self._get_load_percentage,
        )
        super().__init__(coordinator, description)
        UPSMetricsMixin.__init__(self)

    def _get_load_percentage(self, data: dict) -> float | None:
        """Get UPS load percentage."""
        try:
            ups_info = data.get("system_stats", {}).get("ups_info", {})
            return self._validate_ups_metric(
                "LOADPCT",
                ups_info.get("LOADPCT")
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.debug("Error getting UPS load percentage: %s", err)
            return None

class UnraidUPSSensors:
    """Helper class to create all UPS sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize UPS sensors."""
        self.entities = []

        if coordinator.has_ups:
            self.entities.extend([
                UnraidUPSCurrentPowerSensor(coordinator),
                UnraidUPSEnergyConsumption(coordinator),
                UnraidUPSLoadPercentage(coordinator),
            ])