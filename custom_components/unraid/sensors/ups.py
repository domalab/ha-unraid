"""UPS-related sensors for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Final
from datetime import datetime, timezone
from dataclasses import dataclass

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import ( # type: ignore
    PERCENTAGE,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfTime,
    UnitOfEnergy,
)
from homeassistant.util import dt as dt_util # type: ignore
from homeassistant.core import callback # type: ignore

from .base import UnraidSensorBase, ValueValidationMixin
from .const import DOMAIN, UnraidSensorEntityDescription
from ..naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

# UPS metric validation ranges
UPS_METRICS: Final = {
    "NOMPOWER": {"min": 0, "max": 10000, "unit": UnitOfPower.WATT},
    "LOADPCT": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "BCHARGE": {"min": 0, "max": 100, "unit": PERCENTAGE},
    "LINEV": {"min": 0, "max": 500, "unit": UnitOfElectricPotential.VOLT},
    "BATTV": {"min": 0, "max": 60, "unit": UnitOfElectricPotential.VOLT},
    "TIMELEFT": {"min": 0, "max": 1440, "unit": UnitOfTime.MINUTES},
    "ITEMP": {"min": 0, "max": 60, "unit": "°C"},
}

@dataclass
class UPSMetric:
    """UPS metric with validation."""
    value: float
    unit: str
    timestamp: datetime = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = dt_util.now()

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
            key="ups_current_power",
            name=f"{naming.get_entity_name('ups', 'ups')} Current Power",
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

class UnraidUPSEnergyConsumption(UnraidSensorBase, UPSMetricsMixin):
    """UPS energy consumption sensor."""

    # Added power factor and model patterns
    POWER_FACTOR_ESTIMATE = 0.9  # Conservative estimate for VA to W conversion

    # Known UPS model patterns for power calculation
    MODEL_PATTERNS = {
        r'smart-ups.*?(\d{3,4})': 1.0,       # Smart-UPS models use direct VA rating
        r'back-ups.*?(\d{3,4})': 0.9,        # Back-UPS models typically 90% of VA
        r'back-ups pro.*?(\d{3,4})': 0.95,   # Back-UPS Pro models ~95% of VA
        r'smart-ups\s*x.*?(\d{3,4})': 1.0,   # Smart-UPS X series
        r'smart-ups\s*xl.*?(\d{3,4})': 1.0,  # Smart-UPS XL series
        r'smart-ups\s*rt.*?(\d{3,4})': 1.0,  # Smart-UPS RT series
        r'symmetra.*?(\d{3,4})': 1.0,        # Symmetra models
        r'sua\d{3,4}': 1.0,                  # Smart-UPS alternative model format
        r'smx\d{3,4}': 1.0,                  # Smart-UPS SMX model format
        r'smt\d{3,4}': 1.0,                  # Smart-UPS SMT model format
    }

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ups"
        )

        description = UnraidSensorEntityDescription(
            key="ups_energy_consumption",
            name=f"{naming.get_entity_name('ups', 'ups')} Energy Consumption",
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
            for pattern, factor in self.MODEL_PATTERNS.items():
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

            _LOGGER.warning("Could not determine power rating for UPS model: %s", model)
            return None

        except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError) as err:
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
            current_time = datetime.now(timezone.utc)  # Fixed timezone

            if self._last_power is not None and self._last_calculation_time is not None:
                hours = (current_time - self._last_calculation_time).total_seconds() / 3600

                if hours > 24:
                    _LOGGER.warning(
                        "Large time gap detected (%s hours), resetting energy counter",
                        round(hours, 2)
                    )
                    self._reset_energy_counter()
                    return 0.0

                # Calculate average power over the period
                avg_power = (current_power + self._last_power) / 2
                energy_increment = (avg_power * hours) / 1000  # Convert to kWh

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

            return round(self._accumulated_energy, 3)

        except (TypeError, ValueError, KeyError) as err:
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
            attrs = {
                "last_reset": self._last_reset.isoformat() if self._last_reset else "Never",
                "nominal_power": f"{ups_info.get('NOMPOWER', '0')}W",
                "line_voltage": f"{ups_info.get('LINEV', '0')}V",
                "last_transfer_reason": ups_info.get('LASTXFER', 'Unknown'),
                "battery_voltage": f"{ups_info.get('BATTV', '0')}V",
                "battery_charge": f"{ups_info.get('BCHARGE', '0')}%",
                "time_on_battery": f"{ups_info.get('TONBATT', '0')}seconds",
                "power_source": self._power_source,
                "calculation_age": (
                    f"{self._get_time_since_last_calculation():.1f}h"
                    if self._last_calculation_time else "unknown"
                )
            }

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
            name=f"{naming.get_entity_name('ups', 'ups')} Load Percentage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:flash",
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
