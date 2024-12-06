"""Network operations for Unraid."""
from __future__ import annotations

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

@dataclass
class NetworkStats:
    """Network statistics data class."""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_speed: float = 0.0
    tx_speed: float = 0.0
    last_update: Optional[datetime] = None

class NetworkOperationsMixin:
    """Mixin for network-related operations."""

    def __init__(self) -> None:
        """Initialize network operations."""
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
            prev_stats = self._network_stats.get(interface)
            if not prev_stats or not prev_stats.last_update:
                return {"rx_speed": 0.0, "tx_speed": 0.0}

            time_diff = (current_time - prev_stats.last_update).total_seconds()
            if time_diff <= 0:
                return {"rx_speed": prev_stats.rx_speed, "tx_speed": prev_stats.tx_speed}

            # Calculate rates with overflow protection
            rx_diff = current_stats["rx_bytes"] - prev_stats.rx_bytes
            tx_diff = current_stats["tx_bytes"] - prev_stats.tx_bytes

            # Handle counter overflow
            if rx_diff < 0:
                rx_diff = current_stats["rx_bytes"]
            if tx_diff < 0:
                tx_diff = current_stats["tx_bytes"]

            return {
                "rx_speed": rx_diff / time_diff,
                "tx_speed": tx_diff / time_diff
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