"""Binary sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore

from .const import DOMAIN
from .diagnostics.base import UnraidBinarySensorBase
from .diagnostics.disk import UnraidArrayDiskSensor
from .diagnostics.pool import UnraidPoolDiskSensor
from .diagnostics.parity import UnraidParityDiskSensor, UnraidParityCheckSensor
from .diagnostics.ups import UnraidUPSBinarySensor
from .diagnostics.array import UnraidArrayStatusBinarySensor, UnraidArrayHealthSensor
from .diagnostics.const import SENSOR_DESCRIPTIONS
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def _get_parity_info(coordinator: UnraidDataUpdateCoordinator) -> Optional[Dict[str, Any]]:
    """Get parity disk information from mdcmd status."""
    try:
        result = await coordinator.api.execute_command("mdcmd status")
        if result.exit_status != 0:
            return None

        parity_info = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in [
                "diskNumber.0", "diskName.0", "diskSize.0", "diskState.0",
                "diskId.0", "rdevNumber.0", "rdevStatus.0", "rdevName.0",
                "rdevOffset.0", "rdevSize.0", "rdevId.0"
            ]:
                parity_info[key] = value

        # Only return if we found valid parity info
        if "rdevName.0" in parity_info and "diskState.0" in parity_info:
            return parity_info

        return None

    except Exception as err:
        _LOGGER.error("Error getting parity disk info: %s", err)
        return None

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensors."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[UnraidBinarySensorBase] = []
    processed_disks = set()  # Track processed disks

    # Add base sensors first
    for description in SENSOR_DESCRIPTIONS:
        entities.append(UnraidBinarySensorBase(coordinator, description))
        _LOGGER.debug(
            "Added binary sensor | description_key: %s | name: %s",
            description.key,
            description.name,
        )

    # Add Array Status binary sensor
    entities.append(UnraidArrayStatusBinarySensor(coordinator))
    _LOGGER.debug("Added Array Status binary sensor")

    # Add Array Health binary sensor
    entities.append(UnraidArrayHealthSensor(coordinator))
    _LOGGER.debug("Added Array Health binary sensor")

    # Add UPS sensor if UPS info is available
    if coordinator.data.get("system_stats", {}).get("ups_info"):
        entities.append(UnraidUPSBinarySensor(coordinator))
        _LOGGER.debug("Added UPS binary sensor")

    # Check for and add parity-related sensors
    parity_info = await _get_parity_info(coordinator)
    if parity_info:
        # Store parity info in coordinator data
        coordinator.data["parity_info"] = parity_info

        # Add parity disk sensor
        entities.append(UnraidParityDiskSensor(coordinator, parity_info))
        _LOGGER.debug(
            "Added parity disk sensor | device: %s",
            parity_info.get("rdevName.0")
        )

        # Add parity check sensor
        entities.append(UnraidParityCheckSensor(coordinator))
        _LOGGER.debug(
            "Added parity check sensor for %s",
            coordinator.hostname
        )

    # Filter out tmpfs and special mounts
    ignored_mounts = {
        "disks", "remotes", "addons", "rootshare",
        "user/0", "dev/shm"
    }

    # Process disk health sensors
    disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])
    valid_disks = [
        disk for disk in disk_data
        if (
            disk.get("name")
            and not any(mount in disk.get("mount_point", "") for mount in ignored_mounts)
            and disk.get("filesystem") != "tmpfs"
        )
    ]

    # First process array disks
    for disk in valid_disks:
        disk_name = disk.get("name")
        if not disk_name or disk_name in processed_disks:
            continue

        if disk_name.startswith("disk"):
            try:
                entities.append(
                    UnraidArrayDiskSensor(
                        coordinator=coordinator,
                        disk_name=disk_name
                    )
                )
                processed_disks.add(disk_name)
                _LOGGER.info(
                    "Added array disk sensor: %s",
                    disk_name
                )
            except ValueError as err:
                _LOGGER.warning("Skipping invalid array disk %s: %s", disk_name, err)
                continue

    # Then process pool disks
    for disk in valid_disks:
        disk_name = disk.get("name")
        if not disk_name or disk_name in processed_disks:
            continue

        if not disk_name.startswith("disk"):
            try:
                entities.append(
                    UnraidPoolDiskSensor(
                        coordinator=coordinator,
                        disk_name=disk_name
                    )
                )
                processed_disks.add(disk_name)
                _LOGGER.info(
                    "Added pool disk sensor: %s",
                    disk_name
                )
            except ValueError as err:
                _LOGGER.warning("Skipping invalid pool disk %s: %s", disk_name, err)
                continue

    async_add_entities(entities)
