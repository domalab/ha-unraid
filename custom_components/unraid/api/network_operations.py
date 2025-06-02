"""Network operations for Unraid."""
from __future__ import annotations

from collections import deque
import logging
import asyncio
from typing import Deque, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

from .error_handling import with_error_handling, safe_parse

_LOGGER = logging.getLogger(__name__)

@dataclass
class SmoothingStats:
    """Network rate smoothing statistics."""
    # Recent measurements for EMA calculation
    history: Deque[tuple[datetime, float]] = field(
        default_factory=lambda: deque(maxlen=30)  # 1-minute history at 2s intervals
    )
    ema_value: float = 0.0  # Current EMA value
    last_raw_rate: float = 0.0  # Last calculated raw rate
    last_update: Optional[datetime] = None

@dataclass
class NetworkStats:
    """Network statistics data class."""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_speed: float = 0.0
    tx_speed: float = 0.0
    last_update: Optional[datetime] = None

class NetworkRateSmoothingMixin:
    """Mixin for enhanced network rate smoothing."""

    def __init__(self) -> None:
        """Initialize smoothing mixin."""
        self._rx_smoothing = SmoothingStats()
        self._tx_smoothing = SmoothingStats()
        # Adjustable parameters
        self._ema_alpha = 0.4  # Increased for faster response
        self._spike_threshold = 5.0  # Increased to allow more variation
        self._min_rate = 0.001  # Lowered to catch smaller traffic
        self._min_time_diff = 1.0  # Minimum seconds between updates

    def _smooth_rate(
        self,
        current_bytes: int,
        smoothing_stats: SmoothingStats,
        current_time: Optional[datetime] = None
    ) -> float:
        """Calculate smoothed network rate using EMA."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        if smoothing_stats.last_update is None:
            _LOGGER.debug(
                "First measurement - storing bytes=%d at %s",
                current_bytes,
                current_time.isoformat()
            )
            smoothing_stats.last_raw_rate = current_bytes
            smoothing_stats.last_update = current_time
            return 0.0

        try:
            time_diff = (current_time - smoothing_stats.last_update).total_seconds()
            if time_diff < self._min_time_diff:
                _LOGGER.debug(
                    "Update too frequent (%.3fs < %.3fs) - keeping previous rate: %.2f bits/s",
                    time_diff,
                    self._min_time_diff,
                    smoothing_stats.ema_value
                )
                return smoothing_stats.ema_value

            byte_diff = current_bytes - smoothing_stats.last_raw_rate
            current_raw_rate = (byte_diff * 8) / time_diff  # bits/second

            _LOGGER.debug(
                "Rate calculation - bytes: %d → %d (%+d), time: %.3fs, raw_rate: %.2f bits/s",
                smoothing_stats.last_raw_rate,
                current_bytes,
                byte_diff,
                time_diff,
                current_raw_rate
            )

            # Handle counter overflow or reset
            if byte_diff < 0:
                _LOGGER.debug(
                    "Counter reset detected - previous: %d, current: %d",
                    smoothing_stats.last_raw_rate,
                    current_bytes
                )
                current_raw_rate = (current_bytes * 8) / time_diff

            # Update EMA and history
            if current_raw_rate >= self._min_rate:
                previous_ema = smoothing_stats.ema_value
                smoothing_stats.ema_value = (
                    self._ema_alpha * current_raw_rate +
                    (1 - self._ema_alpha) * previous_ema
                )
                _LOGGER.debug(
                    "Updated EMA: %.2f → %.2f bits/s (alpha=%.2f)",
                    previous_ema,
                    smoothing_stats.ema_value,
                    self._ema_alpha
                )
            else:
                previous_ema = smoothing_stats.ema_value
                smoothing_stats.ema_value *= (1 - self._ema_alpha)
                _LOGGER.debug(
                    "Rate below minimum (%.3f < %.3f) - decaying: %.2f → %.2f bits/s",
                    current_raw_rate,
                    self._min_rate,
                    previous_ema,
                    smoothing_stats.ema_value
                )

            smoothing_stats.history.append((current_time, current_raw_rate))
            smoothing_stats.last_raw_rate = current_bytes
            smoothing_stats.last_update = current_time

            return max(smoothing_stats.ema_value, 0.0)

        except Exception as err:
            _LOGGER.error(
                "Rate calculation error: %s (bytes=%d, last_bytes=%d)",
                err,
                current_bytes,
                smoothing_stats.last_raw_rate,
                exc_info=True
            )
            return smoothing_stats.ema_value

    def calculate_rx_rate(self, current_bytes: int) -> float:
        """Calculate smoothed RX rate."""
        return self._smooth_rate(current_bytes, self._rx_smoothing)

    def calculate_tx_rate(self, current_bytes: int) -> float:
        """Calculate smoothed TX rate."""
        return self._smooth_rate(current_bytes, self._tx_smoothing)

    @property
    def smoothing_window(self) -> float:
        """Get effective smoothing window in seconds."""
        return 1.0 / self._ema_alpha  # Approximate window size

class NetworkOperationsMixin(NetworkRateSmoothingMixin):
    """Mixin for network-related operations."""

    def __init__(self) -> None:
        """Initialize network operations."""
        super().__init__()
        self._network_lock = asyncio.Lock()
        self._network_stats = {}
        self._cached_network_stats = {}
        self._last_network_update = None
        self._max_retries = 2
        self._retry_delay = 1.0  # seconds

    async def _execute_with_retry(self, command: str):
        """Execute command with retry mechanism for resilience."""
        retries = 0
        while retries <= self._max_retries:
            try:
                result = await self.execute_command(command)
                return result
            except Exception as err:
                retries += 1
                if retries > self._max_retries:
                    # Provide more specific error context for network operations
                    if "cat /sys/class/net" in command:
                        _LOGGER.error(
                            "Network interface statistics unavailable after %d retries. "
                            "This may indicate the interface is down or the system is under high load. "
                            "Command: %s, Error: %s",
                            self._max_retries,
                            command[:50] + "..." if len(command) > 50 else command,
                            str(err)
                        )
                    else:
                        _LOGGER.error(
                            "Network command failed after %d retries: %s, Error: %s",
                            self._max_retries,
                            command[:50] + "..." if len(command) > 50 else command,
                            str(err)
                        )
                    raise

                _LOGGER.debug(
                    "Retrying network command (attempt %d/%d): %s",
                    retries,
                    self._max_retries + 1,
                    command[:50] + "..." if len(command) > 50 else command
                )
                await asyncio.sleep(self._retry_delay)

    @with_error_handling(fallback_return={})
    async def get_network_stats(self) -> Dict[str, Any]:
        """Fetch network statistics using an optimized batched command.

        This implementation collects all network interface data in a single SSH command,
        including additional metadata like MAC addresses and interface types.
        It also implements caching to avoid unnecessary SSH calls for static data.
        """
        # Check if we have cached data that's still valid
        current_time = datetime.now(timezone.utc)
        if self._last_network_update and (current_time - self._last_network_update).total_seconds() < 1.0:
            # Return cached data for very frequent calls (less than 1 second apart)
            _LOGGER.debug("Using cached network stats (age: %.2fs)",
                         (current_time - self._last_network_update).total_seconds())
            return self._cached_network_stats

        async with self._network_lock:
            # Use a single command to collect all network interface data with additional metadata
            # Filter out virtual interfaces (veth*, vnet*) and only include physical interfaces and bridges
            _LOGGER.debug("Collecting network interface data with optimized batched command")
            cmd = (
                "echo '===INTERFACES==='; "
                "for iface in $(ls -1 /sys/class/net/ | grep -v -E '^(lo|bond|tun|tap|docker|veth|vnet)'); do "
                "  rx=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null || echo 0); "
                "  tx=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null || echo 0); "
                "  speed=$(cat /sys/class/net/$iface/speed 2>/dev/null || echo unknown); "
                "  duplex=$(cat /sys/class/net/$iface/duplex 2>/dev/null || echo unknown); "
                "  carrier=$(cat /sys/class/net/$iface/carrier 2>/dev/null || echo 0); "
                "  mac=$(cat /sys/class/net/$iface/address 2>/dev/null || echo unknown); "
                "  mtu=$(cat /sys/class/net/$iface/mtu 2>/dev/null || echo 0); "
                "  operstate=$(cat /sys/class/net/$iface/operstate 2>/dev/null || echo unknown); "
                "  echo \"$iface|$rx|$tx|$speed|$duplex|$carrier|$mac|$mtu|$operstate\"; "
                "done; "
                "echo '===BRIDGES==='; "
                "for iface in $(ls -1 /sys/class/net/ | grep -E '^br'); do "
                "  rx=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null || echo 0); "
                "  tx=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null || echo 0); "
                "  speed=$(cat /sys/class/net/$iface/speed 2>/dev/null || echo unknown); "
                "  duplex=$(cat /sys/class/net/$iface/duplex 2>/dev/null || echo unknown); "
                "  carrier=$(cat /sys/class/net/$iface/carrier 2>/dev/null || echo 0); "
                "  mac=$(cat /sys/class/net/$iface/address 2>/dev/null || echo unknown); "
                "  mtu=$(cat /sys/class/net/$iface/mtu 2>/dev/null || echo 0); "
                "  operstate=$(cat /sys/class/net/$iface/operstate 2>/dev/null || echo unknown); "
                "  echo \"$iface|$rx|$tx|$speed|$duplex|$carrier|$mac|$mtu|$operstate\"; "
                "done"
            )
            result = await self.execute_command(cmd)

            if result.exit_status != 0:
                _LOGGER.error("Network stats command failed with exit status %d", result.exit_status)
                return {}

            # Process the results
            network_stats = {}
            current_time = datetime.now(timezone.utc)
            section = None

            for line in result.stdout.splitlines():
                # Check for section markers
                if line == "===INTERFACES===":
                    section = "interfaces"
                    continue
                elif line == "===BRIDGES===":
                    section = "bridges"
                    continue

                # Skip empty lines
                if not line.strip():
                    continue

                # Process interface data
                parts = line.split("|")
                if len(parts) == 9:  # We now have 9 fields with the additional metadata
                    try:
                        interface, rx, tx, speed, duplex, carrier, mac, mtu, operstate = parts
                        rx_bytes = safe_parse(int, rx, default=0,
                                            error_msg=f"Invalid rx_bytes for {interface}: {rx}")
                        tx_bytes = safe_parse(int, tx, default=0,
                                            error_msg=f"Invalid tx_bytes for {interface}: {tx}")
                        link_detected = carrier == "1"
                        mtu_value = safe_parse(int, mtu, default=0,
                                             error_msg=f"Invalid MTU for {interface}: {mtu}")

                        # Create enhanced stats dictionary with additional metadata
                        stats = {
                            "rx_bytes": rx_bytes,
                            "tx_bytes": tx_bytes,
                            "speed": speed,
                            "duplex": duplex,
                            "link_detected": link_detected,
                            "connected": link_detected,
                            "mac_address": mac if mac != "unknown" else None,
                            "mtu": mtu_value,
                            "operstate": operstate,
                            "interface_type": "bridge" if section == "bridges" else "physical"
                        }

                        # Add link speed in a standardized format if available
                        if speed != "unknown":
                            try:
                                speed_value = int(speed)
                                stats["link_speed"] = f"{speed_value} Mbps"
                            except ValueError:
                                stats["link_speed"] = speed

                        # Calculate rates if we have previous data
                        if interface in self._network_stats:
                            # Calculate time delta for rate calculation
                            time_delta = (current_time - self._network_stats[interface].last_update).total_seconds()

                            # Only calculate rates if enough time has passed (avoid division by zero)
                            if time_delta >= 0.1:  # At least 100ms between updates
                                rx_delta = rx_bytes - self._network_stats[interface].rx_bytes
                                tx_delta = tx_bytes - self._network_stats[interface].tx_bytes

                                # Calculate bits per second (multiply by 8 to convert bytes to bits)
                                rx_rate = (rx_delta * 8) / time_delta
                                tx_rate = (tx_delta * 8) / time_delta

                                # Apply smoothing if previous rates exist
                                if hasattr(self, f"_last_rx_rate_{interface}") and hasattr(self, f"_last_tx_rate_{interface}"):
                                    last_rx_rate = getattr(self, f"_last_rx_rate_{interface}")
                                    last_tx_rate = getattr(self, f"_last_tx_rate_{interface}")

                                    # Apply exponential smoothing (alpha=0.3)
                                    rx_rate = (0.3 * rx_rate) + (0.7 * last_rx_rate)
                                    tx_rate = (0.3 * tx_rate) + (0.7 * last_tx_rate)

                                # Store the smoothed rates
                                setattr(self, f"_last_rx_rate_{interface}", rx_rate)
                                setattr(self, f"_last_tx_rate_{interface}", tx_rate)

                                # Add rates to stats
                                stats["rx_speed"] = rx_rate
                                stats["tx_speed"] = tx_rate
                            else:
                                # Update too frequent, keep previous rates if available
                                _LOGGER.debug("Update too frequent (%.3fs < 1.000s) - keeping previous rate: %.2f bits/s",
                                             time_delta, getattr(self, f"_last_rx_rate_{interface}", 0.0))
                                if hasattr(self, f"_last_rx_rate_{interface}"):
                                    stats["rx_speed"] = getattr(self, f"_last_rx_rate_{interface}")
                                    stats["tx_speed"] = getattr(self, f"_last_tx_rate_{interface}")
                                else:
                                    stats["rx_speed"] = 0.0
                                    stats["tx_speed"] = 0.0

                        # Store current stats for next update
                        self._network_stats[interface] = NetworkStats(
                            rx_bytes=rx_bytes,
                            tx_bytes=tx_bytes,
                            last_update=current_time
                        )

                        network_stats[interface] = stats
                    except ValueError as e:
                        _LOGGER.warning("Error parsing network stats for %s: %s", interface, e)
                elif len(parts) == 6:  # Handle old format for backward compatibility
                    try:
                        interface, rx, tx, speed, duplex, carrier = parts
                        rx_bytes = safe_parse(int, rx, default=0,
                                            error_msg=f"Invalid rx_bytes for {interface}: {rx}")
                        tx_bytes = safe_parse(int, tx, default=0,
                                            error_msg=f"Invalid tx_bytes for {interface}: {tx}")
                        link_detected = carrier == "1"

                        stats = {
                            "rx_bytes": rx_bytes,
                            "tx_bytes": tx_bytes,
                            "speed": speed,
                            "duplex": duplex,
                            "link_detected": link_detected,
                            "connected": link_detected
                        }

                        # Calculate rates if we have previous data
                        if interface in self._network_stats:
                            rates = await self._calculate_rates(
                                interface,
                                stats,
                                current_time
                            )
                            stats.update(rates)

                        # Store current stats
                        self._network_stats[interface] = NetworkStats(
                            rx_bytes=rx_bytes,
                            tx_bytes=tx_bytes,
                            last_update=current_time
                        )

                        network_stats[interface] = stats
                    except ValueError as e:
                        _LOGGER.warning("Error parsing network stats for %s: %s", interface, e)

            # Cache the results
            self._cached_network_stats = network_stats
            self._last_network_update = current_time
            return network_stats

    async def _get_network_stats_original(self) -> Dict[str, Any]:
        """Original implementation of network stats collection as fallback."""
        try:
            # Get active interfaces
            interfaces = await self._get_active_interfaces()

            # Gather stats for all interfaces concurrently
            tasks = [
                self._get_interface_stats(interface)
                for interface in interfaces
            ]

            # Execute all tasks concurrently
            stats_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            network_stats = {}
            current_time = datetime.now(timezone.utc)

            for interface, stats in zip(interfaces, stats_results):
                if isinstance(stats, Exception):
                    _LOGGER.error(
                        "Error getting stats for interface %s: %s",
                        interface,
                        stats
                    )
                    continue

                # Calculate rates if we have previous data
                if interface in self._network_stats:
                    rates = await self._calculate_rates(
                        interface,
                        stats,
                        current_time
                    )
                    stats.update(rates)

                # Store current stats
                self._network_stats[interface] = NetworkStats(
                    rx_bytes=stats["rx_bytes"],
                    tx_bytes=stats["tx_bytes"],
                    last_update=current_time
                )

                network_stats[interface] = stats

            self._last_network_update = current_time
            return network_stats

        except Exception as err:
            _LOGGER.error("Error in original network stats method: %s", err)
            return {}

    async def _get_active_interfaces(self) -> list[str]:
        """Get list of active network interfaces.

        Only includes physical interfaces (eth*) and bridge interfaces (br*) if configured.
        Excludes virtual interfaces (veth*, vnet*) and other non-physical interfaces.
        """
        try:
            # Get physical interfaces (eth*) and bridge interfaces (br*)
            result = await self.execute_command(
                "ip -br link show | grep -E '^(eth|br)' | grep -v -E 'veth|vnet' | awk '{print $1}'"
            )

            if result.exit_status != 0:
                return []

            return [
                interface.strip()
                for interface in result.stdout.splitlines()
                if interface.strip()
            ]

        except Exception as err:
            _LOGGER.error("Error getting active interfaces: %s", err)
            return []

    async def _get_interface_stats(self, interface: str) -> Dict[str, Any]:
        """Get statistics for a specific interface."""
        try:
            original_interface = interface
            normalized_interface = interface.lower()

            # Only apply VLAN-specific normalization if it looks like a VLAN interface
            if '.' in normalized_interface or '@' in normalized_interface:
                if '@' in normalized_interface:
                    normalized_interface = normalized_interface.split('@')[0]
                normalized_interface = normalized_interface.replace('o', '0')

            _LOGGER.debug(
                "Processing interface: %s (normalized: %s)",
                original_interface,
                normalized_interface
            )

            if not await self._interface_exists(normalized_interface):
                _LOGGER.debug(
                    "Interface not found: %s (normalized from: %s)",
                    normalized_interface,
                    original_interface
                )
                raise ValueError(f"Interface {normalized_interface} does not exist")

            # Get traffic stats separately with improved error handling
            rx_cmd = f"cat /sys/class/net/{normalized_interface}/statistics/rx_bytes 2>/dev/null || echo 0"
            tx_cmd = f"cat /sys/class/net/{normalized_interface}/statistics/tx_bytes 2>/dev/null || echo 0"

            # Execute commands with retry mechanism
            rx_result = await self._execute_with_retry(rx_cmd)
            tx_result = await self._execute_with_retry(tx_cmd)

            # Parse values with fallback to 0 for invalid results
            try:
                rx_bytes = int(rx_result.stdout.strip())
            except (ValueError, AttributeError):
                _LOGGER.warning("Could not parse RX bytes for %s, using 0", normalized_interface)
                rx_bytes = 0

            try:
                tx_bytes = int(tx_result.stdout.strip())
            except (ValueError, AttributeError):
                _LOGGER.warning("Could not parse TX bytes for %s, using 0", normalized_interface)
                tx_bytes = 0

            # Get interface info concurrently
            info = await self._get_interface_info(normalized_interface)

            return {
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "connected": True,
                **info
            }

        except Exception as err:
            _LOGGER.error(
                "Error getting interface stats: %s (interface=%s)",
                err,
                interface
            )
            raise

    async def _interface_exists(self, interface: str) -> bool:
        """Check if network interface exists."""
        try:
            cmd = f"test -d /sys/class/net/{interface}"
            result = await self.execute_command(cmd)
            exists = result.exit_status == 0

            _LOGGER.debug(
                "Interface existence check: %s (exists=%s)",
                interface,
                exists
            )

            return exists
        except Exception as err:
            _LOGGER.error(
                "Error checking interface existence: %s (interface=%s)",
                err,
                interface
            )
            return False

    async def _calculate_rates(
        self,
        interface: str,
        current_stats: Dict[str, Any],
        current_time: datetime
    ) -> Dict[str, float]:
        """Calculate network rates asynchronously."""
        try:
            # Calculate smoothed rates using the enhanced mixin
            rx_rate = self.calculate_rx_rate(current_stats["rx_bytes"])
            tx_rate = self.calculate_tx_rate(current_stats["tx_bytes"])

            # Store smoothed rates in the stats
            current_stats["rx_speed"] = rx_rate
            current_stats["tx_speed"] = tx_rate

            return {
                "rx_speed": rx_rate,
                "tx_speed": tx_rate
            }

        except Exception as err:
            _LOGGER.error(
                "Error calculating rates for interface %s: %s",
                interface,
                err
            )
            return {"rx_speed": 0.0, "tx_speed": 0.0}

    async def _get_interface_info(self, interface: str) -> Dict[str, Any]:
        """Get detailed interface information asynchronously."""
        try:
            # Run ethtool commands concurrently
            speed_cmd = f"ethtool {interface} 2>/dev/null | grep Speed"
            duplex_cmd = f"ethtool {interface} 2>/dev/null | grep Duplex"
            carrier_cmd = f"cat /sys/class/net/{interface}/carrier 2>/dev/null"

            speed_result, duplex_result, carrier_result = await asyncio.gather(
                self.execute_command(speed_cmd),
                self.execute_command(duplex_cmd),
                self.execute_command(carrier_cmd),
                return_exceptions=True
            )

            info = {
                "speed": "unknown",
                "duplex": "unknown",
                "link_detected": False
            }

            # Process speed
            if not isinstance(speed_result, Exception) and speed_result.exit_status == 0:
                if match := speed_result.stdout.strip():
                    info["speed"] = match.split(":")[1].strip()

            # Process duplex
            if not isinstance(duplex_result, Exception) and duplex_result.exit_status == 0:
                if match := duplex_result.stdout.strip():
                    info["duplex"] = match.split(":")[1].strip()

            # Process carrier status
            if not isinstance(carrier_result, Exception) and carrier_result.exit_status == 0:
                info["link_detected"] = carrier_result.stdout.strip() == "1"

            return info

        except Exception as err:
            _LOGGER.error("Error getting interface info: %s", err)
            return {
                "speed": "unknown",
                "duplex": "unknown",
                "link_detected": False
            }