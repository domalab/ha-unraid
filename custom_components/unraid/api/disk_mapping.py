"""Disk mapping utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Dict, Optional, Any

# get_unraid_disk_mapping function moved from helpers.py to avoid circular imports

_LOGGER = logging.getLogger(__name__)

# Note: In the future, all disk mapping should be migrated to use the DiskMapper class
# in disk_mapper.py, which provides more comprehensive disk mapping functionality.

def get_disk_info(data: Dict[str, Any], disk_name: str) -> Optional[Dict[str, Any]]:
    """Get formatted disk information for a specific disk."""
    if not disk_name or "system_stats" not in data:
        return None

    system_stats = data.get("system_stats", {})
    individual_disks = system_stats.get("individual_disks", [])

    # Find disk by name
    disk_data = None
    for disk in individual_disks:
        if disk.get("name") == disk_name:
            disk_data = disk
            break

    if not disk_data:
        return None

    # Get disk mapping if available
    disk_mapping = system_stats.get("disk_mapping", {}).get(disk_name, {})

    # Format the disk information
    formatted_info = {
        "name": disk_name,
        "device": disk_data.get("device") or disk_mapping.get("device", ""),
        "serial": disk_data.get("serial") or disk_mapping.get("serial", ""),
        "mount_point": disk_data.get("mount_point", ""),
        "filesystem": disk_data.get("filesystem", ""),
        "size": {
            "total": disk_data.get("total", 0),
            "used": disk_data.get("used", 0),
            "free": disk_data.get("free", 0),
        },
        "status": _get_disk_status(disk_data),
        "temperature": _extract_temperature(disk_data),
        "smart_status": _extract_smart_status(disk_data),
    }

    return formatted_info

def _get_disk_status(disk_data: Dict[str, Any]) -> str:
    """Get the status of a disk."""
    # Check for standby/spun down status
    if disk_data.get("is_standby", False):
        return "standby"

    # Check for mount status
    if not disk_data.get("mount_point"):
        return "unmounted"

    # Check for disk errors
    if disk_data.get("smart_data", {}).get("overall_health", "") == "FAILED":
        return "error"

    # Default to active
    return "active"

def _extract_temperature(disk_data: Dict[str, Any]) -> Optional[int]:
    """Extract temperature from disk data."""
    # First check direct temperature field
    temp = disk_data.get("temperature")
    if temp is not None:
        try:
            return int(temp)
        except (ValueError, TypeError):
            pass

    # Try to extract from SMART data
    smart_data = disk_data.get("smart_data", {})

    # Check temperature_celsius field first
    temp = smart_data.get("temperature_celsius")
    if temp is not None:
        try:
            return int(temp)
        except (ValueError, TypeError):
            pass

    # Check attributes for temperature value
    for attr in smart_data.get("attributes", []):
        if attr.get("name", "").lower() in ("temperature", "airflow_temperature", "temperature_celsius"):
            try:
                return int(attr.get("value", 0))
            except (ValueError, TypeError):
                pass

    return None

def get_unraid_disk_mapping(system_stats: dict) -> Dict[str, Dict[str, Any]]:
    """Get mapping between Unraid disk names, devices, and serial numbers.

    Note: This function should eventually be migrated to use the DiskMapper class
    in api/disk_mapper.py, which provides more comprehensive disk mapping functionality.
    """
    mapping: Dict[str, Dict[str, Any]] = {}

    # Check for disk data
    individual_disks = system_stats.get("individual_disks", [])
    if not individual_disks:
        _LOGGER.debug("No disk information found in system stats")
        return mapping

    try:
        # Ignore special directories and tmpfs
        ignored_mounts = {
            "disks", "remotes", "addons", "rootshare",
            "user/0", "dev/shm"
        }

        # Filter out disks we want to ignore
        valid_disks = [
            disk for disk in individual_disks
            if (
                disk.get("name")
                and not any(mount in disk.get("mount_point", "") for mount in ignored_mounts)
                and disk.get("filesystem") != "tmpfs"  # Explicitly ignore tmpfs
            )
        ]

        # First, handle array disks (disk1, disk2, etc.)
        base_device = 'b'  # Start at sdb
        array_disks = sorted(
            [disk for disk in valid_disks if disk.get("name", "").startswith("disk")],
            key=lambda x: int(x["name"].replace("disk", ""))
        )

        # Map array disks
        for disk in array_disks:
            disk_name = disk.get("name")
            if disk_name:
                device = f"sd{base_device}"
                mapping[disk_name] = {
                    "device": device,
                    "serial": disk.get("serial", ""),
                    "name": disk_name
                }
                _LOGGER.debug(
                    "Mapped array disk %s to device %s (serial: %s)",
                    disk_name,
                    device,
                    disk.get("serial", "unknown")
                )
                base_device = chr(ord(base_device) + 1)

        # Handle parity disk
        for disk in valid_disks:
            if disk.get("name") == "parity":
                device = disk.get("device")
                if device:
                    mapping["parity"] = {
                        "device": device,
                        "serial": disk.get("serial", ""),
                        "name": "parity"
                    }
                    _LOGGER.debug(
                        "Mapped parity disk to device %s (serial: %s)",
                        device,
                        disk.get("serial", "unknown")
                    )

        # Then handle cache disk if present
        for disk in valid_disks:
            if disk.get("name") == "cache":
                device = disk.get("device")
                if device:
                    mapping["cache"] = {
                        "device": device,
                        "serial": disk.get("serial", ""),
                        "name": "cache"
                    }
                    _LOGGER.debug(
                        "Mapped cache disk to device %s (serial: %s)",
                        device,
                        disk.get("serial", "unknown")
                    )

        return mapping

    except (KeyError, ValueError, AttributeError) as err:
        _LOGGER.debug("Error creating disk mapping: %s", err)
        return mapping


def _extract_smart_status(disk_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract SMART status information."""
    smart_data = disk_data.get("smart_data", {})

    result = {
        "overall_health": smart_data.get("overall_health", "Unknown"),
        "last_test_type": smart_data.get("last_test_type", ""),
        "last_test_status": smart_data.get("last_test_status", ""),
        "errors": [],
    }

    # Extract error information
    for attr in smart_data.get("attributes", []):
        # Check for critical attributes
        if attr.get("when_failed") and attr.get("when_failed") != "-":
            result["errors"].append({
                "id": attr.get("id", 0),
                "name": attr.get("name", "Unknown"),
                "when_failed": attr.get("when_failed", ""),
                "value": attr.get("value", 0),
                "worst": attr.get("worst", 0),
                "threshold": attr.get("threshold", 0),
            })

    return result

