"""SMART operations for Unraid."""
from __future__ import annotations

import json
import logging
import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from enum import IntEnum

from .disk_mapper import DiskMapper
from .error_handling import with_error_handling, safe_parse
from .usb_detection import USBFlashDriveDetector

_LOGGER = logging.getLogger(__name__)

class SmartctlExitCode(IntEnum):
    """Smartctl exit codes."""
    SUCCESS = 0
    COMMAND_LINE_ERROR = 1
    DEVICE_OPEN_ERROR = 2
    SMART_OR_ATA_ERROR = 3
    SMART_TEST_ERROR = 4
    SMART_READ_ERROR = 5
    SMART_PREFAIL_ERROR = 6

class SmartDataManager:
    """Manager for SMART data operations."""

    def __init__(self, instance: Any):
        self._instance = instance
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timeout = timedelta(minutes=5)  # Default fallback
        self._last_update: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._disk_mapper = DiskMapper(instance.execute_command)
        self._usb_detector = USBFlashDriveDetector(instance)

        # Granular cache timeouts for real-time monitoring
        self._cache_timeouts = {
            "temperature": timedelta(minutes=1),    # 1 minute for temperature monitoring
            "power_state": timedelta(seconds=30),   # 30 seconds for power state changes
            "health_status": timedelta(minutes=10), # 10 minutes for health status
            "static_info": timedelta(hours=1),      # 1 hour for model, serial, etc.
        }

    def _convert_nvme_temperature(self, temp_value: Any) -> Optional[int]:
        """Convert NVMe temperature to Celsius with enhanced format detection."""
        if not temp_value:
            return None

        try:
            # Handle string values with units
            if isinstance(temp_value, str):
                temp_str = temp_value.lower().strip()

                # Handle complex strings like "45 Celsius" or "318 Kelvin"
                import re
                # Extract number and unit
                match = re.search(r'(\d+(?:\.\d+)?)\s*([cfk]|celsius|fahrenheit|kelvin)?', temp_str)
                if match:
                    num = float(match.group(1))
                    unit = match.group(2) or ''

                    if 'f' in unit or 'fahrenheit' in unit:  # Fahrenheit
                        return int((num - 32) * 5/9)
                    elif 'k' in unit or 'kelvin' in unit:  # Kelvin
                        return int(num - 273.15)
                    else:  # Assume Celsius
                        return int(num)
                else:
                    # Fallback: extract just the number
                    num_match = re.search(r'(\d+(?:\.\d+)?)', temp_str)
                    if num_match:
                        temp = float(num_match.group(1))
                    else:
                        return None

            # Handle numeric values
            temp = float(temp_value)

            # Enhanced temperature conversion logic
            # NVMe drives can report temperature in various formats:

            # 1. Kelvin (typically 273-400 range)
            if temp > 273 and temp < 400:
                temp = temp - 273.15
                _LOGGER.debug("Converting from Kelvin: %.1fK -> %d°C", temp + 273.15, int(temp))

            # 2. Tenths of a degree Celsius (typically 200-800 range)
            elif temp > 150 and temp < 1000:
                temp = temp / 10
                _LOGGER.debug("Converting from tenths of degree: %.1f -> %d°C", temp * 10, int(temp))

            # 3. Hundredths of a degree (typically 2000-8000 range)
            elif temp > 1000:
                temp = temp / 100
                _LOGGER.debug("Converting from hundredths of degree: %.1f -> %d°C", temp * 100, int(temp))

            # Validate temperature range (-40°C to 125°C for SSDs/NVMe)
            if -40 <= temp <= 125:
                return int(temp)

            _LOGGER.warning(
                "Temperature %.1f°C outside expected range (-40°C to 125°C) - raw value: %s",
                temp,
                temp_value
            )
            return None

        except (TypeError, ValueError) as err:
            _LOGGER.debug("Temperature conversion error for value '%s': %s", temp_value, err)
            return None

    async def _map_logical_to_physical_device(self, device_path: str) -> str:
        """Map logical md devices to physical devices using DiskMapper."""
        # Use the DiskMapper to handle the mapping
        return await self._disk_mapper.map_logical_to_physical_device(device_path)

    @with_error_handling(fallback_return={
        "state": "error",
        "error": "Failed to get SMART data",
        "temperature": None,
        "device_type": "unknown"
    })
    async def get_smart_data(
        self,
        device: str,
        force_refresh: bool = False
        ) -> Dict[str, Any]:
        """Get SMART data for a disk with enhanced data processing."""
        async with self._lock:
            now = datetime.now(timezone.utc)

            # Format device path correctly
            device_path = device
            if not device.startswith('/dev/'):
                if device.startswith('sd'):
                    device_path = f"/dev/{device}"
                elif device.startswith('nvme'):
                    device_path = f"/dev/{device}"
                elif device == "cache":
                    device_path = "/dev/nvme0n1"
                elif device.startswith("disk"):
                    try:
                        disk_num = int(''.join(filter(str.isdigit, device)))
                        device_path = f"/dev/sd{chr(ord('b') + disk_num - 1)}"
                    except ValueError:
                        _LOGGER.error("Invalid disk number in %s", device)
                        return {"state": "error", "error": "Invalid device name", "temperature": None}
                else:
                    _LOGGER.error("Unrecognized device format: %s", device)
                    return {"state": "error", "error": "Invalid device name", "temperature": None}

            # Strip partition numbers from device path for SMART data collection
            # For example, convert /dev/nvme0n1p1 to /dev/nvme0n1
            if 'nvme' in device_path and 'p' in device_path:
                original_device_path = device_path
                device_path = re.sub(r'(nvme\d+n\d+)p\d+', r'\1', device_path)
                _LOGGER.debug("Stripped partition number from NVME device path: %s -> %s",
                            original_device_path, device_path)

                # Validate that the base NVME device actually exists
                try:
                    check_cmd = f"test -e {device_path}"
                    check_result = await self._instance.execute_command(check_cmd)
                    if check_result.exit_status != 0:
                        _LOGGER.debug(
                            "NVME base device %s does not exist (derived from %s), skipping SMART data collection",
                            device_path, original_device_path
                        )
                        return {
                            "state": "unavailable",
                            "error": f"Base NVME device {device_path} not found",
                            "smart_status": "unknown",
                            "temperature": None,
                            "device_type": "nvme"
                        }
                except Exception as err:
                    _LOGGER.warning("Failed to check NVME device existence for %s: %s", device_path, err)

            # Enhanced USB device detection and classification
            try:
                usb_info = await self._usb_detector.detect_usb_device(device_path)

                if usb_info.is_usb:
                    # Check if this USB device supports SMART monitoring
                    if not usb_info.supports_smart:
                        # USB flash drive - skip SMART monitoring
                        device_description = "USB boot drive" if usb_info.is_boot_drive else "USB flash drive"

                        _LOGGER.info(
                            "Detected %s at %s (type: %s, confidence: %.2f, method: %s) - skipping SMART data collection",
                            device_description, device_path, usb_info.device_type, usb_info.confidence, usb_info.detection_method
                        )

                        usb_data = {
                            "state": "usb_device",
                            "error": f"{device_description} doesn't support SMART monitoring",
                            "smart_status": "passed",  # Assume passed for USB flash drives
                            "temperature": None,
                            "device_type": usb_info.device_type,
                            "usb_info": {
                                "is_boot_drive": usb_info.is_boot_drive,
                                "mount_point": usb_info.mount_point,
                                "filesystem": usb_info.filesystem,
                                "model": usb_info.model,
                                "vendor": usb_info.vendor,
                                "size": usb_info.size,
                                "transport": usb_info.transport_type,
                                "detection_confidence": usb_info.confidence,
                                "detection_method": usb_info.detection_method,
                                "supports_smart": usb_info.supports_smart
                            }
                        }

                        self._cache[device_path] = usb_data
                        self._last_update[device_path] = now
                        return usb_data
                    else:
                        # USB storage drive - proceed with SMART monitoring
                        _LOGGER.debug(
                            "Detected USB storage drive at %s (type: %s, confidence: %.2f) - proceeding with SMART collection",
                            device_path, usb_info.device_type, usb_info.confidence
                        )
                else:
                    _LOGGER.debug(
                        "Device %s is not USB (confidence: %.2f, transport: %s) - proceeding with SMART collection",
                        device_path, usb_info.confidence, usb_info.transport_type
                    )

            except Exception as err:
                _LOGGER.warning(
                    "USB detection failed for %s: %s - proceeding with SMART collection",
                    device_path, err
                )

            # Cache check
            if not force_refresh and device_path in self._cache:
                last_update = self._last_update.get(device_path)
                if last_update and (now - last_update) < self._cache_timeout:
                    _LOGGER.debug("Using cached SMART data for %s (age: %s)",
                                device_path, now - last_update)
                    return self._cache[device_path]

            _LOGGER.debug("SMART data request for device %s (path: %s, force_refresh=%s)",
                        device, device_path, force_refresh)

            try:
                # Map logical device to physical device if needed
                try:
                    physical_device = await self._map_logical_to_physical_device(device_path)
                    if physical_device != device_path:
                        _LOGGER.debug("Using physical device %s instead of logical device %s",
                                    physical_device, device_path)
                        device_path = physical_device
                except Exception as err:
                    _LOGGER.warning("Error mapping device, using original: %s", err)

                is_nvme = "nvme" in str(device_path).lower()
                _LOGGER.debug("Device %s detected as: type=%s", device_path,
                            "NVMe" if is_nvme else "SATA")

                if not is_nvme:
                    # Standby check for SATA
                    _LOGGER.debug("Checking standby state for SATA device %s", device_path)
                    result = await self._instance.execute_command(f"smartctl -n standby -j {device_path}")

                    _LOGGER.debug("SATA standby check for %s: exit_code=%d, stdout=%s",
                                device_path, result.exit_status, result.stdout)

                    is_standby = result.exit_status == 2

                    if is_standby:
                        _LOGGER.debug("Device %s confirmed in standby", device_path)
                        standby_data = {
                            "state": "standby",
                            "smart_status": "passed",  # Assume passed for standby disks
                            "temperature": None,
                            "device_type": "sata"
                        }
                        self._cache[device_path] = standby_data
                        self._last_update[device_path] = now
                        return standby_data

                # Get SMART data
                if is_nvme:
                    # Extract nvme index from device path first
                    nvme_index = '0'  # Default
                    if match := re.search(r'nvme(\d+)', device_path):
                        nvme_index = match.group(1)

                    # Try NVMe smart-log command first
                    smart_cmd = f"nvme smart-log -o json /dev/nvme{nvme_index}n1"
                    result = await self._instance.execute_command(smart_cmd)

                    if result.exit_status != 0:
                        # Fallback to smartctl if nvme command fails
                        smart_cmd = f"smartctl -d nvme -a -j /dev/nvme{nvme_index}n1"
                        result = await self._instance.execute_command(smart_cmd)
                else:
                    # Use -a instead of -A for SATA devices to get full attributes including temperature
                    smart_cmd = f"smartctl -a -j {device_path}"

                _LOGGER.debug("Executing SMART command for %s: %s", device_path, smart_cmd)
                result = await self._instance.execute_command(smart_cmd)

                if result.exit_status == 0:
                    try:
                        smart_data = safe_parse(
                            json.loads,
                            result.stdout,
                            default={},
                            error_msg=f"Failed to parse SMART JSON for {device_path}"
                        )
                        _LOGGER.debug("Successfully parsed SMART data for %s", device)

                        # Get SMART status and convert boolean to string
                        smart_passed = smart_data.get("smart_status", {}).get("passed", True)
                        smart_status = "passed" if smart_passed else "failed"

                        processed_data = {
                            "smart_status": smart_status,
                            "temperature": None,
                            "power_on_hours": None,
                            "attributes": {},
                            "device_type": "nvme" if is_nvme else "sata",
                            "state": "active"
                        }

                        # Get temperature based on device type
                        if is_nvme:
                            # Enhanced NVMe temperature handling with multiple detection methods
                            temp = None
                            if isinstance(smart_data, dict):
                                # Method 1: NVMe smart health information log
                                nvme_data = smart_data.get("nvme_smart_health_information_log", {})
                                if isinstance(nvme_data, dict):
                                    temp = self._convert_nvme_temperature(nvme_data.get("temperature"))
                                    if temp is not None:
                                        _LOGGER.debug("NVMe temp from health log: %d°C", temp)

                                # Method 2: Direct temperature field
                                if temp is None and "temperature" in smart_data:
                                    temp_data = smart_data["temperature"]
                                    if isinstance(temp_data, dict):
                                        # Try multiple sub-fields
                                        for field in ["current", "value", "celsius"]:
                                            if field in temp_data:
                                                temp = self._convert_nvme_temperature(temp_data[field])
                                                if temp is not None:
                                                    _LOGGER.debug("NVMe temp from temperature.%s: %d°C", field, temp)
                                                    break
                                    elif isinstance(temp_data, (int, float)):
                                        temp = self._convert_nvme_temperature(temp_data)
                                        if temp is not None:
                                            _LOGGER.debug("NVMe temp from direct temperature: %d°C", temp)

                                # Method 3: Check for other common NVMe temperature fields
                                if temp is None:
                                    temp_fields = [
                                        "composite_temperature",
                                        "controller_temperature",
                                        "current_temperature",
                                        "temp",
                                        "thermal_state"
                                    ]
                                    for field in temp_fields:
                                        if field in smart_data:
                                            temp = self._convert_nvme_temperature(smart_data[field])
                                            if temp is not None:
                                                _LOGGER.debug("NVMe temp from %s: %d°C", field, temp)
                                                break

                            if temp is not None:
                                processed_data["temperature"] = int(temp)
                                _LOGGER.debug(
                                    "NVMe temperature for %s: %d°C",
                                    device,
                                    processed_data["temperature"]
                                )
                            else:
                                _LOGGER.debug("No temperature data found for NVMe device %s", device)
                        else:
                            # Enhanced SATA SSD temperature detection
                            temp = None

                            # Try direct temperature field first
                            if temp_data := smart_data.get("temperature"):
                                if isinstance(temp_data, dict):
                                    temp = temp_data.get("current")
                                elif isinstance(temp_data, (int, float)):
                                    temp = temp_data

                                if temp is not None:
                                    processed_data["temperature"] = int(temp)
                                    _LOGGER.debug(
                                        "SATA temperature for %s: %d°C (direct)",
                                        device,
                                        temp
                                    )

                            # If no direct temperature, search SMART attributes with enhanced patterns
                            if temp is None:
                                # Common temperature attribute names for SSDs and HDDs
                                temp_attr_names = [
                                    "Temperature_Celsius",
                                    "Airflow_Temperature_Cel",
                                    "Temperature_Case",
                                    "Temperature_Internal",
                                    "Drive_Temperature",
                                    "Current_Temperature",
                                    "Temperature"
                                ]

                                for attr in smart_data.get("ata_smart_attributes", {}).get("table", []):
                                    attr_name = attr.get("name", "")

                                    # Check if this is a temperature attribute
                                    if attr_name in temp_attr_names:
                                        # Try different value extraction methods
                                        raw_data = attr.get("raw", {})

                                        # Method 1: Direct value
                                        if temp_val := raw_data.get("value"):
                                            temp = temp_val
                                        # Method 2: String parsing for complex raw values
                                        elif raw_str := raw_data.get("string"):
                                            # Parse strings like "45 (Min/Max 20/55)" or "45 C"
                                            match = re.search(r'(\d+)', str(raw_str))
                                            if match:
                                                temp = int(match.group(1))
                                        # Method 3: Normalized value as fallback
                                        elif norm_val := attr.get("value"):
                                            # Some SSDs report temperature in normalized value
                                            if 0 <= norm_val <= 150:  # Reasonable temperature range
                                                temp = norm_val

                                        if temp is not None:
                                            processed_data["temperature"] = int(temp)
                                            _LOGGER.debug(
                                                "SATA temperature for %s: %d°C (attribute: %s)",
                                                device,
                                                temp,
                                                attr_name
                                            )
                                            break

                        # Update cache
                        self._cache[device] = processed_data
                        self._last_update[device] = now
                        return processed_data

                    except json.JSONDecodeError as err:
                        _LOGGER.error(
                            "Failed to parse SMART data for %s: %s",
                            device,
                            err
                        )
                        error_data = {
                            "state": "error",
                            "error": "JSON parse failed",
                            "temperature": None
                        }
                        self._cache[device] = error_data
                        self._last_update[device] = now
                        return error_data

                # Provide more user-friendly error messages based on exit code
                if result.exit_status == SmartctlExitCode.DEVICE_OPEN_ERROR:
                    _LOGGER.debug(
                        "SMART data unavailable for %s (device not accessible, may be in standby or partition)",
                        device
                    )
                elif result.exit_status == SmartctlExitCode.SMART_TEST_ERROR:
                    # Exit code 4 is common for NVME partitions that don't exist as base devices
                    if 'nvme' in device.lower() and 'p' in device:
                        _LOGGER.debug(
                            "SMART data unavailable for NVME partition %s (base device may not exist)",
                            device
                        )
                    else:
                        _LOGGER.info(
                            "SMART self-test in progress for %s, data temporarily unavailable",
                            device
                        )
                elif result.exit_status == SmartctlExitCode.SMART_OR_ATA_ERROR:
                    _LOGGER.warning(
                        "SMART reports potential issues for %s (exit_code=%d) - check disk health",
                        device,
                        result.exit_status
                    )
                else:
                    _LOGGER.warning(
                        "SMART command failed for %s: exit_code=%d",
                        device,
                        result.exit_status
                    )
                error_data = {
                    "state": "error",
                    "error": f"Command failed: {result.exit_status}",
                    "temperature": None
                }
                self._cache[device] = error_data
                self._last_update[device] = now
                return error_data

            except Exception as err:
                _LOGGER.error(
                    "Error getting SMART data for %s: %s",
                    device,
                    err,
                    exc_info=True
                )
                error_data = {
                    "state": "error",
                    "error": str(err),
                    "temperature": None
                }
                self._cache[device] = error_data
                self._last_update[device] = now
                return error_data

    async def get_usb_detection_stats(self) -> Dict[str, Any]:
        """Get USB detection statistics for debugging and monitoring."""
        try:
            # Get cache stats from USB detector
            usb_stats = self._usb_detector.get_cache_stats()

            # Get all USB devices detected in the system
            all_usb_devices = await self._usb_detector.get_all_usb_devices()

            return {
                "usb_detector_stats": usb_stats,
                "detected_usb_devices": [
                    {
                        "device_path": device.device_path,
                        "is_usb": device.is_usb,
                        "device_type": device.device_type,
                        "is_boot_drive": device.is_boot_drive,
                        "supports_smart": device.supports_smart,
                        "transport": device.transport_type,
                        "mount_point": device.mount_point,
                        "model": device.model,
                        "vendor": device.vendor,
                        "confidence": device.confidence,
                        "detection_method": device.detection_method
                    }
                    for device in all_usb_devices
                ],
                "smart_cache_entries": len(self._cache),
                "usb_devices_in_smart_cache": len([
                    entry for entry in self._cache.values()
                    if entry.get("device_type") in ["usb", "usb_flash_drive", "usb_storage_drive"]
                ])
            }
        except Exception as err:
            _LOGGER.error("Error getting USB detection stats: %s", err)
            return {"error": str(err)}

    def clear_usb_cache(self) -> None:
        """Clear USB detection cache (useful for testing or troubleshooting)."""
        self._usb_detector.clear_cache()
        _LOGGER.info("USB detection cache cleared")