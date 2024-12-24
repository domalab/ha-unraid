"""SMART operations for Unraid."""
from __future__ import annotations

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
import re
from typing import Dict, Any, Optional
from enum import IntEnum

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
        self._cache_timeout = timedelta(minutes=5)
        self._last_update: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    def _convert_nvme_temperature(self, temp_value: Any) -> Optional[int]:
        """Convert NVMe temperature to Celsius with enhanced format detection."""
        if not temp_value:
            return None
            
        try:
            # Handle string values with units
            if isinstance(temp_value, str):
                temp_str = temp_value.lower().strip()
                # Extract numeric value and handle units
                num = float(''.join(filter(str.isdigit, temp_str)))
                if 'f' in temp_str:  # Fahrenheit
                    return int((num - 32) * 5/9)
                elif 'k' in temp_str:  # Kelvin
                    return int(num - 273)
                elif 'c' in temp_str:  # Celsius
                    return int(num)
                    
            # Handle numeric values
            temp = float(temp_value)
            
            # Convert Kelvin if needed (typically > 273)
            if temp > 100:
                temp = temp - 273
                _LOGGER.debug("Converting from Kelvin: %dK -> %d°C", temp + 273, temp)
            
            # Expanded validation range (-40°C to 125°C)
            if -40 <= temp <= 125:
                return int(temp)
            
            _LOGGER.warning(
                "Temperature %d°C outside expected range (-40°C to 125°C) - raw value: %s",
                temp,
                temp_value
            )
            return None
                
        except (TypeError, ValueError) as err:
            _LOGGER.error("Temperature conversion error for value '%s': %s", temp_value, err)
            return None
    
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
                            "smart_status": "Unknown",
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
                    smart_cmd = f"smartctl -A -j {device_path}"

                _LOGGER.debug("Executing SMART command for %s: %s", device_path, smart_cmd)
                result = await self._instance.execute_command(smart_cmd)
                
                if result.exit_status == 0:
                    try:
                        smart_data = json.loads(result.stdout)
                        _LOGGER.debug("Successfully parsed SMART data for %s", device)

                        processed_data = {
                            "smart_status": smart_data.get("smart_status", {}).get("passed", True),
                            "temperature": None,
                            "power_on_hours": None,
                            "attributes": {},
                            "device_type": "nvme" if is_nvme else "sata",
                            "state": "active"
                        }

                        # Get temperature based on device type
                        if is_nvme:
                            # Enhanced NVMe temperature handling
                            temp = None
                            if isinstance(smart_data, dict):
                                # Try different temperature field locations
                                nvme_data = smart_data.get("nvme_smart_health_information_log", {})
                                if isinstance(nvme_data, dict):
                                    temp = self._convert_nvme_temperature(nvme_data.get("temperature"))
                                
                                if temp is None and "temperature" in smart_data:
                                    temp_data = smart_data["temperature"]
                                    if isinstance(temp_data, dict):
                                        temp = self._convert_nvme_temperature(temp_data.get("current"))
                                    elif isinstance(temp_data, (int, float)):
                                        temp = self._convert_nvme_temperature(temp_data)

                            processed_data["temperature"] = temp

                            if temp is not None:
                                processed_data["temperature"] = int(temp)
                                _LOGGER.debug(
                                    "NVMe temperature for %s: %d°C",
                                    device,
                                    processed_data["temperature"]
                                )
                        else:
                            # Try direct temperature field first
                            if temp := smart_data.get("temperature", {}).get("current"):
                                processed_data["temperature"] = temp
                                _LOGGER.debug(
                                    "SATA temperature for %s: %d°C (direct)",
                                    device,
                                    temp
                                )
                            else:
                                # Fallback to attributes
                                for attr in smart_data.get("ata_smart_attributes", {}).get("table", []):
                                    if attr.get("name") == "Temperature_Celsius":
                                        if temp := attr.get("raw", {}).get("value"):
                                            processed_data["temperature"] = temp
                                            _LOGGER.debug(
                                                "SATA temperature for %s: %d°C (attribute)",
                                                device,
                                                temp
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