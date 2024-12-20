"""Data Update Coordinator for Unraid."""
from __future__ import annotations

from contextlib import suppress
import logging
import asyncio
import hashlib
import json
from typing import Any, Dict, Optional

from datetime import datetime, timedelta
from collections import defaultdict, deque
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
from .insights import get_docker_insights
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

        # Device tracking
        self._device_lock = asyncio.Lock()
        self._known_devices: set[str] = set()
        self._device_timeouts = defaultdict(int)

        # Thread safety locks
        self._disk_update_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()

        # Docker Insights
        self._docker_connect_task = None
        self._docker_monitor_ready = asyncio.Event()

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

        # State management
        self._busy = False
        self._closed = False

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

        # Docker Insights initialization
        self.docker_insights = entry.options.get(CONF_DOCKER_INSIGHTS, False)
        self.docker_monitor = None
        _LOGGER.debug("Docker Insights enabled: %s", self.docker_insights)

        if self.docker_insights:
            try:
                DockerInsights = get_docker_insights()  # Get the class only when needed
                self.docker_monitor = DockerInsights(self.api)
                _LOGGER.debug("Created Docker monitor instance")
            except Exception as err:
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
        self._closed = True
        await self.async_unload()

    async def async_unload(self) -> None:
        """Unload the coordinator and cleanup all resources."""
        try:
            self._busy = True
            
            # Stop Docker monitoring if enabled
            if self.docker_monitor:
                try:
                    await self.docker_monitor.disable()
                    await self.docker_monitor.cleanup()
                except Exception as err:
                    _LOGGER.debug("Error disabling Docker monitor: %s", err)
                finally:
                    self.docker_monitor = None

            # Cancel any pending tasks
            if self._docker_connect_task and not self._docker_connect_task.done():
                self._docker_connect_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._docker_connect_task

            # Final cleanup
            try:
                if hasattr(self.api, 'session') and self.api.session:
                    await self.api.session.close()
            except Exception as err:
                _LOGGER.debug("Error closing API session: %s", err)

        except Exception as err:
            _LOGGER.debug("Error during unload: %s", err)
        finally:
            self._busy = False
            self._closed = True

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
        """Verify disk mapping consistency."""
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
                        # Add CPU info explicitly
                        cpu_info = await self.api._get_cpu_info()  # Note the underscore for the private method
                        if cpu_info:
                            _LOGGER.debug("Adding CPU info to system stats: %s", cpu_info)
                            system_stats.update(cpu_info)
                        
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
                if self.docker_insights:
                    try:
                        # Verify docker monitor exists and is ready
                        if not self.docker_monitor:
                            _LOGGER.debug("Docker monitor not initialized, attempting setup")
                            await self.async_setup_docker_monitoring()
                            # Early return if setup fails
                            if not self.docker_monitor:
                                data["docker_stats"] = {"containers": {}, "summary": {}}
                                return data

                        # Get basic container list first
                        containers = await self.api.get_docker_containers()
                        data["docker_containers"] = containers

                        # Then get detailed stats if monitor is ready
                        if hasattr(self.docker_monitor, 'get_container_stats'):
                            docker_stats = await self.docker_monitor.get_container_stats()
                            if docker_stats:
                                _LOGGER.debug("Got Docker stats: %s", docker_stats)
                                data["docker_stats"] = docker_stats
                            else:
                                _LOGGER.debug("No Docker stats returned")
                                data["docker_stats"] = {"containers": {}, "summary": {}}
                        else:
                            _LOGGER.warning("Docker monitor missing get_container_stats method")
                            data["docker_stats"] = {"containers": {}, "summary": {}}
                                
                    except Exception as err:
                        _LOGGER.error("Error getting Docker stats: %s", err, exc_info=True)
                        if "NoneType" in str(err) or "Session is closed" in str(err):
                            _LOGGER.info("Docker connection lost, will retry on next update")
                            self.docker_monitor = None
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
        """Update network statistics asynchronously."""
        try:
            network_stats = await self.api.get_network_stats()
            
            if network_stats:
                # Store network stats in system_stats
                system_stats['network_stats'] = network_stats
                
                # Log debug info for significant changes
                if self._previous_network_stats:
                    for interface, stats in network_stats.items():
                        if interface in self._previous_network_stats:
                            prev_stats = self._previous_network_stats[interface]
                            rx_change = abs(stats['rx_speed'] - prev_stats.get('rx_speed', 0))
                            tx_change = abs(stats['tx_speed'] - prev_stats.get('tx_speed', 0))
                            
                            # Log significant changes (more than 20% difference)
                            if rx_change > prev_stats.get('rx_speed', 0) * 0.2:
                                _LOGGER.debug(
                                    "Significant RX speed change for %s: %.2f -> %.2f",
                                    interface,
                                    prev_stats.get('rx_speed', 0),
                                    stats['rx_speed']
                                )
                            if tx_change > prev_stats.get('tx_speed', 0) * 0.2:
                                _LOGGER.debug(
                                    "Significant TX speed change for %s: %.2f -> %.2f",
                                    interface,
                                    prev_stats.get('tx_speed', 0),
                                    stats['tx_speed']
                                )
                
                # Update previous stats for next comparison
                self._previous_network_stats = network_stats

        except Exception as err:
            _LOGGER.error("Error updating network stats: %s", err)
            # Keep previous stats in case of error
            if self._previous_network_stats:
                system_stats['network_stats'] = self._previous_network_stats

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
                await self.async_setup_docker_monitoring()

            return True

        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err

    async def async_setup_docker_monitoring(self) -> None:
        """Set up Docker monitoring in a non-blocking way."""
        try:
            DockerInsights = get_docker_insights()
            if DockerInsights:
                self.docker_monitor = DockerInsights(self.api)
                
                # Create connection task but don't wait for it
                self._docker_connect_task = asyncio.create_task(
                    self._establish_docker_connection()
                )
            else:
                _LOGGER.error("Docker insights class not available")
                self.docker_monitor = None
                
        except Exception as err:
            _LOGGER.error("Failed to initialize Docker monitoring: %s", err)
            self.docker_monitor = None

    async def _establish_docker_connection(self, retry_count: int = 3, retry_delay: float = 2.0) -> None:
        """Establish Docker connection with retry logic."""
        if not self.docker_monitor:
            return
            
        for attempt in range(retry_count):
            try:
                await self.docker_monitor.connect()
                _LOGGER.debug("Successfully connected to Docker monitor")
                self.docker_monitor._monitor_ready.set() # Update this line
                return
                
            except Exception as err:
                if attempt < retry_count - 1:
                    _LOGGER.warning(
                        "Docker connection attempt %d/%d failed: %s. Retrying in %s seconds",
                        attempt + 1, 
                        retry_count,
                        err,
                        retry_delay
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    _LOGGER.error("Failed to establish Docker connection after %d attempts", retry_count)
                    self.docker_monitor = None

    async def async_update_ups_status(self, has_ups: bool) -> None:
        """Update the UPS status and trigger a refresh."""
        self.has_ups = has_ups
        await self.async_refresh()

    async def async_update_docker_insights(self, enabled: bool) -> None:
        """Update Docker insights status and manage monitor lifecycle."""
        # Store previous state for rollback
        previous_state = self.docker_insights
        previous_monitor = self.docker_monitor

        try:
            _LOGGER.debug("Updating Docker insights state: enabled=%s", enabled)
            self.docker_insights = enabled

            if enabled and not self.docker_monitor:
                _LOGGER.debug("Enabling Docker monitoring")
                await self.async_setup_docker_monitoring()
                if not self.docker_monitor:
                    raise RuntimeError("Failed to initialize Docker monitoring")
                    
            elif not enabled and self.docker_monitor:
                _LOGGER.debug("Disabling Docker monitoring")
                try:
                    # Gracefully shut down monitoring
                    monitor = self.docker_monitor
                    self.docker_monitor = None  # Prevent new operations

                    # Disable stats collection first
                    if hasattr(monitor, 'disable'):
                        try:
                            await monitor.disable()
                        except Exception as err:
                            _LOGGER.warning("Error disabling Docker monitor: %s", err)

                    # Then close all connections
                    if hasattr(monitor, 'cleanup'):
                        await monitor.cleanup()
                    elif hasattr(monitor, 'close'):
                        await monitor.close()

                    # Cancel any remaining tasks
                    tasks = [
                        task for task in asyncio.all_tasks()
                        if 'docker' in str(task).lower() and not task.done()
                    ]
                    for task in tasks:
                        task.cancel()
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

                except Exception as err:
                    _LOGGER.error("Error during Docker monitor shutdown: %s", err)
                    # Continue with cleanup despite errors

            # Request data refresh
            await self.async_request_refresh()
            _LOGGER.info(
                "Successfully %s Docker insights", 
                "enabled" if enabled else "disabled"
            )

        except Exception as err:
            _LOGGER.error("Failed to %s Docker insights: %s", 
                        "enable" if enabled else "disable", 
                        err)
            
            # Rollback to previous state
            self.docker_insights = previous_state
            self.docker_monitor = previous_monitor
            
            # Ensure cleanup if we failed during enable
            if enabled and self.docker_monitor and self.docker_monitor != previous_monitor:
                try:
                    await self.docker_monitor.cleanup()
                except Exception as cleanup_err:
                    _LOGGER.error("Error during rollback cleanup: %s", cleanup_err)
                finally:
                    self.docker_monitor = previous_monitor

            raise RuntimeError(f"Failed to update Docker insights: {err}") from err

        finally:
            # Ensure we're in a consistent state
            if not enabled and self.docker_monitor:
                self.docker_monitor = None