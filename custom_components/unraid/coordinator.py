"""Data Update Coordinator for Unraid."""
from __future__ import annotations

import logging
import asyncio
import hashlib
import json
from typing import Any, Dict, Optional

from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass
from homeassistant.core import callback # type: ignore

from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.update_coordinator import ( # type: ignore
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryNotReady # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .const import (
    CONF_DOCKER_INSIGHTS,
    CONF_HOSTNAME,
    DEFAULT_NAME,
    DOMAIN,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_GENERAL_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    CONF_HAS_UPS,
)
from .unraid import UnraidAPI
from .helpers import get_unraid_disk_mapping
from .docker_insights import DockerInsights
from .disk_mapping import get_disk_info

_LOGGER = logging.getLogger(__name__)

@dataclass
class DiskUpdateMetrics:
    """Class to track disk update metrics."""
    last_update: datetime
    duration: float
    success: bool

class UnraidDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Unraid data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UnraidAPI,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
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

        # Enhanced disk mapping tracking
        self._disk_mapping: Dict[str, str] = {}
        self._previous_disk_mapping: Dict[str, str] = {}
        self._last_disk_config_hash: Optional[str] = None
        self._last_valid_mapping: Optional[Dict[str, str]] = None
        self._mapping_error_count: int = 0

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

        # Docker Insights
        self.docker_insights = entry.options.get(CONF_DOCKER_INSIGHTS, False)
        self.docker_monitor = None
        _LOGGER.debug("Docker Insights enabled: %s", self.docker_insights)

        if self.docker_insights:
            try:
                self.docker_monitor = DockerInsights(self.api)
                _LOGGER.debug("Created Docker monitor instance")
            except (KeyError, ValueError, TypeError) as err:
                _LOGGER.error("Failed to initialize Docker monitoring: %s", err)
                self.docker_monitor = None

        # Register cleanup for Docker monitor
        self.entry.async_on_unload(self.async_stop)

        # Initialize network tracking
        self._previous_network_stats = {}
        self._last_network_update = dt_util.utcnow()

        # Initialize parent class
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self._general_interval),
        )

    @property
    def hostname(self) -> str:
        """Get the hostname for entity naming."""
        raw_hostname = self.entry.data.get(CONF_HOSTNAME, DEFAULT_NAME)
        return raw_hostname.capitalize()

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

    async def async_stop(self) -> None:
        """Stop the coordinator and cleanup resources."""
        try:
            if self.docker_monitor:
                await self.docker_monitor.close()
                self.docker_monitor = None

            # Ensure API connection is closed
            if hasattr(self.api, 'conn') and self.api.conn:
                await self.api.disconnect()

            # Close any remaining sessions
            if hasattr(self, '_session') and self._session:
                await self._session.close()
                
        except Exception as err:
            _LOGGER.error("Error during coordinator shutdown: %s", err)

    async def async_unload(self) -> None:
        """Unload the coordinator and cleanup all resources."""
        await self.async_stop()
        
        try:
            # Clean up any remaining unclosed connectors
            for task in asyncio.all_tasks():
                if 'connector' in str(task) and not task.done():
                    task.cancel()
        except Exception as err:
            _LOGGER.error("Error cleaning up tasks: %s", err)

    def _get_disk_config_hash(self, system_stats: dict) -> str:
        """Generate a hash of current disk configuration to detect changes."""
        disk_config = []
        for disk in system_stats.get("individual_disks", []):
            disk_config.append({
                "name": disk.get("name"),
                "mount_point": disk.get("mount_point"),
                "device": disk.get("device")
            })

        config_str = json.dumps(disk_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    @callback
    def _verify_disk_mapping(
        self,
        old_mapping: Dict[str, str],
        new_mapping: Dict[str, str],
    ) -> bool:
        """Verify disk mapping consistency.
        
        Args:
            old_mapping: Previous disk mapping
            new_mapping: New disk mapping
            
        Returns:
            bool: True if mapping is consistent, False otherwise
        """
        if not old_mapping:
            return True

        inconsistent = {
            disk: (old_dev, new_mapping[disk])
            for disk, old_dev in old_mapping.items()
            if disk in new_mapping and old_dev != new_mapping[disk]
        }

        if inconsistent:
            self._mapping_error_count += 1
            _LOGGER.warning(
                "Inconsistent disk mapping detected (error count: %d): %s",
                self._mapping_error_count,
                {k: f"was {v[0]}, now {v[1]}" for k, v in inconsistent.items()}
            )
            return False

        self._mapping_error_count = 0
        return True

    async def _async_update_disk_mapping(self, system_stats: dict) -> dict:
        """Update disk mapping data."""
        try:
            if "individual_disks" not in system_stats:
                return system_stats

            # Update disk mapping
            disk_mapping = get_unraid_disk_mapping({"system_stats": system_stats})
            system_stats["disk_mapping"] = disk_mapping

            # Add formatted disk info for each mapped disk
            system_stats["disk_info"] = {}
            for disk_name in disk_mapping:
                disk_info = get_disk_info({"system_stats": system_stats}, disk_name)
                if disk_info:
                    system_stats["disk_info"][disk_name] = disk_info

            return system_stats

        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.error("Error updating disk mapping: %s", err)
            return system_stats

    async def _async_update_disk_data(
        self,
        system_stats: dict[str, Any]
    ) -> dict[str, Any]:
        """Update disk-specific data."""
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
                    array_data = await self.api.get_array_usage()

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

                except (ConnectionError, TimeoutError, ValueError, OSError) as err:
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
        """Fetch data from Unraid."""
        try:
            _LOGGER.debug("Starting data update cycle")
            async with self.api:
                _LOGGER.debug("Established SSH session")
                # Initialize data structure
                data: Dict[str, Any] = {}

                # Step 1: Update core system stats (Always run)
                try:
                    # Get base system stats first
                    _LOGGER.debug("Fetching system stats...")
                    system_stats = await self.api.get_system_stats()
                    if system_stats:
                        _LOGGER.debug(
                            "Got system stats: %s",
                            {
                                k: '...' if k == 'individual_disks' else v
                                for k, v in system_stats.items()
                            }
                        )
                        data["system_stats"] = system_stats
                except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                    _LOGGER.error("Error getting system stats: %s", err)
                    data["system_stats"] = {}

                # Step 2: Get VMs, Docker Containers, and User Scripts
                try:
                    # Run these tasks concurrently
                    vms, containers, scripts = await asyncio.gather(
                        self.api.get_vms(),
                        self.api.get_docker_containers(),
                        self.api.get_user_scripts()
                    )

                    # Process results
                    data["vms"] = vms
                    data["docker_containers"] = containers
                    data["user_scripts"] = scripts

                except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                    _LOGGER.error("Error getting base data: %s", err)
                    data.update({
                        "vms": [],
                        "docker_containers": [],
                        "user_scripts": []
                    })

                # Step 3: Update disk-related data (Always run)
                if "system_stats" in data:
                    try:
                        # Get disk configuration
                        disk_cfg_result = await self.api.execute_command(
                            "cat /boot/config/disk.cfg"
                        )
                        if disk_cfg_result and disk_cfg_result.exit_status == 0:
                            disk_config = {}
                            for line in disk_cfg_result.stdout.splitlines():
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    try:
                                        key, value = line.split("=", 1)
                                        disk_config[key] = value.strip('"')
                                    except ValueError:
                                        continue
                            data["disk_config"] = disk_config
                    except (OSError, ConnectionError, TimeoutError) as err:
                        _LOGGER.error("Error getting disk config: %s", err)

                    # Handle disk updates
                    if self.disk_update_due:
                        try:
                            data["system_stats"] = await self._async_update_disk_data(
                                data["system_stats"]
                            )
                        except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                            _LOGGER.error("Error updating disk data: %s", err)
                    elif self.data and "system_stats" in self.data:
                        # Reuse previous disk data
                        data["system_stats"]["individual_disks"] = (
                            self.data["system_stats"].get("individual_disks", [])
                        )
                        data["system_stats"]["array_usage"] = (
                            self.data["system_stats"].get("array_usage", {})
                        )

                    # Update disk mapping and network stats
                    data["system_stats"] = await self._async_update_disk_mapping(
                        data["system_stats"]
                    )
                    await self._async_update_network_stats(data["system_stats"])

                # Step 4: UPS data if enabled (independent of Docker)
                if self.has_ups:
                    try:
                        ups_info = await self.api.get_ups_info()
                        if ups_info:
                            data["ups_info"] = ups_info
                    except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                        _LOGGER.error("Error getting UPS info: %s", err)

                # Step 5: Docker data (Only if Docker insights is enabled)
                if self.docker_insights and self.docker_monitor:
                    try:
                        # Get basic container list first
                        containers = await self.api.get_docker_containers()
                        data["docker_containers"] = containers

                        # Then get detailed stats if available
                        docker_stats = await self.docker_monitor.get_container_stats()
                        _LOGGER.debug("Got Docker stats: %s", docker_stats)
                        data["docker_stats"] = docker_stats
                    except Exception as err:
                        _LOGGER.error("Error getting Docker stats: %s", err)
                        # Don't let Docker errors affect other data
                        data["docker_containers"] = []
                        data["docker_stats"] = {"containers": {}, "summary": {}}

                _LOGGER.debug("Data update complete. Keys collected: %s", list(data.keys()))
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

        except (ConnectionError, TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error updating network stats: %s", err)
            # Don't re-raise - network stats are non-critical

    async def async_setup(self) -> bool:
        """Verify we can connect to the Unraid server and setup monitoring."""
        try:
            # First verify Unraid connection
            if not await self.api.ping():
                raise ConfigEntryNotReady("Unable to connect to Unraid server")

            # Initialize base system monitoring first
            await self._async_update_data()

            # Initialize Docker monitoring if enabled
            if self.docker_insights:
                try:
                    self.docker_monitor = DockerInsights(self.api)
                    await self.docker_monitor.connect()
                    _LOGGER.debug("Connected to Docker monitor")
                except Exception as err:
                    _LOGGER.error("Failed to initialize Docker monitoring: %s", err)
                    self.docker_monitor = None

            return True

        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err

    async def async_update_ups_status(self, has_ups: bool) -> None:
        """Update the UPS status and trigger a refresh."""
        self.has_ups = has_ups
        await self.async_refresh()

    async def async_update_docker_insights(self, enabled: bool) -> None:
        """Update Docker insights status."""
        self.docker_insights = enabled
        if enabled and not self.docker_monitor:
            try:
                self.docker_monitor = DockerInsights(self.api)
                await self.docker_monitor.connect()
            except (ConnectionError, TimeoutError, ValueError, OSError) as err:
                _LOGGER.error("Failed to initialize Docker monitoring: %s", err)
                self.docker_monitor = None
        elif not enabled and self.docker_monitor:
            await self.docker_monitor.close()
            self.docker_monitor = None

        await self.async_request_refresh()
