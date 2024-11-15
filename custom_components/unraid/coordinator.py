"""DataUpdateCoordinator for Unraid."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import asyncio
from typing import Any, Dict
from collections import deque
from dataclasses import dataclass
from homeassistant.core import callback

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator, 
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_GENERAL_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    CONF_HAS_UPS,
)
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

@dataclass
class DiskUpdateMetrics:
    """Class to track disk update metrics."""
    last_update: datetime
    duration: float
    success: bool

class UnraidDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Unraid data.
    
    This coordinator manages two different update intervals:
    1. General interval (minutes): For updating non-disk sensors
    2. Disk interval (hours): For updating disk-related information
    
    The coordinator ensures thread-safe updates and proper error handling.
    """

    def __init__(
        self, 
        hass: HomeAssistant, 
        api: UnraidAPI, 
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator.
        
        Args:
            hass: HomeAssistant instance
            api: UnraidAPI instance
            entry: ConfigEntry instance
        """
        self.api = api
        self.entry = entry
        self.has_ups = entry.options.get(CONF_HAS_UPS, False)
        
        # Thread safety locks
        self._disk_update_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()
        
        # Update tracking
        self._last_disk_update: datetime | None = None
        self._update_metrics: deque[DiskUpdateMetrics] = deque(maxlen=10)
        self._disk_update_in_progress = False
        self._failed_update_count = 0

        # Get update intervals from options with validation
        self._general_interval = max(
            1, 
            min(
                60,
                entry.options.get(CONF_GENERAL_INTERVAL, DEFAULT_GENERAL_INTERVAL)
            )
        )
        self._disk_interval = max(
            1,
            min(
                24,
                entry.options.get(CONF_DISK_INTERVAL, DEFAULT_DISK_INTERVAL)
            )
        )

        self._disk_update_interval = timedelta(hours=self._disk_interval)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self._general_interval),
        )

    @property
    def disk_update_due(self) -> bool:
        """Check if a disk update is due."""
        if self._last_disk_update is None:
            return True
        
        next_update = self._last_disk_update + self._disk_update_interval
        return dt_util.utcnow() >= next_update

    @callback
    def async_get_last_disk_update(self) -> datetime | None:
        """Get the timestamp of the last successful disk update."""
        return self._last_disk_update

    @callback
    def async_get_update_metrics(self) -> list[DiskUpdateMetrics]:
        """Get recent update metrics."""
        return list(self._update_metrics)

    async def _async_update_disk_data(
        self, 
        system_stats: dict[str, Any]
    ) -> dict[str, Any]:
        """Update disk-specific data.
        
        Args:
            system_stats: Current system stats dictionary to update
            
        Returns:
            Updated system stats dictionary
            
        Raises:
            UpdateFailed: If disk update fails
        """
        start_time = dt_util.utcnow()
        success = False
        duration = 0.0

        try:
            async with self._disk_update_lock:
                if self._disk_update_in_progress:
                    _LOGGER.debug("Disk update already in progress, skipping")
                    return system_stats

                self._disk_update_in_progress = True
                
                try:
                    _LOGGER.debug("Starting disk information update")
                    
                    disk_data = await self.api.get_individual_disk_usage()
                    array_data = await self.api._get_array_usage()
                    
                    system_stats["individual_disks"] = disk_data
                    system_stats["array_usage"] = array_data
                    
                    self._last_disk_update = dt_util.utcnow()
                    self._failed_update_count = 0
                    success = True
                    
                    _LOGGER.debug(
                        "Disk update completed successfully. Next update due: %s",
                        self._last_disk_update + self._disk_update_interval
                    )
                    
                    return system_stats

                except Exception as err:
                    self._failed_update_count += 1
                    error_msg = f"Error updating disk data: {err}"
                    
                    if self._failed_update_count >= 3:
                        _LOGGER.error(
                            "%s. Failed update count: %d", 
                            error_msg, 
                            self._failed_update_count
                        )
                    else:
                        _LOGGER.warning(error_msg)
                        
                    # Reuse previous disk data if available
                    if "individual_disks" in self.data.get("system_stats", {}):
                        system_stats["individual_disks"] = (
                            self.data["system_stats"]["individual_disks"]
                        )
                        system_stats["array_usage"] = (
                            self.data["system_stats"]["array_usage"]
                        )
                        return system_stats
                        
                    raise UpdateFailed(error_msg) from err

        finally:
            self._disk_update_in_progress = False
            duration = (dt_util.utcnow() - start_time).total_seconds()
            
            async with self._metrics_lock:
                self._update_metrics.append(
                    DiskUpdateMetrics(
                        last_update=dt_util.utcnow(),
                        duration=duration,
                        success=success,
                    )
                )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Unraid.
        
        This method implements the main update logic, handling both
        general updates and disk updates when due.
        
        Returns:
            Dict containing all Unraid data
            
        Raises:
            UpdateFailed: If critical data cannot be fetched
        """
        try:
            # Always fetch non-disk data
            data = {
                "vms": await self.api.get_vms(),
                "docker_containers": await self.api.get_docker_containers(),
                "user_scripts": await self.api.get_user_scripts(),
                "parity_status": await self.api.get_parity_status(),
            }

            # Get base system stats
            system_stats = await self.api.get_system_stats()

            # Handle disk updates
            if self.disk_update_due:
                system_stats = await self._async_update_disk_data(system_stats)
            elif self.data and "system_stats" in self.data:
                # Reuse previous disk data
                system_stats["individual_disks"] = (
                    self.data["system_stats"]["individual_disks"]
                )
                system_stats["array_usage"] = (
                    self.data["system_stats"]["array_usage"]
                )

            # Add network statistics processing
            await self._async_update_network_stats(system_stats)

            # Update system stats in final data
            data["system_stats"] = system_stats

            # Add UPS data if enabled
            if self.has_ups:
                ups_info = await self.api.get_ups_info()
                if ups_info:
                    data["ups_info"] = ups_info

            return data

        except Exception as err:
            _LOGGER.error("Error communicating with Unraid: %s", err)
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def _async_update_network_stats(
        self, 
        system_stats: dict[str, Any]
    ) -> None:
        """Update network statistics with proper rate calculation."""
        try:
            network_stats = await self.api.get_network_stats()
            current_time = dt_util.utcnow()

            if (hasattr(self, '_previous_network_stats') and 
                hasattr(self, '_last_network_update')):
                
                time_diff = (
                    current_time - self._last_network_update
                ).total_seconds()
                
                if time_diff > 0:
                    for interface, stats in network_stats.items():
                        if interface in self._previous_network_stats:
                            prev_stats = self._previous_network_stats[interface]
                            
                            # Calculate rates with overflow protection
                            for direction in ['rx', 'tx']:
                                current = stats[f'{direction}_bytes']
                                previous = prev_stats[f'{direction}_bytes']
                                
                                if current >= previous:
                                    rate = (current - previous) / time_diff
                                else:
                                    # Handle counter overflow
                                    rate = 0
                                    _LOGGER.debug(
                                        "Network counter overflow detected for %s %s",
                                        interface,
                                        direction
                                    )
                                    
                                stats[f'{direction}_speed'] = rate

            # Update previous stats
            self._previous_network_stats = network_stats
            self._last_network_update = current_time
            
            # Add network stats to system_stats
            system_stats['network_stats'] = network_stats

        except Exception as err:
            _LOGGER.error("Error updating network stats: %s", err)
            # Don't re-raise - network stats are non-critical

    async def async_setup(self) -> bool:
        """Verify we can connect to the Unraid server."""
        try:
            if not await self.api.ping():
                raise ConfigEntryNotReady("Unable to connect to Unraid server")
            return True
        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err

    async def async_update_ups_status(self, has_ups: bool) -> None:
        """Update the UPS status and trigger a refresh."""
        self.has_ups = has_ups
        await self.async_refresh()