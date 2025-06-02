"""Network-related sensors for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Any, Literal
from dataclasses import dataclass

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

from  ..api.network_operations import NetworkRateSmoothingMixin

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

class UnraidNetworkSensor(UnraidSensorBase, NetworkRateSmoothingMixin):
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
            name=f"{interface} {direction.capitalize()}",
            device_class=SensorDeviceClass.DATA_RATE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:arrow-down" if direction == "inbound" else "mdi:arrow-up",
            suggested_display_precision=2,
            value_fn=self._get_network_rate,
            available_fn=self._is_interface_available,
        )

        # Initialize both parent classes properly
        UnraidSensorBase.__init__(self, coordinator, description)
        NetworkRateSmoothingMixin.__init__(self)

        _LOGGER.debug(
            "UnraidNetworkSensor initialized for %s %s. Has smoothing methods: rx=%s, tx=%s",
            interface,
            direction,
            hasattr(self, 'calculate_rx_rate'),
            hasattr(self, 'calculate_tx_rate')
        )

    def _get_unit(self, bits_per_sec: float) -> NetworkSpeedUnit:
        """Get the most appropriate unit for a network speed."""
        old_unit = getattr(self, '_unit', NetworkSpeedUnit(1, "bit/s"))

        for unit in reversed(NETWORK_UNITS):
            if bits_per_sec >= unit.multiplier:
                _LOGGER.debug(
                    "Unit conversion - rate: %.2f bits/s, selected unit: %s (multiplier: %d), "
                    "converted value: %.2f %s (changed from %s)",
                    bits_per_sec,
                    unit.symbol,
                    unit.multiplier,
                    bits_per_sec / unit.multiplier,
                    unit.symbol,
                    old_unit.symbol
                )
                return unit

        _LOGGER.debug(
            "Using minimum unit - rate: %.2f bits/s, unit: %s",
            bits_per_sec,
            NETWORK_UNITS[0].symbol
        )
        return NETWORK_UNITS[0]

    def _get_network_rate(self, data: dict) -> float | None:
        """Calculate current network rate with smoothing."""
        try:
            network_stats = data.get("system_stats", {}).get("network_stats", {})
            if self._interface not in network_stats:
                _LOGGER.debug(
                    "No stats found for interface %s. Available interfaces: %s",
                    self._interface,
                    list(network_stats.keys())
                )
                return 0.0

            stats = network_stats[self._interface]
            current_bytes = (
                stats.get("rx_bytes", 0)
                if self._direction == "inbound"
                else stats.get("tx_bytes", 0)
            )

            _LOGGER.debug(
                "%s %s: Processing bytes=%d",
                self._interface,
                self._direction,
                current_bytes
            )

            rate = (
                self.calculate_rx_rate(current_bytes)
                if self._direction == "inbound"
                else self.calculate_tx_rate(current_bytes)
            )

            _LOGGER.debug(
                "%s %s: Raw rate=%.2f bits/s",
                self._interface,
                self._direction,
                rate
            )

            if rate > 0:
                self._unit = self._get_unit(rate)
                converted_rate = round(rate / self._unit.multiplier, 2)

                _LOGGER.debug(
                    "%s %s: Final conversion %.2f bits/s → %.2f %s",
                    self._interface,
                    self._direction,
                    rate,
                    converted_rate,
                    self._unit.symbol
                )

                return converted_rate

            return 0.0

        except Exception as err:
            _LOGGER.error(
                "Error calculating rate for %s %s: %s",
                self._interface,
                self._direction,
                err,
                exc_info=True
            )
            return 0.0

    def _is_interface_available(self, data: dict) -> bool:
        """Check if network interface is available."""
        try:
            network_stats = data.get("system_stats", {}).get("network_stats", {})

            # Use the same normalization as in network_operations
            normalized_interface = self._interface.lower()
            if '.' in normalized_interface or '@' in normalized_interface:
                if '@' in normalized_interface:
                    normalized_interface = normalized_interface.split('@')[0]
                normalized_interface = normalized_interface.replace('o', '0')

            return (
                normalized_interface in network_stats
                and network_stats[normalized_interface].get("connected", False)
                and bool(re.match(VALID_INTERFACE_PATTERN, normalized_interface))
                and normalized_interface not in EXCLUDED_INTERFACES
            )
        except Exception as err:
            _LOGGER.error(
                "Error checking interface availability: %s (interface=%s)",
                err,
                self._interface
            )
            return False

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return self._unit.symbol

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional network interface attributes with user-friendly formatting."""
        try:
            stats = (
                self.coordinator.data.get("system_stats", {})
                .get("network_stats", {})
                .get(self._interface, {})
            )

            attrs = {
                "interface_name": self._interface,
                "connection_status": "Connected" if stats.get("connected", False) else "Disconnected",
                "link_detected": "Yes" if stats.get("link_detected", False) else "No",
                "mac_address": stats.get("mac_address", "Unknown"),
                "last_update": dt_util.now().isoformat(),
            }

            # Add interface details with user-friendly names
            if info := stats.get("interface_info"):
                attrs["interface_details"] = info

            # Add error counts with user-friendly formatting
            if "rx_errors" in stats or "tx_errors" in stats:
                rx_errors = stats.get("rx_errors", 0)
                tx_errors = stats.get("tx_errors", 0)
                rx_dropped = stats.get("rx_dropped", 0)
                tx_dropped = stats.get("tx_dropped", 0)

                attrs.update({
                    "receive_errors": f"{rx_errors:,}" if rx_errors > 0 else "None",
                    "transmit_errors": f"{tx_errors:,}" if tx_errors > 0 else "None",
                    "receive_dropped": f"{rx_dropped:,}" if rx_dropped > 0 else "None",
                    "transmit_dropped": f"{tx_dropped:,}" if tx_dropped > 0 else "None",
                })

            # Add speed information with proper formatting
            if speed := stats.get("speed"):
                try:
                    speed_val = float(speed)
                    if speed_val >= 1000:
                        attrs["link_speed"] = f"{speed_val / 1000:.1f} Gbps"
                    else:
                        attrs["link_speed"] = f"{speed_val:.0f} Mbps"
                except (ValueError, TypeError):
                    attrs["link_speed"] = f"{speed} Mbps"
            else:
                attrs["link_speed"] = "Unknown"

            # Add duplex mode with user-friendly formatting
            if duplex := stats.get("duplex"):
                attrs["duplex_mode"] = duplex.title() if duplex else "Unknown"
            else:
                attrs["duplex_mode"] = "Unknown"

            # Add total bytes transferred with formatting
            if self._direction == "inbound":
                total_bytes = stats.get("rx_bytes", 0)
                attrs["total_data_received"] = self._format_bytes(total_bytes)
            else:
                total_bytes = stats.get("tx_bytes", 0)
                attrs["total_data_transmitted"] = self._format_bytes(total_bytes)

            return attrs

        except (TypeError, KeyError, AttributeError) as err:
            _LOGGER.debug(
                "Error getting attributes for interface %s: %s",
                self._interface,
                err
            )
            return {}

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes into human-readable format."""
        if bytes_value <= 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        value = float(bytes_value)

        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{int(value)} {units[unit_index]}"
        else:
            return f"{value:.2f} {units[unit_index]}"

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