async def parse_disks_ini(execute_command) -> Dict[str, Dict[str, Any]]:
    """Parse disks.ini to get disk mappings and info."""
    try:
        result = await execute_command("cat /var/local/emhttp/disks.ini")
        if result.exit_status != 0:
            _LOGGER.debug("Failed to read disks.ini: exit code %d", result.exit_status)
            return {}

        mapping = {}
        current_disk = None
        disk_data = {}

        for line in result.stdout.splitlines():
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # New disk section
            if line.startswith("[") and line.endswith("]"):
                # Save previous disk data if exists
                if current_disk and disk_data:
                    mapping[current_disk] = disk_data

                # Start new disk section
                current_disk = line[1:-1].strip('"')  # Remove [] and quotes
                disk_data = {"name": current_disk}
                continue

            # Parse key=value pairs
            if "=" in line and current_disk:
                key, value = line.split("=", 1)
                key = key.strip().strip('"')
                value = value.strip().strip('"')
                disk_data[key] = value

        # Add last disk if exists
        if current_disk and disk_data:
            mapping[current_disk] = disk_data

        _LOGGER.debug("Parsed disk mappings from disks.ini: %s", mapping)
        return mapping

    except Exception as err:
        _LOGGER.error("Error parsing disks.ini: %s", err)
        return {}

def parse_disk_config(config_content: str) -> Dict[str, Dict[str, str]]:
    """Parse disk.cfg content."""
    config = {}
    try:
        for line in config_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"')

                # Parse disk-specific settings
                if match := re.match(r"disk(IdSlot|FsType)\.(\d+)$", key):
                    setting_type, disk_num = match.groups()
                    disk_key = f"disk{disk_num}"

                    if disk_key not in config:
                        config[disk_key] = {}

                    if setting_type == "IdSlot":
                        config[disk_key]["serial"] = value
                    else:
                        config[disk_key]["filesystem"] = value

                # Global settings
                elif key == "spindownDelay":
                    if "global" not in config:
                        config["global"] = {}
                    config["global"]["spindown_delay"] = value

        return config
    except Exception as err:
        _LOGGER.error("Error parsing disk config: %s", err)
        return {}
