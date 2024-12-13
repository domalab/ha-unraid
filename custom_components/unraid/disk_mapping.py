"""Disk mapping utilities for Unraid integration."""
from typing import Dict, Any
import logging

from .helpers import format_bytes

_LOGGER = logging.getLogger(__name__)

def get_unraid_disk_mapping(data: dict) -> Dict[str, str]:
    """Map Unraid disks to their device paths and serial numbers."""
    mapping = {}

    try:
        # Get disk information from system stats
        for disk in data.get("system_stats", {}).get("individual_disks", []):
            name = disk.get("name", "")
            device = disk.get("device", "")
            serial = disk.get("serial", "")  # Get serial number if available

            # Skip if missing essential info
            if not name or not device:
                continue

            # Map array disk (disk1, disk2, etc)
            if name.startswith("disk"):
                mapping[name] = {
                    "device": device,
                    "serial": serial
                }

            # Map parity disk
            elif name == "parity":
                mapping["parity"] = {
                    "device": device,
                    "serial": serial
                }

            # Map cache disk(s)
            elif name.startswith("cache"):
                mapping[name] = {
                    "device": device,
                    "serial": serial
                }

        return mapping

    except (KeyError, TypeError, AttributeError) as err:
        _LOGGER.error("Error mapping disks: %s", err)
        return {}

def get_disk_info(data: dict, disk_name: str) -> Dict[str, Any]:
    """Get information for a specific disk."""
    try:
        # Find disk in system stats
        for disk in data.get("system_stats", {}).get("individual_disks", []):
            if disk.get("name") == disk_name:
                # Basic disk information
                info = {
                    "device": disk.get("device", "unknown"),
                    "serial": disk.get("serial", "unknown"),
                    "temperature": f"{disk.get('temperature', '0')}°C",
                }

                # Usage information
                info.update({
                    "current_usage": f"{disk.get('percentage', 0):.1f}%",
                    "total_size": format_bytes(disk.get("total", 0)),
                    "used_space": format_bytes(disk.get("used", 0)),
                    "free_space": format_bytes(disk.get("free", 0)),
                })

                # Status information
                info.update({
                    "smart_status": disk.get("health", "Unknown"),
                    "disk_status": disk.get("status", "unknown"),
                    "spin_down_delay": disk.get("spin_down_delay", "unknown"),
                })

                return info

        return {}

    except (KeyError, TypeError, AttributeError) as err:
        _LOGGER.error("Error getting disk info for %s: %s", disk_name, err)
        return {}