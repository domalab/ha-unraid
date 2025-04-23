"""Data Update Coordinator for Unraid."""
from __future__ import annotations

import logging
import asyncio
import hashlib
import json
import time
import gc
from typing import Any, Dict, Optional, List, Set, cast

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
from .helpers import parse_speed_string
from .api.disk_mapper import DiskMapper
from .api.cache_manager import CacheManager, CacheItemPriority
from .api.sensor_priority import SensorPriorityManager, SensorPriority, SensorCategory
from .api.logging_helper import LogManager
from .types import UnraidDataDict, SystemStatsDict, DockerContainerDict, VMDict, UserScriptDict

_LOGGER = logging.getLogger(__name__)

@dataclass
class DiskUpdateMetrics:
    """Class to track disk update metrics."""
    last_update: datetime
    duration: float
    success: bool

class UnraidDataUpdateCoordinator(DataUpdateCoordinator[UnraidDataDict]):
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

        # Check if UPS is enabled in configuration
        has_ups_in_data = entry.data.get(CONF_HAS_UPS, False)
        has_ups_in_options = entry.options.get(CONF_HAS_UPS, False)
        _LOGGER.debug(
            "UPS configuration - Data: %s, Options: %s",
            has_ups_in_data,
            has_ups_in_options
        )

        # Use data if options is not set
        self.has_ups = has_ups_in_options or has_ups_in_data
        _LOGGER.debug("UPS enabled: %s", self.has_ups)

        # Device tracking
        self._device_lock = asyncio.Lock()
        self._known_devices: set[str] = set()
        self._device_timeouts = defaultdict(int)

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

        # Get disk update interval in minutes
        disk_interval_minutes = entry.options.get(CONF_DISK_INTERVAL, DEFAULT_DISK_INTERVAL)
        self._disk_interval = disk_interval_minutes

        # Convert minutes to timedelta
        self._disk_update_interval = timedelta(minutes=self._disk_interval)

        # Always use entity format version 2
        self._entity_format = 2

        # Initialize network tracking
        self._previous_network_stats = {}
        self._last_network_update = dt_util.utcnow()

        # Performance optimization components
        self._cache_manager = CacheManager(max_size_bytes=50 * 1024 * 1024)  # Increased to 50MB limit
        self._sensor_manager = SensorPriorityManager()
        self._log_manager = LogManager()
        self._log_manager.configure()
        self._update_requested_sensors: Set[str] = set()

        # Cache TTL settings for different data types
        self._cache_ttls = {
            # Static or rarely changing data
            "disk_mapping": 3600,  # 1 hour
            "disk_info": 1800,     # 30 minutes
            "smart_data": 1800,    # 30 minutes
            "docker_info": 600,    # 10 minutes
            "vm_info": 600,        # 10 minutes

            # Semi-dynamic data
            "system_stats": 120,    # 2 minutes
            "array_state": 60,      # 1 minute
            "ups_info": 120,        # 2 minutes

            # Highly dynamic data
            "cpu_info": 30,         # 30 seconds
            "memory_info": 30,      # 30 seconds
            "network_stats": 15,    # 15 seconds
        }

        # Resource monitoring
        self._last_memory_check = dt_util.utcnow()
        self._memory_warning_emitted = False

        # Initialize parent class
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self._general_interval),
        )

    @property
    def hostname(self) -> str:
        """Get the hostname for entity naming.

        First tries to get the hostname from the Unraid server,
        then falls back to the hostname from the config entry.
        """
        # Try to get the hostname from the data if available
        if self.data and "hostname" in self.data:
            hostname = self.data.get("hostname")
            if hostname:
                _LOGGER.debug("Using hostname from Unraid server: %s", hostname)
                return hostname

        # Fall back to the hostname from the config entry
        raw_hostname = self.entry.data.get(CONF_HOSTNAME, DEFAULT_NAME)
        _LOGGER.debug("Using hostname from config entry: %s", raw_hostname)
        return raw_hostname.capitalize()

    @property
    def entity_format(self) -> int:
        """Get the entity format version."""
        return self._entity_format

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

    def _get_disk_config_hash(self, system_stats: SystemStatsDict) -> str:
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
        """Update disk mapping data using the DiskMapper class."""
        try:
            if "individual_disks" not in system_stats:
                return system_stats

            # Create a DiskMapper instance
            disk_mapper = DiskMapper(self.api.execute_command)

            # Convert system_stats disk data to the format expected by DiskMapper
            disk_mapping = {}
            for disk in system_stats.get("individual_disks", []):
                name = disk.get("name", "")
                if name:
                    disk_mapping[name] = {
                        "device": disk.get("device", ""),
                        "serial": disk.get("serial", ""),
                        "name": name
                    }

            system_stats["disk_mapping"] = disk_mapping

            # Add formatted disk info for each mapped disk
            system_stats["disk_info"] = {}
            for disk_name in disk_mapping:
                disk_info = disk_mapper.get_disk_info_from_system_stats(system_stats, disk_name)
                if disk_info:
                    system_stats["disk_info"][disk_name] = disk_info

            return system_stats

        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.error("Error updating disk mapping: %s", err)
            return system_stats

    async def _update_disk_mappings(self, data: dict) -> None:
        """Update disk mappings with comprehensive information using DiskMapper."""
        try:
            # Create a DiskMapper instance
            disk_mapper = DiskMapper(self.api.execute_command)

            # Only update if we don't already have valid mappings
            if not data.get("disk_mappings"):
                # Get disk identifiers from DiskMapper
                disk_identifiers = await disk_mapper.refresh_mappings()

                # Convert DiskIdentifier objects to dictionaries for backward compatibility
                mappings = {}
                for disk_name, identifier in disk_identifiers.items():
                    mappings[disk_name] = {
                        "name": disk_name,
                        "device": identifier.device or "",
                        "serial": identifier.serial or "",
                        "status": identifier.status,
                        "filesystem": identifier.filesystem or "",
                        "spindown_delay": identifier.spindown_delay
                    }

                if mappings:
                    data["disk_mappings"] = mappings
                    _LOGGER.debug(
                        "Updated disk mappings for %d disks using DiskMapper",
                        len(mappings)
                    )
                else:
                    _LOGGER.debug("No disk mappings available from DiskMapper")
        except Exception as err:
            _LOGGER.warning("Error updating disk mappings: %s", err)
            # Don't let mapping errors affect other data
            if "disk_mappings" not in data:
                data["disk_mappings"] = {}

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

                    disk_data, extra_stats = await self.api.get_individual_disk_usage()
                    array_data = await self.api.get_array_usage()

                    system_stats["individual_disks"] = disk_data
                    system_stats["array_usage"] = array_data

                    # Add any extra stats from disk operations
                    if extra_stats:
                        for key, value in extra_stats.items():
                            system_stats[key] = value

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
            # Check memory usage periodically - don't update if we're over limit
            await self._check_memory_usage()

            _LOGGER.debug("Starting data update cycle")
            async with self.api:
                # Initialize data structure
                data: UnraidDataDict = {}
                cache_hits = 0
                cache_misses = 0
                start_time = time.time()

                # Get hostname from cache or fetch from Unraid server
                hostname_key = self._get_cache_key("hostname")
                hostname = self._cache_manager.get(hostname_key)

                if hostname:
                    data["hostname"] = hostname
                    _LOGGER.debug("Using cached hostname: %s", hostname)
                else:
                    try:
                        hostname = await self.api.get_hostname()
                        if hostname:
                            data["hostname"] = hostname
                            # Cache the hostname
                            self._cache_manager.set(
                                hostname_key,
                                hostname,
                                ttl=86400,  # 24 hours - hostname rarely changes
                                priority=CacheItemPriority.CRITICAL
                            )
                            _LOGGER.debug("Retrieved hostname from Unraid server: %s", hostname)
                    except Exception as err:
                        _LOGGER.debug("Error getting hostname from Unraid server: %s", err)

                # Track what data is needed based on sensor priorities
                # Check if self.async_contexts exists before calling len()
                has_contexts = hasattr(self, 'async_contexts') and self.async_contexts is not None
                critical_update = bool(self._update_requested_sensors) or (has_contexts and bool(self.async_contexts))

                # Step 1: Update core system stats (Always run)
                try:
                    # Get base system stats first
                    _LOGGER.debug("Fetching system stats...")

                    # Try to get system stats from cache first
                    system_stats_key = self._get_cache_key("system_stats")
                    system_stats: Optional[SystemStatsDict] = None

                    if critical_update:
                        # Force update if specifically requested
                        system_stats = await self.api.get_system_stats()
                        cache_misses += 1

                        # Cache the result for future use
                        if system_stats:
                            self._cache_manager.set(
                                system_stats_key,
                                system_stats,
                                ttl=self._cache_ttls["system_stats"],
                                priority=CacheItemPriority.HIGH
                            )
                    else:
                        # Get from cache with fallback to API call
                        system_stats = self._cache_manager.get(system_stats_key)

                        if system_stats:
                            cache_hits += 1
                            _LOGGER.debug("Using cached system stats")
                        else:
                            system_stats = await self.api.get_system_stats()
                            cache_misses += 1

                            # Cache the result
                            if system_stats:
                                self._cache_manager.set(
                                    system_stats_key,
                                    system_stats,
                                    ttl=self._cache_ttls["system_stats"],
                                    priority=CacheItemPriority.HIGH
                                )

                    if system_stats:
                        # Add CPU info with caching
                        cpu_info_key = self._get_cache_key("cpu_info")

                        # CPU info is volatile - cache for shorter period
                        cpu_info = None
                        if not critical_update:
                            cpu_info = self._cache_manager.get(cpu_info_key)
                            if cpu_info:
                                cache_hits += 1

                        if not cpu_info:
                            cpu_info = {}
                            # Get CPU info from system stats if needed
                            system_stats_data = await self.api.get_system_stats()
                            if system_stats_data and "cpu_info" in system_stats_data:
                                cpu_info = system_stats_data.get("cpu_info", {})
                            cache_misses += 1

                            if cpu_info:
                                self._cache_manager.set(
                                    cpu_info_key,
                                    cpu_info,
                                    ttl=self._cache_ttls["cpu_info"],
                                    priority=CacheItemPriority.HIGH
                                )

                        if cpu_info:
                            system_stats.update(cpu_info)

                        data["system_stats"] = system_stats
                except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                    _LOGGER.error("Error getting system stats: %s", err)
                    data["system_stats"] = {}

                # Get array state and parity info - always critical
                array_state_key = self._get_cache_key("array_state")
                array_state = None

                # Array state is critical - shorter cache or force update if needed
                if critical_update:
                    array_state = await self._get_array_state()
                    cache_misses += 1

                    # Cache for very short period (it's important)
                    if array_state:
                        self._cache_manager.set(
                            array_state_key,
                            array_state,
                            ttl=30,  # 30 second cache for array state
                            priority=CacheItemPriority.CRITICAL
                        )
                else:
                    # Try cache first
                    array_state = self._cache_manager.get(array_state_key)
                    if array_state:
                        cache_hits += 1
                    else:
                        array_state = await self._get_array_state()
                        cache_misses += 1

                        if array_state:
                            self._cache_manager.set(
                                array_state_key,
                                array_state,
                                ttl=30,
                                priority=CacheItemPriority.CRITICAL
                            )

                if array_state:
                    data["array_state"] = array_state

                # Step 2: Get VMs, Docker Containers, and User Scripts - use priority-based updates
                # Initialize default values in case they don't exist yet
                vms = []
                containers = []
                scripts = []

                # Only update these if they are due according to sensor priority
                vm_key = self._get_cache_key("vms")
                docker_key = self._get_cache_key("docker_containers")
                scripts_key = self._get_cache_key("user_scripts")

                # Check if any sensors related to these categories need updates
                # Safely get VM and container IDs from existing data
                vm_ids = []
                container_ids = []

                if hasattr(self, 'data') and self.data is not None:
                    if isinstance(self.data.get("vms"), list):
                        vm_ids = [vm.get("name", "") for vm in self.data.get("vms", []) if isinstance(vm, dict)]

                    if isinstance(self.data.get("docker_containers"), list):
                        container_ids = [c.get("name", "") for c in self.data.get("docker_containers", []) if isinstance(c, dict)]

                need_vm_update = critical_update or any(
                    self._sensor_manager.should_update(f"vm_{vm_id}")
                    for vm_id in vm_ids if vm_id
                )

                need_docker_update = critical_update or any(
                    self._sensor_manager.should_update(f"docker_{container_id}")
                    for container_id in container_ids if container_id
                )

                need_scripts_update = critical_update or self._sensor_manager.should_update("user_scripts")

                try:
                    # Run these tasks concurrently if needed, otherwise use cache
                    tasks = []

                    # VM update task
                    if need_vm_update:
                        tasks.append(self.api.get_vms())
                        cache_misses += 1
                    else:
                        vms = self._cache_manager.get(vm_key, [])
                        if vms:
                            cache_hits += 1
                        else:
                            tasks.append(self.api.get_vms())
                            cache_misses += 1

                    # Docker update task
                    if need_docker_update:
                        tasks.append(self.api.get_docker_containers())
                        cache_misses += 1
                    else:
                        containers = self._cache_manager.get(docker_key, [])
                        if containers:
                            cache_hits += 1
                        else:
                            tasks.append(self.api.get_docker_containers())
                            cache_misses += 1

                    # Scripts update task
                    if need_scripts_update:
                        tasks.append(self.api.get_user_scripts())
                        cache_misses += 1
                    else:
                        scripts = self._cache_manager.get(scripts_key, [])
                        if scripts:
                            cache_hits += 1
                        else:
                            tasks.append(self.api.get_user_scripts())
                            cache_misses += 1

                    # Run needed tasks concurrently
                    if tasks:
                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        # Process results based on which tasks were run
                        task_index = 0

                        # Process VM results if that task was run
                        if need_vm_update or not self._cache_manager.get(vm_key):
                            vms = results[task_index] if not isinstance(results[task_index], Exception) else []
                            task_index += 1

                            # Cache VM results
                            if vms:
                                self._cache_manager.set(
                                    vm_key,
                                    vms,
                                    ttl=300,  # 5 minute cache for VMs
                                    priority=CacheItemPriority.MEDIUM
                                )

                        # Process Docker results if that task was run
                        if need_docker_update or not self._cache_manager.get(docker_key):
                            containers = results[task_index] if not isinstance(results[task_index], Exception) else []
                            task_index += 1

                            # Cache Docker results
                            if containers:
                                self._cache_manager.set(
                                    docker_key,
                                    containers,
                                    ttl=300,  # 5 minute cache for containers
                                    priority=CacheItemPriority.MEDIUM
                                )

                        # Process Scripts results if that task was run
                        if need_scripts_update or not self._cache_manager.get(scripts_key):
                            scripts = results[task_index] if not isinstance(results[task_index], Exception) else []

                            # Cache Scripts results
                            if scripts:
                                self._cache_manager.set(
                                    scripts_key,
                                    scripts,
                                    ttl=600,  # 10 minute cache for scripts (rarely change)
                                    priority=CacheItemPriority.LOW
                                )

                    # Process results
                    data["vms"] = cast(List[VMDict], vms)
                    data["docker_containers"] = cast(List[DockerContainerDict], containers)
                    data["user_scripts"] = cast(List[UserScriptDict], scripts)

                    # Record sensor updates - ensure lists are iterable
                    if isinstance(vms, list):
                        for vm in vms:
                            if isinstance(vm, dict):
                                vm_id = vm.get("name", "unknown")
                                self._sensor_manager.record_update(f"vm_{vm_id}", vm.get("state"))

                    if isinstance(containers, list):
                        for container in containers:
                            if isinstance(container, dict):
                                container_id = container.get("name", "unknown")
                                self._sensor_manager.record_update(f"docker_{container_id}", container.get("state"))

                    if isinstance(scripts, list):
                        self._sensor_manager.record_update("user_scripts", len(scripts))

                except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                    _LOGGER.error("Error getting VM/Docker/Scripts data: %s", err)
                    data.update({
                        "vms": self._cache_manager.get(vm_key, []),
                        "docker_containers": self._cache_manager.get(docker_key, []),
                        "user_scripts": self._cache_manager.get(scripts_key, [])
                    })

                # Step 3: Update disk-related data based on priority and schedule
                if "system_stats" in data:
                    # Check if disk update is due based on schedule or forced update
                    disk_update_needed = (
                        critical_update or
                        self.disk_update_due or
                        any(s.startswith("disk_") for s in self._update_requested_sensors)
                    )

                    try:
                        # Handle disk updates
                        if disk_update_needed:
                            _LOGGER.debug("Disk update needed, running full update")
                            data["system_stats"] = await self._async_update_disk_data(
                                data["system_stats"]
                            )
                        elif self.data and "system_stats" in self.data:
                            # Reuse previous disk data
                            data["system_stats"]["individual_disks"] = (
                                self.data["system_stats"].get("individual_disks", [])
                            )
                            data["system_stats"]["array_usage"] = (
                                self.data["system_stats"].get("array_usage", {})
                            )

                        # Update disk mapping with cache
                        if disk_update_needed or "disk_mapping" not in data["system_stats"]:
                            # Force mapping update when needed
                            data["system_stats"] = await self._async_update_disk_mapping(
                                data["system_stats"]
                            )

                        # Update network stats based on priority
                        need_network_update = critical_update or any(
                            self._sensor_manager.should_update(f"network_{iface}")
                            for iface in self._previous_network_stats
                        ) if self._previous_network_stats else True

                        if need_network_update:
                            await self._async_update_network_stats(data["system_stats"])

                            # Record sensor updates
                            network_stats = data["system_stats"].get("network_stats", {})
                            if isinstance(network_stats, dict):
                                for interface in network_stats:
                                    stats = network_stats[interface]
                                    if isinstance(stats, dict):
                                        self._sensor_manager.record_update(
                                            f"network_{interface}",
                                            stats.get("rx_speed", 0)
                                        )

                    except Exception as err:
                        _LOGGER.error("Error updating disk/network data: %s", err)

                # Step 4: UPS data if enabled
                if self.has_ups:
                    ups_key = self._get_cache_key("ups_info")
                    need_ups_update = critical_update or self._sensor_manager.should_update("ups_status")

                    try:
                        ups_info = None

                        if need_ups_update:
                            ups_info = await self.api.get_ups_info()
                            cache_misses += 1

                            # Cache UPS info
                            if ups_info and isinstance(ups_info, dict):
                                self._cache_manager.set(
                                    ups_key,
                                    ups_info,
                                    ttl=120,  # 2 minute cache for UPS
                                    priority=CacheItemPriority.HIGH
                                )

                                # Record sensor update
                                status = ups_info.get("STATUS")
                                if status is not None:
                                    self._sensor_manager.record_update("ups_status", status)
                        else:
                            ups_info = self._cache_manager.get(ups_key)
                            if ups_info:
                                cache_hits += 1
                            else:
                                ups_info = await self.api.get_ups_info()
                                cache_misses += 1

                                if ups_info and isinstance(ups_info, dict):
                                    self._cache_manager.set(
                                        ups_key,
                                        ups_info,
                                        ttl=120,
                                        priority=CacheItemPriority.HIGH
                                    )

                        if ups_info and isinstance(ups_info, dict):
                            # Store UPS info in both locations for backward compatibility
                            data["ups_info"] = ups_info
                            _LOGGER.debug("UPS info fetched: %s", ups_info)

                            # Also store in system_stats for the UPS sensors to access
                            if "system_stats" in data and isinstance(data["system_stats"], dict):
                                data["system_stats"]["ups_info"] = ups_info
                                _LOGGER.debug("UPS info stored in system_stats")
                    except (ConnectionError, TimeoutError, OSError, ValueError) as err:
                        _LOGGER.error("Error getting UPS info: %s", err)

                # Step 5: Add parity schedule parsing with caching
                parity_key = self._get_cache_key("parity_schedule")
                need_parity_update = critical_update or self._sensor_manager.should_update("parity_schedule")

                try:
                    next_check = None

                    if need_parity_update:
                        next_check = await self._parse_parity_schedule()
                        cache_misses += 1

                        if next_check:
                            self._cache_manager.set(
                                parity_key,
                                next_check,
                                ttl=3600,  # 1 hour cache (rarely changes)
                                priority=CacheItemPriority.LOW
                            )

                            # Record sensor update
                            if isinstance(next_check, str):
                                self._sensor_manager.record_update("parity_schedule", next_check)
                    else:
                        next_check = self._cache_manager.get(parity_key)
                        if next_check:
                            cache_hits += 1
                        else:
                            next_check = await self._parse_parity_schedule()
                            cache_misses += 1

                            if next_check:
                                self._cache_manager.set(
                                    parity_key,
                                    next_check,
                                    ttl=3600,
                                    priority=CacheItemPriority.LOW
                                )

                    if next_check and isinstance(next_check, str):
                        data["next_parity_check"] = next_check

                except Exception as err:
                    _LOGGER.error("Error parsing parity schedule: %s", err)
                    data["next_parity_check"] = "Unknown"

                # Clear requested sensor updates
                self._update_requested_sensors.clear()

                # Calculate and log update performance
                elapsed = time.time() - start_time
                _LOGGER.debug(
                    "Data update complete in %.2fs. Cache hits: %d, misses: %d, hit rate: %.1f%%",
                    elapsed,
                    cache_hits,
                    cache_misses,
                    (cache_hits / max(1, cache_hits + cache_misses)) * 100
                )

                return data

        except Exception as err:
            _LOGGER.error("Error communicating with Unraid: %s", err)
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def _check_memory_usage(self) -> None:
        """Check memory usage and log warnings if needed."""
        # Only check once per minute
        if (dt_util.utcnow() - self._last_memory_check).total_seconds() < 60:
            return

        self._last_memory_check = dt_util.utcnow()

        try:
            # Get memory usage - use psutil if available, otherwise skip
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # Log warning if over 90MB
            if memory_mb > 90 and not self._memory_warning_emitted:
                _LOGGER.warning(
                    "High memory usage detected: %.1f MB - consider adjusting cache size",
                    memory_mb
                )
                self._memory_warning_emitted = True
            elif memory_mb < 85 and self._memory_warning_emitted:
                # Reset warning flag if memory drops below threshold
                self._memory_warning_emitted = False

            # If extremely high, force garbage collection and cache cleanup
            if memory_mb > 110:
                _LOGGER.warning(
                    "Critically high memory usage: %.1f MB - forcing cache cleanup",
                    memory_mb
                )

                # Force cleanup
                self._cache_manager._cleanup()

                # Force Python garbage collection
                gc.collect()

        except (ImportError, Exception):
            # If psutil not available, silently continue
            pass

    async def _parse_parity_schedule(self) -> Optional[str]:
        """Parse the parity check schedule."""
        try:
            result = await self.api.execute_command(
                "cat /boot/config/plugins/dynamix/parity-check.cron"
            )
            next_check = "Unknown"

            if result and result.exit_status == 0:
                # Parse the cron entries
                for line in result.stdout.splitlines():
                    if "mdcmd check" in line and not line.startswith('#'):
                        # Split the cron entry
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            minute, hour, dom, month, _ = parts[:5]  # dow not used

                            now = dt_util.now()
                            next_run = None

                            # Parse based on the cron pattern
                            if dom == "1" and month == "1":  # Yearly on Jan 1st
                                next_run = now.replace(
                                    month=1,
                                    day=1,
                                    hour=int(hour),
                                    minute=int(minute),
                                    second=0,
                                    microsecond=0
                                )
                                if next_run <= now:
                                    next_run = next_run.replace(year=next_run.year + 1)
                            elif dom == "1" and month == "*":  # Monthly on 1st
                                next_run = now.replace(
                                    day=1,
                                    hour=int(hour),
                                    minute=int(minute),
                                    second=0,
                                    microsecond=0
                                )
                                if next_run <= now:
                                    if next_run.month == 12:
                                        next_run = next_run.replace(year=next_run.year + 1, month=1)
                                    else:
                                        next_run = next_run.replace(month=next_run.month + 1)

                            if next_run:
                                # Format the date nicely
                                if (next_run - now).days == 0:
                                    next_check = f"Today at {next_run.strftime('%H:%M')}"
                                elif (next_run - now).days == 1:
                                    next_check = f"Tomorrow at {next_run.strftime('%H:%M')}"
                                else:
                                    next_check = next_run.strftime("%b %d %Y at %H:%M")
                                break

            # If no cron schedule found, check disk config
            if next_check == "Unknown":
                # Get disk config from cache if possible
                disk_config_key = self._get_cache_key("disk_config")
                disk_config = self._cache_manager.get(disk_config_key, {})

                if not disk_config:
                    # Try to read disk config
                    result = await self.api.execute_command("cat /boot/config/disk.cfg")
                    if result and result.exit_status == 0:
                        disk_config = {}
                        for line in result.stdout.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                try:
                                    key, value = line.split("=", 1)
                                    disk_config[key] = value.strip('"')
                                except ValueError:
                                    continue

                        # Cache the disk config
                        self._cache_manager.set(
                            disk_config_key,
                            disk_config,
                            ttl=3600,  # 1 hour cache
                            priority=CacheItemPriority.LOW
                        )

                if disk_config:
                    if not disk_config.get("parity.mode") == "4":  # If not manual mode
                        next_check = "Schedule configuration error"
                    else:
                        next_check = "Manual Only"

            return next_check

        except Exception as err:
            _LOGGER.error("Error parsing parity schedule: %s", err)
            return "Unknown"

    def _get_cache_key(self, key_type: str, identifier: str = "") -> str:
        """Generate a standardized cache key."""
        if identifier:
            return f"{key_type}:{self.hostname}:{identifier}"
        return f"{key_type}:{self.hostname}"

    def register_sensor(
        self,
        sensor_id: str,
        category: Optional[SensorCategory] = None,
        priority: Optional[SensorPriority] = None
    ) -> None:
        """Register a sensor with the priority system."""
        self._sensor_manager.register_sensor(sensor_id, category, priority)

    def request_sensor_update(self, sensor_id: str) -> None:
        """Request a specific sensor to be updated in the next update cycle."""
        self._update_requested_sensors.add(sensor_id)

    def get_sensor_stats(self) -> Dict[str, Any]:
        """Get statistics about sensor prioritization."""
        return self._sensor_manager.get_sensor_stats()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about cache usage."""
        return self._cache_manager.get_stats()

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

            # Warm up the cache with initial data
            await self._warm_up_cache()

            # Initialize base system monitoring first
            await self._async_update_data()

            return True

        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err

    async def _warm_up_cache(self) -> None:
        """Warm up the cache with initial data."""
        _LOGGER.debug("Warming up cache with initial data")
        async with self.api:
            try:
                # Fetch hostname first (needed for entity IDs)
                hostname = await self.api.get_hostname()
                if hostname:
                    # Store hostname in a special cache entry
                    self._cache_manager.set(
                        self._get_cache_key("hostname"),
                        hostname,
                        ttl=86400,  # 24 hours - hostname rarely changes
                        priority=CacheItemPriority.CRITICAL
                    )
                    _LOGGER.debug("Cache warmed up with hostname: %s", hostname)

                # Fetch system stats (most critical)
                system_stats = await self.api.get_system_stats()
                if system_stats:
                    self._cache_manager.set(
                        self._get_cache_key("system_stats"),
                        system_stats,
                        ttl=self._cache_ttls["system_stats"],
                        priority=CacheItemPriority.HIGH
                    )
                    _LOGGER.debug("Cache warmed up with system stats")

                # Fetch disk mapping (rarely changes)
                disk_mapping = await self.api.get_disk_mappings()
                if disk_mapping:
                    self._cache_manager.set(
                        self._get_cache_key("disk_mapping"),
                        disk_mapping,
                        ttl=self._cache_ttls["disk_mapping"],
                        priority=CacheItemPriority.LOW
                    )
                    _LOGGER.debug("Cache warmed up with disk mapping")

                # Fetch Docker info if available
                if await self.api.check_docker_running():
                    docker_info = await self.api.get_docker_containers()
                    if docker_info:
                        self._cache_manager.set(
                            self._get_cache_key("docker_info"),
                            docker_info,
                            ttl=self._cache_ttls["docker_info"],
                            priority=CacheItemPriority.MEDIUM
                        )
                        _LOGGER.debug("Cache warmed up with Docker info")
            except Exception as err:
                _LOGGER.warning("Error warming up cache: %s", err)

    async def async_update_ups_status(self, has_ups: bool) -> None:
        """Update the UPS status and trigger a refresh."""
        self.has_ups = has_ups
        await self.async_refresh()

    async def _get_array_state(self) -> Optional[Dict[str, Any]]:
        """Get array state information."""
        try:
            result = await self.api.execute_command("mdcmd status")
            if result.exit_status != 0:
                return None

            array_state = {}
            for line in result.stdout.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                array_state[key.strip()] = value.strip()

            # Parse parity history
            parity_history = await self._parse_parity_history()
            if parity_history:
                array_state["parity_history"] = parity_history

            return array_state

        except Exception as err:
            _LOGGER.error("Error getting array state: %s", err)
            return None

    async def _parse_parity_history(self) -> Optional[Dict[str, Any]]:
        """Parse parity check history from the log file."""
        try:
            _LOGGER.debug("Attempting to read parity check history")
            result = await self.api.execute_command(
                "cat /boot/config/parity-checks.log"
            )
            if result.exit_status != 0:
                _LOGGER.warning(
                    "Failed to read parity history file: exit_code=%d, stderr='%s'",
                    result.exit_status,
                    result.stderr
                )
                return None

            _LOGGER.debug("Raw parity history content: %s", result.stdout)

            latest_check = None
            for line in result.stdout.splitlines():
                # Skip empty lines
                if not line.strip():
                    continue

                # Format can vary:
                # Old: YYYY MMM DD HH:MM:SS|Duration|Speed|Status|Errors
                # New: YYYY MMM DD HH:MM:SS|Duration|Speed|Status|Errors|Type|Size|Duration|Step|Description
                _LOGGER.debug("Processing parity history line: %s", line)

                fields = line.strip().split("|")
                # Minimum required fields: date, duration, speed, status
                if len(fields) < 4:
                    _LOGGER.warning("Invalid parity history line (insufficient fields): %s", line)
                    continue

                try:
                    # Handle different space-separated date formats
                    date_str = fields[0]
                    _LOGGER.debug("Parsing date: %s", date_str)

                    # Try different date formats
                    date_formats = [
                        "%Y %b %d %H:%M:%S",  # Full format with year
                        "%b %d %H:%M:%S"     # Format without year
                    ]

                    check_date = None
                    for date_format in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, date_format)

                            # If the format doesn't include year, assume current year
                            if date_format == "%b %d %H:%M:%S":
                                current_year = datetime.now().year
                                parsed_date = parsed_date.replace(year=current_year)

                                # Handle edge case: if date is in the future, use previous year
                                if parsed_date > datetime.now():
                                    parsed_date = parsed_date.replace(year=current_year-1)

                            check_date = parsed_date
                            break
                        except ValueError:
                            continue

                    if check_date is None:
                        # If all parsing attempts failed, raise an error to be caught by outer exception handler
                        raise ValueError(f"Could not parse date: {date_str}")

                    # Format duration from seconds to readable format
                    try:
                        duration_secs = int(fields[1])
                        hours = duration_secs // 3600
                        minutes = (duration_secs % 3600) // 60
                        seconds = duration_secs % 60
                        duration_str = f"{hours} hours, {minutes} minutes, {seconds} seconds"
                    except ValueError:
                        duration_str = "Unknown"
                        _LOGGER.warning("Could not parse duration value: %s", fields[1])

                    # Parse speed using helper function
                    try:
                        speed_bytes = parse_speed_string(fields[2].strip())
                        speed_mb = round(speed_bytes / 1_000_000, 2)
                    except ValueError as err:
                        _LOGGER.warning("Could not parse speed value: %s - %s", fields[2], err)
                        speed_mb = 0

                    # Get error count (defaults to 0 if not present)
                    try:
                        errors = int(fields[4]) if len(fields) > 4 else 0
                    except ValueError:
                        errors = 0

                    # Build check info with additional fields if available
                    check_info = {
                        "date": check_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "duration": duration_str,
                        "speed": f"{speed_mb} MB/s",
                        "status": "Success" if fields[3] == "0" else f"Failed ({fields[3]} errors)",
                        "errors": errors,
                        "type": fields[5] if len(fields) > 5 else "Unknown",
                        "size": fields[6] if len(fields) > 6 else "Unknown"
                    }

                    # Add description if available (new format)
                    if len(fields) > 9:
                        check_info["description"] = fields[9]

                    _LOGGER.debug("Processed check info: %s", check_info)

                    # Skip invalid dates (like 1969) and update latest check
                    if check_date.year < 2000:
                        _LOGGER.warning("Skipping invalid date: %s", date_str)
                        continue

                    if not latest_check or check_date > datetime.strptime(latest_check["date"], "%Y-%m-%d %H:%M:%S"):
                        latest_check = check_info
                        _LOGGER.debug("Updated latest check info")

                except (ValueError, IndexError) as err:
                    _LOGGER.warning(
                        "Error parsing parity history line '%s': %s",
                        line,
                        err,
                        exc_info=True
                    )
                    continue

            _LOGGER.debug("Final latest check info: %s", latest_check)
            return latest_check

        except Exception as err:
            _LOGGER.error(
                "Error reading parity history: %s",
                err,
                exc_info=True
            )
            return None
