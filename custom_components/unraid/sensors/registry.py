"""Sensor registry for Unraid integration."""
from __future__ import annotations

import logging
from typing import Dict, List, Any, Callable, Optional, Set

from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ..coordinator import UnraidDataUpdateCoordinator
from .factory import SensorFactory
from .const import UnraidSensorEntityDescription
from .base import UnraidSensorBase
from ..const import DOMAIN
from ..helpers import EntityNaming
from .metadata import get_sensor_description

_LOGGER = logging.getLogger(__name__)


def register_system_sensors() -> None:
    """Register system sensors with the factory."""
    from .system import (
        UnraidCPUUsageSensor,
        UnraidRAMUsageSensor,
        UnraidUptimeSensor,
        UnraidCPUTempSensor,
        UnraidMotherboardTempSensor,
        UnraidDockerVDiskSensor,
        UnraidLogFileSystemSensor,
        UnraidBootUsageSensor,
        UnraidFanSensor,
    )

    # Register sensor types
    SensorFactory.register_sensor_type("cpu_usage", UnraidCPUUsageSensor)
    SensorFactory.register_sensor_type("ram_usage", UnraidRAMUsageSensor)
    SensorFactory.register_sensor_type("uptime", UnraidUptimeSensor)
    SensorFactory.register_sensor_type("cpu_temp", UnraidCPUTempSensor)
    SensorFactory.register_sensor_type("motherboard_temp", UnraidMotherboardTempSensor)
    SensorFactory.register_sensor_type("docker_vdisk", UnraidDockerVDiskSensor)
    SensorFactory.register_sensor_type("log_filesystem", UnraidLogFileSystemSensor)
    SensorFactory.register_sensor_type("boot_usage", UnraidBootUsageSensor)
    SensorFactory.register_sensor_type("fan", UnraidFanSensor)

    # Register creator functions
    SensorFactory.register_sensor_creator(
        "system_sensors",
        create_system_sensors,
        group="system"
    )


def register_storage_sensors() -> None:
    """Register storage sensors with the factory."""
    from .storage import (
        UnraidArraySensor,
        UnraidDiskSensor,
        UnraidPoolSensor,
    )

    # Register sensor types
    SensorFactory.register_sensor_type("array", UnraidArraySensor)
    SensorFactory.register_sensor_type("disk", UnraidDiskSensor)
    SensorFactory.register_sensor_type("pool", UnraidPoolSensor)

    # Register creator functions
    SensorFactory.register_sensor_creator(
        "storage_sensors",
        create_storage_sensors,
        group="storage"
    )


def register_network_sensors() -> None:
    """Register network sensors with the factory."""
    from .network import UnraidNetworkSensor

    # Register sensor types
    SensorFactory.register_sensor_type("network", UnraidNetworkSensor)

    # Register creator functions
    SensorFactory.register_sensor_creator(
        "network_sensors",
        create_network_sensors,
        group="network"
    )


def register_ups_sensors() -> None:
    """Register UPS sensors with the factory."""
    from .ups import (
        UnraidUPSCurrentPowerSensor,
        UnraidUPSEnergyConsumption,
        UnraidUPSLoadPercentage,
    )

    # Register sensor types
    SensorFactory.register_sensor_type("ups_power", UnraidUPSCurrentPowerSensor)
    SensorFactory.register_sensor_type("ups_energy", UnraidUPSEnergyConsumption)
    SensorFactory.register_sensor_type("ups_load", UnraidUPSLoadPercentage)

    # Register creator functions
    SensorFactory.register_sensor_creator(
        "ups_sensors",
        create_ups_sensors,
        group="ups"
    )


