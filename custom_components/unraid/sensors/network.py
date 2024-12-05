"""Network-related sensors for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Any, Literal
from dataclasses import dataclass
from datetime import datetime, timezone

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidSensorBase
from .const import (
    UnraidSensorEntityDescription,
    VALID_INTERFACE_PATTERN,
    EXCLUDED_INTERFACES,
)

_LOGGER = logging.getLogger(__name__)

@dataclass
class NetworkSpeedUnit:
    """Network unit representation."""
    multiplier: int
    symbol: str

NETWORK_UNITS = [
    NetworkSpeedUnit(1, "bit/s"),
    NetworkSpeedUnit(1000, "kbit/s"),
    NetworkSpeedUnit(1000000, "Mbit/s"),
    NetworkSpeedUnit(1000000000, "Gbit/s"),
]

class NetworkRatesMixin:
    """Mixin for network rate calculations."""

    def __init__(self) -> None:
        """Initialize the mixin."""
        self._last_bytes: int | None = None
        self._last_update: datetime | None = None
        self._current_rate: float = 0.0

    def _calculate_rate(
        self,
        current_bytes: int,
        current_time: datetime | None = None
    ) -> float:
        """Calculate network transfer rate."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        if self._last_bytes is None or self._last_update is None:
            self._last_bytes = current_bytes
            self._last_update = current_time
            return 0.0

        try:
            time_diff = (current_time - self._last_update).total_seconds()
            if time_diff <= 0:
                return self._current_rate

            byte_diff = current_bytes - self._last_bytes

            # Handle counter overflow
            if byte_diff < 0:
                _LOGGER.debug("Network counter overflow detected")
                byte_diff = current_bytes

            rate = (byte_diff / time_diff) * 8  # Convert to bits/second

            self._last_bytes = current_bytes
            self._last_update = current_time
            self._current_rate = rate

            return rate

        except (ArithmeticError, TypeError, ValueError) as err:
            _LOGGER.debug("Error calculating network rate: %s", err)
            return self._current_rate

    def _get_unit(self, bits_per_sec: float) -> NetworkSpeedUnit:
        """Get the most appropriate unit for a network speed."""
        for unit in reversed(NETWORK_UNITS):
            if bits_per_sec >= unit.multiplier:
                return unit
        return NETWORK_UNITS[0]

class UnraidNetworkSensor(UnraidSensorBase, NetworkRatesMixin):
    """Network interface sensor for Unraid."""

    def __init__(
        self,
        coordinator,
        interface: str,
        direction: Literal["inbound", "outbound"]
    ) -> None:
        """Initialize the sensor."""
        self._interface = interface
        self._direction = direction
        self._unit = NetworkSpeedUnit(1, "bit/s")  # Start with lowest unit

        description = UnraidSensorEntityDescription(
            key=f"network_{interface}_{direction}",
            name=f"Network {interface} {direction.capitalize()}",
            device_class=SensorDeviceClass.DATA_RATE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:arrow-down" if direction == "inbound" else "mdi:arrow-up",
            suggested_display_precision=2,
            value_fn=self._get_network_rate,
            available_fn=self._is_interface_available,
        )

        super().__init__(coordinator, description)
        NetworkRatesMixin.__init__(self)

    def _get_network_rate(self, data: dict) -> float | None:
        """Calculate current network rate."""
        try:
            network_stats = data.get("system_stats", {}).get("network_stats", {})
            if self._interface not in network_stats:
                return None

            stats = network_stats[self._interface]
            current_bytes = (
                stats.get("rx_bytes", 0)
                if self._direction == "inbound"
                else stats.get("tx_bytes", 0)
            )

            rate = self._calculate_rate(current_bytes)
            if rate is not None:
                # Update unit based on current rate
                self._unit = self._get_unit(rate)
                # Convert to chosen unit
                return round(rate / self._unit.multiplier, 2)

            return None

        except (TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug(
                "Error getting network rate for %s %s: %s",
                self._interface,
                self._direction,
                err
            )
            return None

    def _is_interface_available(self, data: dict) -> bool:
        """Check if network interface is available."""
        network_stats = data.get("system_stats", {}).get("network_stats", {})
        return (
            self._interface in network_stats
            and network_stats[self._interface].get("connected", False)
            and bool(re.match(VALID_INTERFACE_PATTERN, self._interface))
            and self._interface not in EXCLUDED_INTERFACES
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self._unit.symbol

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional network interface attributes."""
        try:
            stats = (
                self.coordinator.data.get("system_stats", {})
                .get("network_stats", {})
                .get(self._interface, {})
            )

            attrs = {
                "interface": self._interface,
                "connected": stats.get("connected", False),
                "link_detected": stats.get("link_detected", False),
                "mac_address": stats.get("mac_address", "unknown"),
                "last_update": dt_util.now().isoformat(),
            }

            # Add interface details
            if info := stats.get("interface_info"):
                attrs["interface_info"] = info

            # Add error counts if available
            if "rx_errors" in stats or "tx_errors" in stats:
                attrs.update({
                    "rx_errors": stats.get("rx_errors", 0),
                    "tx_errors": stats.get("tx_errors", 0),
                    "rx_dropped": stats.get("rx_dropped", 0),
                    "tx_dropped": stats.get("tx_dropped", 0),
                })

            # Add speed information
            if speed := stats.get("speed"):
                attrs["link_speed"] = f"{speed} Mbps"

            # Add duplex mode
            if duplex := stats.get("duplex"):
                attrs["duplex_mode"] = duplex

            return attrs

        except (TypeError, KeyError, AttributeError) as err:
            _LOGGER.debug(
                "Error getting attributes for interface %s: %s",
                self._interface,
                err
            )
            return {}

class UnraidNetworkSensors:
    """Helper class to create all network sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize network sensors."""
        self.entities = []

        # Get network stats
        network_stats = (
            coordinator.data.get("system_stats", {})
            .get("network_stats", {})
        )

        # Create sensors for active interfaces
        for interface in network_stats:
            if (
                network_stats[interface].get("connected", False)
                and bool(re.match(VALID_INTERFACE_PATTERN, interface))
                and interface not in EXCLUDED_INTERFACES
            ):
                # Add inbound sensor
                self.entities.append(
                    UnraidNetworkSensor(coordinator, interface, "inbound")
                )
                # Add outbound sensor
                self.entities.append(
                    UnraidNetworkSensor(coordinator, interface, "outbound")
                )
