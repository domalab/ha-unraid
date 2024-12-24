"""Network operations for Unraid."""
from __future__ import annotations

from collections import deque
import logging
import asyncio
from typing import Deque, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

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
        self._last_network_update = None

    async def get_network_stats(self) -> Dict[str, Any]:
        """Fetch network statistics asynchronously."""
        try:
            async with self._network_lock:
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
            _LOGGER.error("Error getting network stats: %s", err)
            return {}

    async def _get_active_interfaces(self) -> list[str]:
        """Get list of active network interfaces."""
        try:
            result = await self.execute_command(
                "ip -br link show | grep -E '^(eth|bond)' | awk '{print $1}'"
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
            # Get traffic stats
            stats_cmd = (
                f"cat /sys/class/net/{interface}/statistics/rx_bytes "
                f"/sys/class/net/{interface}/statistics/tx_bytes"
            )
            stats_result = await self.execute_command(stats_cmd)
            
            if stats_result.exit_status != 0:
                raise ValueError(f"Failed to get stats for {interface}")
                
            rx_bytes, tx_bytes = map(int, stats_result.stdout.splitlines())
            
            # Get interface info concurrently
            info = await self._get_interface_info(interface)
            
            return {
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "connected": True,
                **info
            }
            
        except Exception as err:
            _LOGGER.error("Error getting interface stats: %s", err)
            raise

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
        
