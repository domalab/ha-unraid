"""Disk mapping utilities for Unraid integration."""
import re
from typing import Dict, Any
import logging

from ..helpers import format_bytes

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