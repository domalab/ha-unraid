"""Consolidated disk mapping utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
import asyncio
from typing import Dict, Optional, Any, Callable, Awaitable, List
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

@dataclass
class DiskIdentifier:
    """Class to hold disk identification information."""
    name: str
    device: Optional[str] = None
    serial: Optional[str] = None
    filesystem: Optional[str] = None
    status: str = "unknown"
    spindown_delay: str = "-1"
    mount_point: Optional[str] = None

class DiskMapper:
    """Class to handle all disk mapping operations."""

    def __init__(self, execute_command: Callable[[str], Awaitable[Any]]):
        """Initialize the disk mapper.

        Args:
            execute_command: Function to execute commands on the Unraid server
        """
        self._execute_command = execute_command
        self._disk_mappings: Dict[str, DiskIdentifier] = {}
        self._device_to_disk: Dict[str, str] = {}
        self._serial_to_disk: Dict[str, str] = {}
        self._cache_valid = False

    async def refresh_mappings(self) -> Dict[str, DiskIdentifier]:
        """Refresh disk mappings from all available sources."""
        try:
            # Get all data sources in parallel
            command_results = await asyncio.gather(
                self._execute_command("cat /var/local/emhttp/disks.ini"),
                self._execute_command("cat /boot/config/disk.cfg"),
                return_exceptions=True
            )

            # Clear existing mappings
            self._disk_mappings = {}
            self._device_to_disk = {}
            self._serial_to_disk = {}

            # Parse disks.ini first (primary source)
            if not isinstance(command_results[0], Exception) and command_results[0].exit_status == 0:
                disks_ini_mappings = await self._parse_disks_ini(command_results[0].stdout)
                for disk_name, disk_info in disks_ini_mappings.items():
                    identifier = DiskIdentifier(
                        name=disk_name,
                        device=disk_info.get("device", ""),
                        serial=disk_info.get("id", ""),  # Serial is in the 'id' field
                        status=disk_info.get("status", "unknown"),
                        filesystem=disk_info.get("fsType", ""),
                        spindown_delay="-1"  # Default, will be updated from disk.cfg
                    )
                    self._disk_mappings[disk_name] = identifier

                    # Update lookup dictionaries
                    if identifier.device:
                        self._device_to_disk[identifier.device] = disk_name
                    if identifier.serial:
                        self._serial_to_disk[identifier.serial] = disk_name

            # Add spindown delays from disk.cfg if needed
            if not isinstance(command_results[1], Exception) and command_results[1].exit_status == 0:
                disk_cfg = self._parse_disk_config(command_results[1].stdout)
                # Update spindown delays in mappings
                for disk_name, config in disk_cfg.items():
                    if disk_name in self._disk_mappings:
                        self._disk_mappings[disk_name].spindown_delay = config.get("spindown_delay", "-1")

            if not self._disk_mappings:
                _LOGGER.warning("No disk mappings found from any source")
            else:
                _LOGGER.debug("Found disk mappings: %s", self._disk_mappings)

            self._cache_valid = True
            return self._disk_mappings

        except Exception as err:
            _LOGGER.error("Error refreshing disk mappings: %s", err)
            self._cache_valid = False
            return {}

    async def get_disk_identifier(self, disk_name: str) -> Optional[DiskIdentifier]:
        """Get disk identifier by name."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return self._disk_mappings.get(disk_name)

    async def get_disk_by_device(self, device: str) -> Optional[DiskIdentifier]:
        """Get disk identifier by device path."""
        if not self._cache_valid:
            await self.refresh_mappings()

        disk_name = self._device_to_disk.get(device)
        if disk_name:
            return self._disk_mappings.get(disk_name)
        return None

    async def get_disk_by_serial(self, serial: str) -> Optional[DiskIdentifier]:
        """Get disk identifier by serial number."""
        if not self._cache_valid:
            await self.refresh_mappings()

        disk_name = self._serial_to_disk.get(serial)
        if disk_name:
            return self._disk_mappings.get(disk_name)
        return None

    async def get_all_disks(self) -> Dict[str, DiskIdentifier]:
        """Get all disk identifiers."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return self._disk_mappings

    async def get_array_disks(self) -> List[DiskIdentifier]:
        """Get all array disks (disk1, disk2, etc)."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return [disk for name, disk in self._disk_mappings.items()
                if name.startswith("disk") and name[4:].isdigit()]

    async def get_parity_disks(self) -> List[DiskIdentifier]:
        """Get all parity disks (parity, parity2)."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return [disk for name, disk in self._disk_mappings.items()
                if name == "parity" or name == "parity2"]

    async def get_cache_disks(self) -> List[DiskIdentifier]:
        """Get all cache disks (cache, cache2, etc)."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return [disk for name, disk in self._disk_mappings.items()
                if name.startswith("cache")]

    async def get_pool_disks(self) -> List[DiskIdentifier]:
        """Get all pool disks (not array, parity, or cache)."""
        if not self._cache_valid:
            await self.refresh_mappings()

        return [disk for name, disk in self._disk_mappings.items()
                if not (name.startswith("disk") or
                        name == "parity" or name == "parity2" or
                        name.startswith("cache"))]

    async def map_logical_to_physical_device(self, device_path: str) -> str:
        """Map logical md devices to physical devices."""
        if "md" not in device_path:
            return device_path

        # Extract md number
        md_num = None
        if match := re.search(r'md(\d+)', device_path):
            md_num = match.group(1)

        if not md_num:
            return device_path

        # Get the physical device for this md device from array information
        array_info = await self._execute_command("mdcmd status")
        if array_info.exit_status != 0:
            return device_path

        # Parse the output to find the physical device
        try:
            for line in array_info.stdout.splitlines():
                if f"diskNumber.{md_num}" in line:
                    # Found the disk number, now get the device
                    for device_line in array_info.stdout.splitlines():
                        if f"rdevName.{md_num}" in device_line:
                            device_name = device_line.split('=')[1].strip()
                            if device_name:
                                return f"/dev/{device_name}"
        except Exception as err:
            _LOGGER.warning("Error mapping logical device %s: %s", device_path, err)

        return device_path

    async def _parse_disks_ini(self, content: str) -> Dict[str, Dict[str, Any]]:
        """Parse disks.ini content to get disk mappings and info."""
        try:
            mapping = {}
            current_disk = None
            disk_data = {}

            for line in content.splitlines():
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

            return mapping

        except Exception as err:
            _LOGGER.error("Error parsing disks.ini: %s", err)
            return {}

    def _parse_disk_config(self, config_content: str) -> Dict[str, Dict[str, Any]]:
        """Parse disk.cfg to get disk configuration."""
        try:
            config = {}

            for line in config_content.splitlines():
                line = line.strip()

                # Skip empty lines and comments
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

    def get_disk_info_from_system_stats(self, system_stats: Dict[str, Any], disk_name: str) -> Optional[Dict[str, Any]]:
        """Get formatted disk information for a specific disk from system stats."""
        if not disk_name or not system_stats:
            return None

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
            "status": self._get_disk_status(disk_data),
            "temperature": self._extract_temperature(disk_data),
            "smart_status": self._extract_smart_status(disk_data),
        }

        return formatted_info

    def _get_disk_status(self, disk_data: Dict[str, Any]) -> str:
        """Extract disk status from disk data."""
        if not disk_data:
            return "unknown"

        # Check for explicit status field
        if status := disk_data.get("status"):
            return status.lower()

        # Infer status from other fields
        if disk_data.get("mounted") is True:
            return "mounted"
        elif disk_data.get("mounted") is False:
            return "unmounted"

        return "unknown"

    def _extract_temperature(self, disk_data: Dict[str, Any]) -> Optional[int]:
        """Extract temperature from disk data."""
        if not disk_data:
            return None

        # Check for temperature field
        temp = disk_data.get("temperature")
        if temp is not None:
            try:
                return int(temp)
            except (ValueError, TypeError):
                pass

        # Check for smart data
        smart_data = disk_data.get("smart_data", {})
        if temp := smart_data.get("temperature"):
            try:
                return int(temp)
            except (ValueError, TypeError):
                pass

        return None

    def _extract_smart_status(self, disk_data: Dict[str, Any]) -> str:
        """Extract SMART status from disk data."""
        if not disk_data:
            return "Unknown"

        # Check for smart_status field
        if status := disk_data.get("smart_status"):
            return status

        # Check for smart data
        smart_data = disk_data.get("smart_data", {})
        if status := smart_data.get("status"):
            return "Passed" if status else "Failed"

        return "Unknown"

    def extract_smart_data(self, smart_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant SMART data for display."""
        if not smart_data:
            return {}

        result = {
            "status": smart_data.get("smart_status", False),
            "temperature": smart_data.get("temperature"),
            "power_on_hours": smart_data.get("power_on_hours"),
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