def create_system_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create system sensors."""
    from .system import (
        UnraidCPUUsageSensor,
        UnraidRAMUsageSensor,
        UnraidUptimeSensor,
        UnraidCPUTempSensor,
        UnraidMotherboardTempSensor,
        UnraidDockerVDiskSensor,
        UnraidLogFileSystemSensor,
        UnraidBootUsageSensor,
        UnraidFanSensor,
    )

    entities = [
        UnraidCPUUsageSensor(coordinator),
        UnraidRAMUsageSensor(coordinator),
        UnraidUptimeSensor(coordinator),
        UnraidCPUTempSensor(coordinator),
        UnraidMotherboardTempSensor(coordinator),
        UnraidDockerVDiskSensor(coordinator),
        UnraidLogFileSystemSensor(coordinator),
        UnraidBootUsageSensor(coordinator),
    ]

    # Add fan sensors if available
    fan_data = (
        coordinator.data.get("system_stats", {})
        .get("temperature_data", {})
        .get("fans", {})
    )

    if fan_data:
        for fan_id, fan_info in fan_data.items():
            entities.append(
                UnraidFanSensor(coordinator, fan_id, fan_info)
            )
            _LOGGER.debug(
                "Added fan sensor: %s (%s)",
                fan_id,
                fan_info.get("label", "unknown")
            )

    return entities


def create_storage_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create storage sensors."""
    from .storage import (
        UnraidArraySensor,
        UnraidDiskSensor,
        UnraidPoolSensor,
        get_disk_number,
        is_solid_state_drive,
        get_pool_info,
    )

    entities = []

    # Add array sensor
    entities.append(UnraidArraySensor(coordinator))

    try:
        disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])
        if not isinstance(disk_data, list):
            _LOGGER.error("Invalid disk data format - expected list")
            disk_data = []

        # Define ignored mounts and filesystem types
        ignored_mounts = {
            "disks", "remotes", "addons", "rootshare",
            "user/0", "dev/shm"
        }

        # Track processed disks
        processed_disks = set()

        # Sort and process array disks (spinning drives)
        array_disks = []
        solid_state_disks = []

        # Get pool information
        pool_info = get_pool_info(coordinator.data.get("system_stats", {}))

        # First pass - categorize disks
        for disk in disk_data:
            if not isinstance(disk, dict):
                continue

            disk_name = disk.get("name", "")
            if not disk_name:
                continue

            # Skip ignored mounts
            mount_point = disk.get("mount_point", "")
            if any(ignored in mount_point for ignored in ignored_mounts):
                continue

            # Route disk to appropriate list based on type
            if is_solid_state_drive(disk):
                solid_state_disks.append(disk)
            elif disk_name.startswith("disk"):
                try:
                    disk_num = get_disk_number(disk_name)
                    if disk_num is not None:
                        array_disks.append((disk_num, disk))
                except ValueError:
                    _LOGGER.warning("Invalid disk number format: %s", disk_name)

        # Process spinning drives with UnraidDiskSensor
        for _, disk in sorted(array_disks, key=lambda x: x[0]):
            try:
                disk_name = disk.get("name", "")
                if disk_name not in processed_disks:
                    entities.append(
                        UnraidDiskSensor(
                            coordinator=coordinator,
                            disk_name=disk_name
                        )
                    )
                    processed_disks.add(disk_name)
                    _LOGGER.debug("Added spinning disk sensor: %s", disk_name)
            except ValueError as err:
                _LOGGER.warning("Error adding disk sensor: %s", err)

        # Process solid state drives with UnraidPoolSensor
        for disk in solid_state_disks:
            try:
                disk_name = disk.get("name", "")
                if disk_name not in processed_disks:
                    entities.append(
                        UnraidPoolSensor(
                            coordinator=coordinator,
                            pool_name=disk_name
                        )
                    )
                    processed_disks.add(disk_name)
                    _LOGGER.debug("Added SSD sensor: %s", disk_name)
            except ValueError as err:
                _LOGGER.warning("Error adding SSD sensor: %s", err)

        # Then handle pools
        for pool_name in pool_info:
            try:
                if pool_name not in processed_disks:
                    # Log detailed pool information for debugging
                    _LOGGER.info(
                        "Processing pool: %s, filesystem: %s, mount: %s",
                        pool_name,
                        pool_info[pool_name].get("filesystem", "unknown"),
                        pool_info[pool_name].get("mount_point", "unknown")
                    )

                    # Create sensor for the pool
                    entities.append(
                        UnraidPoolSensor(
                            coordinator=coordinator,
                            pool_name=pool_name
                        )
                    )
                    processed_disks.add(pool_name)
                    _LOGGER.info("Added pool sensor: %s", pool_name)
            except ValueError as err:
                _LOGGER.warning("Error adding pool sensor: %s", err)

    except Exception as err:
        _LOGGER.error("Error setting up storage sensors: %s", err, exc_info=True)

    return entities


def create_network_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create network sensors."""
    from .network import UnraidNetworkSensor, VALID_INTERFACE_PATTERN, EXCLUDED_INTERFACES
    import re

    entities = []

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
            entities.append(
                UnraidNetworkSensor(coordinator, interface, "inbound")
            )
            # Add outbound sensor
            entities.append(
                UnraidNetworkSensor(coordinator, interface, "outbound")
            )

    return entities


def create_ups_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create UPS sensors."""
    from .ups import (
        UnraidUPSCurrentPowerSensor,
        UnraidUPSEnergyConsumption,
        UnraidUPSLoadPercentage,
    )

    entities = []

    if coordinator.has_ups:
        entities.extend([
            UnraidUPSCurrentPowerSensor(coordinator),
            UnraidUPSEnergyConsumption(coordinator),
            UnraidUPSLoadPercentage(coordinator),
        ])

    return entities


def register_all_sensors() -> None:
    """Register all sensor types with the factory."""
    register_system_sensors()
    register_storage_sensors()
    register_network_sensors()
    register_ups_sensors()
