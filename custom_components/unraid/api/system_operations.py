"""System operations for Unraid."""
from __future__ import annotations

import logging
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass

import asyncio
import asyncssh # type: ignore

from .network_operations import NetworkOperationsMixin
from .error_handling import with_error_handling, safe_parse
from .raid_detection import RAIDControllerDetector
from .power_monitoring import CPUPowerMonitor
from ..utils import format_bytes, extract_fans_data
from ..const import (
    TEMP_WARN_THRESHOLD,
    TEMP_CRIT_THRESHOLD,
)

class CommandExecutor(Protocol):
    """Protocol for classes that can execute SSH commands."""

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None
    ) -> asyncssh.SSHCompletedProcess:
        """Execute a command on the remote server."""
        ...

_LOGGER = logging.getLogger(__name__)

@dataclass
class ArrayState:
    """Unraid array state information."""
    state: str
    num_disks: int
    num_disabled: int
    num_invalid: int
    num_missing: int
    synced: bool
    sync_action: Optional[str] = None
    sync_progress: float = 0.0
    sync_errors: int = 0

class SystemOperationsMixin(CommandExecutor):
    """Mixin for system-related operations."""

    def __init__(self) -> None:
        """Initialize system operations."""
        self._network_ops: Optional[NetworkOperationsMixin] = None
        self._fan_hardware_available: Optional[bool] = None  # Cache fan hardware detection
        self._raid_detector: Optional[RAIDControllerDetector] = None
        self._power_monitor: Optional[CPUPowerMonitor] = None

    def set_network_ops(self, network_ops: NetworkOperationsMixin) -> None:
        """Set network operations instance."""
        self._network_ops = network_ops

    def _detect_fan_hardware_availability(self, sensors_dict: Dict[str, Dict[str, Any]]) -> bool:
        """
        Detect if the system has fan hardware by checking sensor data.
        This is a lightweight check to determine if we should attempt fan parsing.
        """
        if not sensors_dict:
            return False

        # Quick scan for any fan-related keywords in sensor data
        fan_keywords = ['fan', 'cooling', 'rpm']

        for device, readings in sensors_dict.items():
            if not isinstance(readings, dict):
                continue

            device_lower = device.lower()
            # Check device names for fan-related terms
            if any(keyword in device_lower for keyword in fan_keywords):
                return True

            # Check sensor keys for fan-related terms
            for key in readings.keys():
                key_lower = key.lower()
                if any(keyword in key_lower for keyword in fan_keywords):
                    return True

        return False

    def _extract_fans_data_optimized(self, sensors_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Optimized fan data extraction with hardware detection caching.
        """
        # Check cached fan hardware availability
        if self._fan_hardware_available is False:
            # We've already determined this system has no fan hardware
            _LOGGER.debug("Skipping fan detection - no fan hardware detected previously")
            return {}

        # If we haven't checked yet, or we know fans exist, proceed with detection
        if self._fan_hardware_available is None:
            # First time - detect if fan hardware is available
            self._fan_hardware_available = self._detect_fan_hardware_availability(sensors_dict)
            if not self._fan_hardware_available:
                _LOGGER.debug("No fan hardware detected - caching result to skip future checks")
                return {}
            else:
                _LOGGER.debug("Fan hardware detected - will continue monitoring")

        # Fan hardware is available, extract fan data
        return extract_fans_data(sensors_dict)

    def reset_fan_hardware_cache(self) -> None:
        """
        Reset the fan hardware detection cache.
        Useful for edge cases where hardware configuration changes.
        """
        self._fan_hardware_available = None
        _LOGGER.debug("Fan hardware detection cache reset")

    async def get_raid_controller_info(self) -> Dict[str, Any]:
        """
        Get RAID controller information and recommendations.

        Returns advisory information about RAID controllers since Unraid
        works best with individual disk access (JBOD/IT mode).
        """
        try:
            if self._raid_detector is None:
                self._raid_detector = RAIDControllerDetector(self.execute_command)

            controllers = await self._raid_detector.detect_raid_controllers()
            advisory = self._raid_detector.get_raid_advisory()

            _LOGGER.debug("RAID controller detection complete: %s", advisory["message"])
            return advisory

        except Exception as err:
            _LOGGER.error("Error detecting RAID controllers: %s", err)
            return {
                "status": "error",
                "message": "Failed to detect RAID controllers",
                "controllers": [],
                "recommendations": []
            }

    async def get_cpu_power_info(self) -> Dict[str, Any]:
        """
        Get CPU power monitoring information.

        Safely detects and returns CPU power consumption data from
        Intel RAPL or AMD sensors without risking system stability.
        """
        try:
            if self._power_monitor is None:
                self._power_monitor = CPUPowerMonitor(self.execute_command)

            power_summary = await self._power_monitor.get_power_summary()
            _LOGGER.debug("CPU power monitoring: %s", power_summary["source"])
            return power_summary

        except Exception as err:
            _LOGGER.debug("Error getting CPU power info: %s", err)
            return {
                "supported": False,
                "source": "error",
                "total_power": None,
                "package_power": None,
                "core_power": None,
                "uncore_power": None,
                "dram_power": None,
                "power_limit": None
            }

    @with_error_handling(fallback_return={})
    async def get_system_stats(self) -> Dict[str, Any]:
        """Fetch system statistics from the Unraid server.

        This method uses a batched command approach to efficiently collect
        all system statistics in a single SSH command.
        """
        _LOGGER.debug("Fetching system stats from Unraid server")

        # Use the optimized batched command approach
        system_stats = await self.collect_system_stats()
        if system_stats:
            return system_stats

        # If batched command fails, return empty dict (handled by error_handling decorator)
        _LOGGER.warning("System stats collection failed")
        return {}

    async def _parse_array_state(self) -> ArrayState:
        """Parse detailed array state from mdcmd output."""
        try:
            result = await self.execute_command("mdcmd status")
            if result.exit_status != 0:
                return ArrayState(
                    state="unknown",
                    num_disks=0,
                    num_disabled=0,
                    num_invalid=0,
                    num_missing=0,
                    synced=False
                )

            # Parse mdcmd output
            state_dict = {}
            for line in result.stdout.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    state_dict[key] = value.strip()

            return ArrayState(
                state=state_dict.get("mdState", "UNKNOWN").upper(),
                num_disks=int(state_dict.get("mdNumDisks", 0)),
                num_disabled=int(state_dict.get("mdNumDisabled", 0)),
                num_invalid=int(state_dict.get("mdNumInvalid", 0)),
                num_missing=int(state_dict.get("mdNumMissing", 0)),
                synced=bool(int(state_dict.get("sbSynced", 0))),
                sync_action=state_dict.get("mdResyncAction"),
                sync_progress=float(state_dict.get("mdResync", 0)),
                sync_errors=int(state_dict.get("mdResyncCorr", 0))
            )

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error parsing array state: %s", err)
            return ArrayState(
                state="ERROR",
                num_disks=0,
                num_disabled=0,
                num_invalid=0,
                num_missing=0,
                synced=False
            )

    async def _get_array_status(self) -> str:
        """Get Unraid array status using mdcmd."""
        try:
            result = await self.execute_command("mdcmd status")
            if result.exit_status != 0:
                return "unknown"

            # Parse mdcmd output
            status_lines = result.stdout.splitlines()
            status_dict = {}
            for line in status_lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    status_dict[key] = value

            # Check array state
            if status_dict.get("mdState") == "STARTED":
                return "started"
            elif status_dict.get("mdState") == "STOPPED":
                return "stopped"
            else:
                return status_dict.get("mdState", "unknown").lower()

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error getting array status: %s", err)
            return "error"

    async def _get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information with caching and robust error handling.

        Returns:
            Dict containing:
                - cpu_arch: CPU architecture (e.g. x86_64)
                - cpu_cores: Number of CPU cores
                - cpu_model: CPU model name
                - cpu_threads_per_core: Number of threads per core
                - cpu_sockets: Number of physical CPU sockets
                - cpu_max_freq: Maximum CPU frequency in MHz
                - cpu_min_freq: Minimum CPU frequency in MHz
        """
        cache_key = "_cpu_info_cache"
        cache_time_key = "_cpu_info_cache_time"

        # Check cache age - refresh every 24 hours
        if hasattr(self, cache_key) and hasattr(self, cache_time_key):
            cache_age = datetime.now() - getattr(self, cache_time_key)
            if cache_age.total_seconds() < 86400:  # 24 hours
                return getattr(self, cache_key)

        try:
            # Get detailed CPU info using lscpu -J
            result = await self.execute_command("lscpu -J")
            if result.exit_status != 0:
                raise RuntimeError(f"lscpu command failed: {result.stderr}")

            cpu_data = json.loads(result.stdout)

            # Helper function to safely extract values from lscpu output
            def get_lscpu_value(field_name: str) -> Optional[str]:
                for entry in cpu_data.get("lscpu", []):
                    if entry.get("field", "").startswith(field_name):
                        return entry.get("data")
                return None

            # Extract relevant CPU information
            cpu_info = {
                "cpu_arch": get_lscpu_value("Architecture:") or "unknown",
                "cpu_cores": int(get_lscpu_value("CPU(s):") or 0),
                "cpu_model": get_lscpu_value("Model name:") or "unknown",
                "cpu_threads_per_core": int(get_lscpu_value("Thread(s) per core:") or 0),
                "cpu_sockets": int(get_lscpu_value("Socket(s):") or 0),
                "cpu_max_freq": float(get_lscpu_value("CPU max MHz:") or 0),
                "cpu_min_freq": float(get_lscpu_value("CPU min MHz:") or 0),
            }

            # Validate core count with fallback methods if needed
            if cpu_info["cpu_cores"] == 0:
                # Fallback 1: Try nproc
                nproc_result = await self.execute_command("nproc")
                if nproc_result.exit_status == 0:
                    cpu_info["cpu_cores"] = int(nproc_result.stdout.strip())
                else:
                    # Fallback 2: Count processors in /proc/cpuinfo
                    cpu_count_result = await self.execute_command(
                        "cat /proc/cpuinfo | grep -c processor"
                    )
                    if cpu_count_result.exit_status == 0:
                        cpu_info["cpu_cores"] = int(cpu_count_result.stdout.strip())

            # Validate architecture with fallback
            if cpu_info["cpu_arch"] == "unknown":
                arch_result = await self.execute_command("uname -m")
                if arch_result.exit_status == 0:
                    cpu_info["cpu_arch"] = arch_result.stdout.strip()

            # Get CPU temperature if available
            try:
                temp_result = await self.execute_command(
                    "sensors -j 2>/dev/null | grep -i 'core[[:space:]]*[0-9]' -A1 | grep 'input' | awk '{print $2}' | tr -d ',' | sort -rn | head -n1"
                )
                if temp_result.exit_status == 0:
                    temp = float(temp_result.stdout.strip())
                    if 0 <= temp <= 125:  # Reasonable CPU temp range
                        cpu_info["cpu_temp"] = temp
                        cpu_info["cpu_temp_warning"] = temp >= TEMP_WARN_THRESHOLD
                        cpu_info["cpu_temp_critical"] = temp >= TEMP_CRIT_THRESHOLD
            except (ValueError, OSError) as err:
                _LOGGER.debug("Could not get CPU temperature: %s", err)

            # Cache the results with timestamp
            setattr(self, cache_key, cpu_info)
            setattr(self, cache_time_key, datetime.now())

            return cpu_info

        except json.JSONDecodeError as err:
            _LOGGER.error("Error parsing lscpu JSON output: %s", err)
            return await self._get_fallback_cpu_info()
        except (OSError, RuntimeError) as err:
            _LOGGER.error("Error getting CPU info: %s", err)
            return await self._get_fallback_cpu_info()

    async def _get_fallback_cpu_info(self) -> Dict[str, Any]:
        """Fallback method to get basic CPU info if primary method fails.

        Uses a single command to get all required information to reduce SSH calls.
        """
        try:
            # Get basic CPU info using a single command
            cmd = (
                "echo '===ARCH==='; uname -m; "
                "echo '===CORES==='; nproc; "
                "echo '===MODEL==='; cat /proc/cpuinfo | grep 'model name' | head -n1 | cut -d':' -f2"
            )
            result = await self.execute_command(cmd)

            # Default values
            cpu_info = {
                "cpu_arch": "unknown",
                "cpu_cores": 0,
                "cpu_model": "unknown",
                "cpu_threads_per_core": 0,
                "cpu_sockets": 0,
                "cpu_max_freq": 0,
                "cpu_min_freq": 0,
            }

            if result.exit_status == 0:
                # Parse the output
                lines = result.stdout.strip().split('\n')
                section = None

                for line in lines:
                    if line == '===ARCH===':
                        section = 'arch'
                    elif line == '===CORES===':
                        section = 'cores'
                    elif line == '===MODEL===':
                        section = 'model'
                    elif section == 'arch' and line.strip():
                        cpu_info['cpu_arch'] = line.strip()
                    elif section == 'cores' and line.strip():
                        try:
                            cpu_info['cpu_cores'] = int(line.strip())
                        except ValueError:
                            pass
                    elif section == 'model' and line.strip():
                        cpu_info['cpu_model'] = line.strip()

            return cpu_info
        except Exception as err:
            _LOGGER.error("Error getting fallback CPU info: %s", err)
            return {
                "cpu_arch": "unknown",
                "cpu_cores": 0,
                "cpu_model": "unknown",
                "cpu_threads_per_core": 0,
                "cpu_sockets": 0,
                "cpu_max_freq": 0,
                "cpu_min_freq": 0,
            }

    async def _get_cpu_usage(self) -> Optional[float]:
        """Fetch CPU usage information from the Unraid system.

        Returns:
            Float between 0-100 representing total CPU usage percentage,
            or None if the data could not be retrieved.
        """
        try:
            _LOGGER.debug("Fetching CPU usage")

            # Get per-CPU usage stats
            result = await self.execute_command(
                "top -bn1 | grep '^%Cpu' | awk '{print 100 - $8}'"
            )

            if result.exit_status != 0:
                _LOGGER.error("CPU usage command failed with exit status %d", result.exit_status)
                return None

            try:
                # Parse and validate usage percentage
                usage = float(result.stdout.strip())
                if 0 <= usage <= 100:
                    return round(usage, 2)

                _LOGGER.warning("CPU usage outside valid range (0-100): %f", usage)
                return None

            except ValueError as err:
                _LOGGER.error("Failed to parse CPU usage from output '%s': %s",
                            result.stdout.strip(), err)
                return None

        except (asyncssh.Error, asyncio.TimeoutError) as err:
            _LOGGER.error("Connection error getting CPU usage: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Unexpected error getting CPU usage: %s", err)
            return None

    async def _get_memory_usage(self) -> Dict[str, Any]:
        """Fetch RAM information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching memory usage from /proc/meminfo")
            result = await self.execute_command("cat /proc/meminfo")
            if result.exit_status != 0:
                _LOGGER.error("Memory usage command failed with exit status %d", result.exit_status)
                return {"percentage": None}

            # Parse meminfo into a dictionary
            memory_info = {}
            for line in result.stdout.splitlines():
                try:
                    key, value = line.split(':')
                    # Convert kB to bytes and strip 'kB'
                    value = int(value.strip().split()[0]) * 1024
                    memory_info[key.strip()] = value
                except (ValueError, IndexError):
                    continue

            # Calculate memory values
            total = memory_info.get('MemTotal', 0)
            free = memory_info.get('MemFree', 0)
            cached = memory_info.get('Cached', 0)
            buffers = memory_info.get('Buffers', 0)
            available = memory_info.get('MemAvailable', 0)

            # Calculate used memory (total - free - cached - buffers)
            used = total - free - cached - buffers

            # Validate values to prevent division by zero or negative values
            if total <= 0:
                _LOGGER.error("Invalid total memory value: %d", total)
                return {"percentage": None}

            # Format values for reporting
            memory_stats = {
                "percentage": round((used / total) * 100, 2),
                "total": format_bytes(total),
                "used": format_bytes(used),
                "free": format_bytes(free),
                "cached": format_bytes(cached),
                "buffers": format_bytes(buffers),
                "available": format_bytes(available),
            }

            _LOGGER.debug("Memory stats calculated: %s", memory_stats)
            return memory_stats

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error getting memory usage: %s", err)
            return {"percentage": None}

    async def _get_boot_usage(self) -> Dict[str, Optional[float]]:
        """Fetch boot information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching boot usage")
            result = await self.execute_command("df -k /boot | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error("Boot usage command failed with exit status %d", result.exit_status)
                return {"percentage": None, "total": None, "used": None, "free": None}

            total, used, free = map(int, result.stdout.strip().split())
            percentage = (used / total) * 100 if total > 0 else 0

            return {
                "percentage": float(round(percentage, 2)),
                "total": total * 1024,  # Convert to bytes
                "used": used * 1024,    # Convert to bytes
                "free": free * 1024     # Convert to bytes
            }
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting boot usage: %s", str(e))
            return {"percentage": None, "total": None, "used": None, "free": None}

    async def _get_uptime(self) -> Optional[float]:
        """Fetch Uptime information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching uptime")
            result = await self.execute_command("awk '{print $1}' /proc/uptime")
            if result.exit_status != 0:
                _LOGGER.error("Uptime command failed with exit status %d", result.exit_status)
                return None

            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return float(match.group(1))
            else:
                _LOGGER.error("Failed to parse uptime from output: %s", result.stdout)
                return None
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting uptime: %s", str(e))
            return None

    async def _get_cache_usage(self) -> Dict[str, Any]:
        """Fetch cache information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching cache usage")
            # First check if cache is mounted
            cache_check = await self.execute_command("mountpoint -q /mnt/cache")
            if cache_check.exit_status != 0:
                _LOGGER.debug("Cache is not mounted, skipping usage check")
                return {
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0,
                    "status": "not_mounted"
                }

            result = await self.execute_command("df -k /mnt/cache | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.debug("Cache usage command failed, cache might not be available")
                return {
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0,
                    "status": "error"
                }

            output = result.stdout.strip()
            if not output:
                return {
                    "percentage": 0,
                    "total": 0,
                    "used": 0,
                    "free": 0,
                    "status": "empty"
                }

            total, used, free = map(int, output.split())
            percentage = (used / total) * 100 if total > 0 else 0

            return {
                "percentage": float(round(percentage, 2)),
                "total": total * 1024,  # Convert to bytes
                "used": used * 1024,    # Convert to bytes
                "free": free * 1024,    # Convert to bytes
                "status": "mounted"
            }

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting cache usage: %s", str(e))
            return {
                "percentage": 0,
                "total": 0,
                "used": 0,
                "free": 0,
                "status": "error"
            }

    async def _get_log_filesystem_usage(self) -> Dict[str, Any]:
        """Fetch log filesystem information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching log filesystem usage")
            result = await self.execute_command("df -k /var/log | awk 'NR==2 {print $2,$3,$4,$5}'")
            if result.exit_status != 0:
                _LOGGER.error("Log filesystem usage command failed with exit status %d", result.exit_status)
                return {}

            total, used, free, percentage = result.stdout.strip().split()
            return {
                "total": int(total) * 1024,
                "used": int(used) * 1024,
                "free": int(free) * 1024,
                "percentage": float(percentage.strip('%'))
            }
        except (asyncssh.Error, OSError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.error("Error getting log filesystem usage: %s", str(err))
            return {}

    @with_error_handling(fallback_return={})
    async def get_temperature_data(self) -> Dict[str, Any]:
        """Fetch temperature information from the Unraid system."""
        temp_data = {}

        # Get sensors data
        _LOGGER.debug("Fetching temperature data")
        try:
            result = await self.execute_command("sensors")
            if result.exit_status == 0:
                # Parse sensors output
                sensors_dict = safe_parse(
                    self._parse_sensors_output,
                    result.stdout,
                    default={},
                    error_msg="Error parsing sensors output"
                )
                temp_data['sensors'] = sensors_dict

                # Extract fan data
                fans = safe_parse(
                    extract_fans_data,
                    sensors_dict,
                    default={},
                    error_msg="Error extracting fan data"
                )
                if fans:
                    temp_data['fans'] = fans
                    _LOGGER.debug("Found fans: %s", list(fans.keys()))
                else:
                    _LOGGER.debug("No fans found in sensor data")
        except Exception as err:
            _LOGGER.warning("Error getting sensors data: %s", err)

        # Get thermal zone data
        try:
            result = await self.execute_command("paste <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp)")
            if result.exit_status == 0:
                temp_data['thermal_zones'] = safe_parse(
                    self._parse_thermal_zones,
                    result.stdout,
                    default={},
                    error_msg="Error parsing thermal zones"
                )
        except Exception as err:
            _LOGGER.warning("Error getting thermal zone data: %s", err)

        return temp_data

    def _parse_sensors_output(self, output: str) -> Dict[str, Dict[str, str]]:
        """Parse the output of the sensors command."""
        sensors_data = {}
        current_sensor = None
        key_counters = {}  # Track duplicate keys per sensor

        for line in output.splitlines():
            if ':' not in line:
                current_sensor = line.strip()
                sensors_data[current_sensor] = {}
                key_counters[current_sensor] = {}  # Initialize counters for this sensor
            else:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.split('(')[0].strip()

                # Handle duplicate keys by adding a number
                if key in sensors_data[current_sensor]:
                    key_counters[current_sensor][key] = key_counters[current_sensor].get(key, 1) + 1
                    key = f"{key} #{key_counters[current_sensor][key]}"

                sensors_data[current_sensor][key] = value

        return sensors_data

    def _parse_thermal_zones(self, output: str) -> Dict[str, float]:
        """Parse the output of the thermal zones command."""
        thermal_zones = {}
        for line in output.splitlines():
            try:
                parts = line.split()
                if len(parts) >= 2:
                    zone_type, temp = parts[0], parts[1]
                    thermal_zones[zone_type] = float(temp) / 1000  # Convert milli-Celsius to Celsius
                else:
                    _LOGGER.debug("Skipping malformed thermal zone line: %s", line)
            except (ValueError, IndexError) as err:
                _LOGGER.debug("Error parsing thermal zone data: %s (line: %s)", err, line)
        return thermal_zones

    def _parse_intel_gpu_data(self, gpu_output: str, device_info: str) -> Dict[str, Any] | None:
        """Parse Intel GPU data from intel_gpu_top output and device info."""
        try:
            gpu_output = gpu_output.strip()
            device_info = device_info.strip()

            _LOGGER.debug("Intel GPU raw output: '%s'", gpu_output)
            _LOGGER.debug("Intel GPU device info: '%s'", device_info)

            # Check if Intel GPU is available
            if gpu_output in ('not_available', 'command_failed', '') or device_info == 'no_intel_gpu':
                _LOGGER.debug("Intel GPU not available: output='%s', device_info='%s'", gpu_output, device_info)
                return None

            gpu_data: Dict[str, Any] = {
                "usage_percentage": 0.0,
                "model": "Unknown Intel GPU",
                "driver_version": "Unknown",
                "power_watts": None,
                "frequency_mhz": None,
                "memory_used_mb": None,
                "memory_total_mb": None,
                "engines": {}
            }

            # Parse device info from lspci
            if device_info and device_info != 'no_intel_gpu':
                # Extract GPU model from lspci output
                # Example: "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630 (rev 02)"
                if 'Intel Corporation' in device_info:
                    model_match = re.search(r'Intel Corporation (.+?)(?:\s+\(rev|\s*$)', device_info)
                    if model_match:
                        gpu_data["model"] = f"Intel {model_match.group(1).strip()}"

            # Parse intel_gpu_top JSON output
            if gpu_output and gpu_output not in ('not_available', 'command_failed', 'no_pci_device'):
                try:
                    # intel_gpu_top outputs JSON array with multiple objects, need to handle properly
                    # Based on gpustat-unraid plugin approach
                    stdout = gpu_output.strip()

                    # Fix the JSON format - intel_gpu_top outputs invalid JSON with missing commas
                    # The output looks like: [{\n}\n{\n}] instead of [{\n},{\n}]
                    try:
                        # First try to parse as-is in case the format is fixed in newer versions
                        json_array = json.loads(stdout)
                    except json.JSONDecodeError:
                        # Fix the missing comma between JSON objects
                        _LOGGER.debug("Fixing malformed JSON from intel_gpu_top")
                        # Replace }{ with },{ to fix the JSON array format
                        fixed_json = stdout.replace('}\n{', '},\n{').replace('}\r\n{', '},\r\n{').replace('}\r{', '},\r{')
                        try:
                            json_array = json.loads(fixed_json)
                        except json.JSONDecodeError as e:
                            _LOGGER.debug("Failed to parse fixed JSON: %s", e)
                            return self._parse_intel_gpu_text_fallback(stdout, gpu_data)

                    if isinstance(json_array, list) and len(json_array) >= 2:
                        # Use the second JSON object (first sample is usually incomplete)
                        gpu_json = json_array[1]
                        _LOGGER.debug("Using second JSON object from intel_gpu_top output")
                    elif isinstance(json_array, list) and len(json_array) == 1:
                        # Use the only available object
                        gpu_json = json_array[0]
                        _LOGGER.debug("Using single JSON object from intel_gpu_top output")
                    elif isinstance(json_array, dict):
                        # Single object, use as-is
                        gpu_json = json_array
                        _LOGGER.debug("Using direct JSON object from intel_gpu_top output")
                    else:
                        _LOGGER.warning("Unexpected JSON format from intel_gpu_top: %s", type(json_array))
                        return None

                    _LOGGER.debug("Successfully parsed Intel GPU JSON data")

                    # Extract overall GPU usage from engines
                    if 'engines' in gpu_json:
                        engines = gpu_json['engines']
                        total_usage = 0.0
                        engine_count = 0
                        max_usage = 0.0

                        # Parse individual engine usage
                        for engine_name, engine_data in engines.items():
                            if isinstance(engine_data, dict) and 'busy' in engine_data:
                                usage = float(engine_data['busy'])
                                gpu_data["engines"][engine_name] = round(usage, 1)
                                total_usage += usage
                                engine_count += 1
                                max_usage = max(max_usage, usage)

                        # Use maximum engine usage as overall GPU usage (like gpustat plugin)
                        if engine_count > 0:
                            gpu_data["usage_percentage"] = round(max_usage, 1)

                    # Extract frequency information
                    if 'frequency' in gpu_json:
                        freq_data = gpu_json['frequency']
                        if isinstance(freq_data, dict) and 'actual' in freq_data:
                            gpu_data["frequency_mhz"] = int(freq_data['actual'])

                    # Extract power information (handle both old and new formats)
                    if 'power' in gpu_json:
                        power_data = gpu_json['power']
                        if isinstance(power_data, dict):
                            # New format with GPU and Package power
                            if 'GPU' in power_data:
                                gpu_data["power_watts"] = round(float(power_data['GPU']), 1)
                            elif 'Package' in power_data:
                                gpu_data["power_watts"] = round(float(power_data['Package']), 1)
                            # Old format with single value
                            elif 'value' in power_data:
                                gpu_data["power_watts"] = round(float(power_data['value']), 1)

                    # Extract IMC bandwidth information
                    if 'imc-bandwidth' in gpu_json:
                        imc_data = gpu_json['imc-bandwidth']
                        if isinstance(imc_data, dict):
                            if 'reads' in imc_data:
                                gpu_data["memory_bandwidth_read"] = round(float(imc_data['reads']), 2)
                            if 'writes' in imc_data:
                                gpu_data["memory_bandwidth_write"] = round(float(imc_data['writes']), 2)

                except json.JSONDecodeError as err:
                    _LOGGER.debug("Failed to parse intel_gpu_top JSON output: %s", err)
                    # Fallback: try to parse text output if JSON parsing fails
                    return self._parse_intel_gpu_text_fallback(gpu_output, gpu_data)
                except Exception as err:
                    _LOGGER.debug("Error processing Intel GPU JSON data: %s", err)
                    return self._parse_intel_gpu_text_fallback(gpu_output, gpu_data)

            # Only return data if we have a valid GPU detected
            model = gpu_data.get("model", "Unknown Intel GPU")
            usage = gpu_data.get("usage_percentage", 0)
            if model != "Unknown Intel GPU" or (isinstance(usage, (int, float)) and usage > 0):
                return gpu_data

            return None

        except Exception as err:
            _LOGGER.debug("Error parsing Intel GPU data: %s", err)
            return None

    async def _get_intel_gpu_info(self) -> Optional[Dict[str, Any]]:
        """Get Intel GPU information separately with proper timeout."""
        try:
            _LOGGER.debug("Fetching Intel GPU information")

            # First check if Intel GPU is available
            gpu_check_cmd = "lspci | grep -i 'vga\\|display\\|3d' | grep -i intel"
            gpu_check_result = await self.execute_command(gpu_check_cmd)

            if gpu_check_result.exit_status != 0:
                _LOGGER.debug("No Intel GPU detected")
                return None

            device_info = gpu_check_result.stdout.strip()
            _LOGGER.debug("Intel GPU device detected: %s", device_info)

            # Check if intel_gpu_top is available
            tool_check_cmd = "command -v intel_gpu_top"
            tool_check_result = await self.execute_command(tool_check_cmd)

            if tool_check_result.exit_status != 0:
                _LOGGER.debug("intel_gpu_top not available")
                return None

            # Get PCI slot for specific GPU targeting
            gpu_pci = device_info.split()[0] if device_info else ""

            # Run intel_gpu_top with proper timeout
            if gpu_pci:
                gpu_cmd = f"timeout 10 intel_gpu_top -J -s 1000 -n 2 -d pci:slot=\"0000:{gpu_pci}\""
            else:
                gpu_cmd = "timeout 10 intel_gpu_top -J -s 1000 -n 2"

            _LOGGER.debug("Running Intel GPU command: %s", gpu_cmd)
            gpu_result = await self.execute_command(gpu_cmd)

            if gpu_result.exit_status != 0:
                _LOGGER.debug("Intel GPU command failed with exit status %d", gpu_result.exit_status)
                return None

            gpu_output = gpu_result.stdout.strip()
            _LOGGER.debug("Intel GPU command output length: %d characters", len(gpu_output))

            # Clean up the output - remove any potential control characters
            gpu_output_clean = ''.join(char for char in gpu_output if ord(char) >= 32 or char in '\n\r\t')
            _LOGGER.debug("Intel GPU cleaned output length: %d characters", len(gpu_output_clean))

            # Check if output looks like valid JSON
            if gpu_output_clean.startswith('[') and gpu_output_clean.endswith(']'):
                _LOGGER.debug("Intel GPU output appears to be valid JSON array")
            else:
                _LOGGER.warning("Intel GPU output doesn't look like valid JSON: starts with '%s', ends with '%s'",
                              gpu_output_clean[:10], gpu_output_clean[-10:])

            # Parse the GPU data
            return self._parse_intel_gpu_data(gpu_output_clean, device_info)

        except Exception as err:
            _LOGGER.debug("Error getting Intel GPU info: %s", err)
            return None

    def _parse_intel_gpu_text_fallback(self, gpu_output: str, gpu_data: Dict[str, Any]) -> Dict[str, Any] | None:
        """Fallback parser for intel_gpu_top text output."""
        try:
            # If JSON parsing fails, try to parse text output
            # This is a simplified parser for basic usage information
            lines = gpu_output.split('\n')

            for line in lines:
                line = line.strip()

                # Look for engine usage patterns
                if 'Render/3D' in line and '%' in line:
                    match = re.search(r'(\d+(?:\.\d+)?)%', line)
                    if match:
                        gpu_data["engines"]["render"] = float(match.group(1))

                elif 'Blitter' in line and '%' in line:
                    match = re.search(r'(\d+(?:\.\d+)?)%', line)
                    if match:
                        gpu_data["engines"]["blitter"] = float(match.group(1))

                elif 'Video' in line and '%' in line:
                    match = re.search(r'(\d+(?:\.\d+)?)%', line)
                    if match:
                        gpu_data["engines"]["video"] = float(match.group(1))

            # Calculate average usage from engines
            if gpu_data["engines"]:
                total_usage = sum(gpu_data["engines"].values())
                engine_count = len(gpu_data["engines"])
                gpu_data["usage_percentage"] = round(total_usage / engine_count, 1)

            return gpu_data if gpu_data["engines"] else None

        except Exception as err:
            _LOGGER.debug("Error in Intel GPU text fallback parser: %s", err)
            return None

    async def system_reboot(self, delay: int = 0) -> bool:
        """Reboot the Unraid system."""
        try:
            if delay > 0:
                _LOGGER.info("Scheduling reboot with %d second delay", delay)
                command = f"shutdown -r +{delay//60}"
            else:
                _LOGGER.info("Executing immediate reboot")
                command = "shutdown -r now"

            result = await self.execute_command(command)

            if result.exit_status != 0:
                _LOGGER.error("Reboot command failed: %s", result.stderr)
                return False

            _LOGGER.info("Reboot command executed successfully")
            return True

        except Exception as err:
            _LOGGER.error("Error during reboot: %s", str(err))
            return False

    async def system_shutdown(self, delay: int = 0) -> bool:
        """Shutdown the Unraid system."""
        try:
            if delay > 0:
                _LOGGER.info("Scheduling shutdown with %d second delay", delay)
                command = f"shutdown +{delay//60}"
            else:
                _LOGGER.info("Executing immediate shutdown")
                command = "shutdown now"

            result = await self.execute_command(command)

            if result.exit_status != 0:
                _LOGGER.error("Shutdown command failed: %s", result.stderr)
                return False

            _LOGGER.info("Shutdown command executed successfully")
            return True

        except Exception as err:
            _LOGGER.error("Error during shutdown: %s", str(err))
            return False

    async def get_service_status(self, service_name: str) -> bool:
        """Check if an Unraid service is running."""
        try:
            result = await self.execute_command(f"/etc/rc.d/rc.{service_name} status")
            return result.exit_status == 0 and "is currently running" in result.stdout
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError):
            return False

    async def get_hostname(self) -> str:
        """Get the Unraid server hostname.

        Uses a single command with fallback options to reduce SSH calls.
        Always returns a valid hostname string, using 'server' as a fallback.
        """
        try:
            # Use a single command with || for fallback
            cmd = "hostname -f || uname -n || echo 'unknown'"
            result = await self.execute_command(cmd)

            if result.exit_status == 0:
                hostname = result.stdout.strip()
                if hostname and hostname != 'unknown':
                    # Sanitize hostname
                    sanitized = self._sanitize_hostname(hostname)
                    _LOGGER.debug("Retrieved hostname: %s (sanitized: %s)", hostname, sanitized)
                    return sanitized

            _LOGGER.warning("Could not retrieve valid hostname, using default name")
            return 'server'
        except (asyncssh.Error, OSError, ValueError) as err:
            _LOGGER.error("Error getting hostname: %s", err)
            return 'server'

    async def _get_system_timezone(self) -> str:
        """Get the system timezone.

        Uses a single command with fallback options to reduce SSH calls.
        """
        try:
            # Use a single command with || for fallback
            cmd = "cat /etc/timezone || timedatectl show --property=Timezone --value || echo 'UTC'"
            tz_result = await self.execute_command(cmd)

            if tz_result.exit_status == 0:
                timezone = tz_result.stdout.strip()
                if timezone:
                    return timezone

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.debug("Error getting system timezone: %s", err)

        return "UTC"  # Default to UTC

    @with_error_handling(fallback_return={})
    async def collect_system_stats(self) -> Dict[str, Any]:
        """Collect system statistics using a single batched command."""
        # Use a single command to collect all system statistics
        _LOGGER.debug("Collecting system statistics with batched command")
        cmd = (
            "echo '===ARRAY_STATE==='; "
            "mdcmd status; "
            "echo '===CPU_USAGE==='; "
            "top -bn1 | grep '^%Cpu' | awk '{print 100 - $8}'; "
            "echo '===CPU_INFO==='; "
            "echo 'CORES:'; nproc; "
            "echo 'MODEL:'; grep 'model name' /proc/cpuinfo | head -1 | cut -d':' -f2 | sed 's/^ *//'; "
            "echo 'ARCH:'; uname -m; "
            "echo '===MEMORY_INFO==='; "
            "cat /proc/meminfo; "
            "echo '===UPTIME==='; "
            "cat /proc/uptime; "
            "echo '===TEMPERATURE==='; "
            "sensors; "
            "echo '===THERMAL_ZONES==='; "
            "paste <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp); "
            "echo '===BOOT_USAGE==='; "
            "df -k /boot | awk 'NR==2 {print $2,$3,$4}'; "
            "echo '===CACHE_USAGE==='; "
            "mountpoint -q /mnt/cache && df -k /mnt/cache | awk 'NR==2 {print $2,$3,$4}' || echo 'not_mounted'; "
            "echo '===LOG_USAGE==='; "
            "df -k /var/log | awk 'NR==2 {print $2,$3,$4,$5}'; "
            "echo '===DOCKER_VDISK==='; "
            "df -k /var/lib/docker | awk 'NR==2 {print $2,$3,$4}' 2>/dev/null || echo 'not_mounted'; "
            "echo '===INTEL_GPU==='; "
            "if command -v intel_gpu_top >/dev/null 2>&1; then "
            "GPU_PCI=$(lspci | grep -i 'vga\\|display\\|3d' | grep -i intel | head -1 | cut -d' ' -f1); "
            "if [ -n \"$GPU_PCI\" ]; then "
            "timeout 8 intel_gpu_top -J -s 1000 -n 2 -d pci:slot=\"0000:$GPU_PCI\" 2>/dev/null || echo 'gpu_timeout'; "
            "else echo 'no_pci_device'; fi; "
            "else echo 'not_available'; fi; "
            "echo '===GPU_DEVICE_INFO==='; "
            "lspci | grep -i 'vga\\|display\\|3d' | grep -i intel || echo 'no_intel_gpu'"
        )

        result = await self.execute_command(cmd)

        if result.exit_status == 0:
            # Split the output into sections
            sections = {}
            current_section = None
            section_content = []

            for line in result.stdout.splitlines():
                if line.startswith('===') and line.endswith('==='):
                    # Save previous section if it exists
                    if current_section:
                        sections[current_section] = '\n'.join(section_content)
                    # Start new section
                    current_section = line.strip('=').strip()
                    section_content = []
                elif current_section:
                    section_content.append(line)

            # Save the last section
            if current_section and section_content:
                sections[current_section] = '\n'.join(section_content)

            # Parse each section
            system_stats: Dict[str, Any] = {}

            # Parse array state
            if 'ARRAY_STATE' in sections:
                array_state = self._parse_array_state_from_output(sections['ARRAY_STATE'])
                system_stats['array_state'] = {
                    "state": array_state.state,
                    "num_disks": array_state.num_disks,
                    "num_disabled": array_state.num_disabled,
                    "num_invalid": array_state.num_invalid,
                    "num_missing": array_state.num_missing,
                    "synced": array_state.synced,
                    "sync_action": array_state.sync_action,
                    "sync_progress": array_state.sync_progress,
                    "sync_errors": array_state.sync_errors,
                }

                # Parse CPU usage
                if 'CPU_USAGE' in sections:
                    try:
                        cpu_usage = float(sections['CPU_USAGE'].strip())
                        if 0 <= cpu_usage <= 100:
                            system_stats['cpu_usage'] = float(round(cpu_usage, 2))
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not parse CPU usage from output: %s", sections['CPU_USAGE'])

                # Parse CPU info
                if 'CPU_INFO' in sections:
                    try:
                        cpu_info_lines = sections['CPU_INFO'].strip().split('\n')
                        cpu_cores: Optional[int] = None
                        cpu_model: Optional[str] = None
                        cpu_arch: Optional[str] = None

                        for line in cpu_info_lines:
                            line = line.strip()
                            if line.startswith('CORES:'):
                                continue
                            elif line.startswith('MODEL:'):
                                continue
                            elif line.startswith('ARCH:'):
                                continue
                            elif cpu_cores is None and line.isdigit():
                                cpu_cores = int(line)
                            elif cpu_model is None and line and not line.isdigit():
                                cpu_model = line
                            elif cpu_arch is None and line and not line.isdigit() and cpu_model is not None:
                                cpu_arch = line

                        if cpu_cores:
                            system_stats['cpu_cores'] = cpu_cores
                        if cpu_model:
                            system_stats['cpu_model'] = cpu_model
                        if cpu_arch:
                            system_stats['cpu_arch'] = cpu_arch

                    except (ValueError, TypeError) as err:
                        _LOGGER.debug("Could not parse CPU info from output: %s, error: %s", sections['CPU_INFO'], err)

                # Parse memory info
                if 'MEMORY_INFO' in sections:
                    system_stats['memory_usage'] = self._parse_memory_info(sections['MEMORY_INFO'])

                # Parse uptime
                if 'UPTIME' in sections:
                    try:
                        uptime_match = re.search(r'(\d+(\.\d+)?)', sections['UPTIME'])
                        if uptime_match:
                            system_stats['uptime'] = float(uptime_match.group(1))
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not parse uptime from output: %s", sections['UPTIME'])

                # Parse temperature data
                if 'TEMPERATURE' in sections:
                    sensors_dict = self._parse_sensors_output(sections['TEMPERATURE'])
                    temp_data = {'sensors': sensors_dict}

                    # Extract fan data using optimized detection
                    fans = self._extract_fans_data_optimized(sensors_dict)
                    if fans:
                        temp_data['fans'] = fans

                    system_stats['temperature_data'] = temp_data

                # Parse thermal zones
                if 'THERMAL_ZONES' in sections and sections['THERMAL_ZONES'].strip():
                    thermal_zones = self._parse_thermal_zones(sections['THERMAL_ZONES'])
                    if 'temperature_data' not in system_stats:
                        system_stats['temperature_data'] = {}
                    system_stats['temperature_data']['thermal_zones'] = thermal_zones

                # Parse boot usage
                if 'BOOT_USAGE' in sections and sections['BOOT_USAGE'].strip():
                    try:
                        total, used, free = map(int, sections['BOOT_USAGE'].strip().split())
                        percentage = (used / total) * 100 if total > 0 else 0
                        system_stats['boot_usage'] = {
                            "percentage": float(round(percentage, 2)),
                            "total": total * 1024,  # Convert to bytes
                            "used": used * 1024,    # Convert to bytes
                            "free": free * 1024     # Convert to bytes
                        }
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not parse boot usage from output: %s", sections['BOOT_USAGE'])

                # Parse cache usage
                if 'CACHE_USAGE' in sections:
                    cache_output = sections['CACHE_USAGE'].strip()
                    if cache_output == 'not_mounted':
                        system_stats['cache_usage'] = {
                            "percentage": 0,
                            "total": 0,
                            "used": 0,
                            "free": 0,
                            "status": "not_mounted"
                        }
                    else:
                        try:
                            total, used, free = map(int, cache_output.split())
                            percentage = (used / total) * 100 if total > 0 else 0
                            system_stats['cache_usage'] = {
                                "percentage": float(round(percentage, 2)),
                                "total": total * 1024,  # Convert to bytes
                                "used": used * 1024,    # Convert to bytes
                                "free": free * 1024,    # Convert to bytes
                                "status": "mounted"
                            }
                        except (ValueError, TypeError):
                            _LOGGER.debug("Could not parse cache usage from output: %s", cache_output)

                # Parse log filesystem usage
                if 'LOG_USAGE' in sections and sections['LOG_USAGE'].strip():
                    try:
                        total, used, free, percentage = sections['LOG_USAGE'].strip().split()
                        system_stats['log_filesystem'] = {
                            "total": int(total) * 1024,
                            "used": int(used) * 1024,
                            "free": int(free) * 1024,
                            "percentage": float(percentage.strip('%'))
                        }
                    except (ValueError, TypeError):
                        _LOGGER.debug("Could not parse log usage from output: %s", sections['LOG_USAGE'])

                # Parse docker vdisk usage
                if 'DOCKER_VDISK' in sections:
                    docker_output = sections['DOCKER_VDISK'].strip()
                    if docker_output == 'not_mounted':
                        system_stats['docker_vdisk'] = {
                            "percentage": 0,
                            "total": 0,
                            "used": 0,
                            "free": 0
                        }
                    else:
                        try:
                            total, used, free = map(int, docker_output.split())
                            percentage = (used / total) * 100 if total > 0 else 0
                            system_stats['docker_vdisk'] = {
                                "percentage": float(round(percentage, 2)),
                                "total": total * 1024,  # Convert to bytes
                                "used": used * 1024,    # Convert to bytes
                                "free": free * 1024     # Convert to bytes
                            }
                        except (ValueError, TypeError):
                            _LOGGER.debug("Could not parse docker vdisk usage from output: %s", docker_output)

                # Parse Intel GPU data
                if 'INTEL_GPU' in sections and 'GPU_DEVICE_INFO' in sections:
                    gpu_output = sections['INTEL_GPU'].strip()
                    device_info = sections['GPU_DEVICE_INFO'].strip()

                    if gpu_output not in ('not_available', 'gpu_timeout', 'no_pci_device') and device_info != 'no_intel_gpu':
                        intel_gpu_data = self._parse_intel_gpu_data(gpu_output, device_info)
                        if intel_gpu_data:
                            system_stats['intel_gpu'] = intel_gpu_data
                            _LOGGER.debug("Successfully parsed Intel GPU data from batched command: %s", intel_gpu_data.get('model', 'Unknown'))
                    else:
                        _LOGGER.debug("Intel GPU not available or command failed: %s", gpu_output)

            # Get UPS info separately as it's not part of the batched command
            system_stats['ups_info'] = await self.get_ups_info()

            # Get array usage separately as it requires parsing the array state first
            system_stats['array_usage'] = await self.get_array_usage()

            # Get individual disks separately as it's more complex
            disks, extra_stats = await self.get_individual_disk_usage()
            system_stats['individual_disks'] = disks

            # Add any extra stats from disk operations
            if extra_stats:
                for key, value in extra_stats.items():
                    system_stats[key] = value

            return system_stats

        _LOGGER.warning("Batched system stats command failed with exit status %d", result.exit_status)
        return {}

    def _parse_array_state_from_output(self, output: str) -> ArrayState:
        """Parse array state from mdcmd output string."""
        try:
            # Parse mdcmd output
            state_dict = {}
            for line in output.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    state_dict[key] = value.strip()

            return ArrayState(
                state=state_dict.get("mdState", "UNKNOWN").upper(),
                num_disks=int(state_dict.get("mdNumDisks", 0)),
                num_disabled=int(state_dict.get("mdNumDisabled", 0)),
                num_invalid=int(state_dict.get("mdNumInvalid", 0)),
                num_missing=int(state_dict.get("mdNumMissing", 0)),
                synced=bool(int(state_dict.get("sbSynced", 0))),
                sync_action=state_dict.get("mdResyncAction"),
                sync_progress=float(state_dict.get("mdResync", 0)),
                sync_errors=int(state_dict.get("mdResyncCorr", 0))
            )
        except (ValueError, TypeError) as err:
            _LOGGER.error("Error parsing array state from output: %s", err)
            return ArrayState(
                state="ERROR",
                num_disks=0,
                num_disabled=0,
                num_invalid=0,
                num_missing=0,
                synced=False
            )

    def _parse_memory_info(self, output: str) -> Dict[str, Any]:
        """Parse memory info from /proc/meminfo output."""
        try:
            # Parse meminfo into a dictionary
            memory_info = {}
            for line in output.splitlines():
                try:
                    key, value = line.split(':')
                    # Convert kB to bytes and strip 'kB'
                    value = int(value.strip().split()[0]) * 1024
                    memory_info[key.strip()] = value
                except (ValueError, IndexError):
                    continue

            # Calculate memory values
            total = memory_info.get('MemTotal', 0)
            free = memory_info.get('MemFree', 0)
            cached = memory_info.get('Cached', 0)
            buffers = memory_info.get('Buffers', 0)
            available = memory_info.get('MemAvailable', 0)

            # Calculate used memory (total - free - cached - buffers)
            used = total - free - cached - buffers

            # Validate values to prevent division by zero or negative values
            if total <= 0:
                _LOGGER.error("Invalid total memory value: %d", total)
                return {"percentage": None}

            # Format values for reporting
            memory_stats = {
                "percentage": round((used / total) * 100, 2),
                "total": format_bytes(total),
                "used": format_bytes(used),
                "free": format_bytes(free),
                "cached": format_bytes(cached),
                "buffers": format_bytes(buffers),
                "available": format_bytes(available),
            }

            return memory_stats

        except Exception as err:
            _LOGGER.error("Error parsing memory info: %s", err)
            return {"percentage": None}

    def _sanitize_hostname(self, hostname: str) -> str:
        """Sanitize hostname for entity ID compatibility.

        Returns a valid hostname string that can be used in entity IDs.
        If the hostname is invalid, returns 'server' as a fallback.
        """
        if not hostname or hostname == 'unknown':
            return 'server'

        # Remove invalid characters
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', hostname.lower())

        # Replace consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)

        # Trim to max length
        sanitized = sanitized[:32]  # Using constant would be better

        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')

        # Ensure we have a valid hostname
        if not sanitized:
            return 'server'

        return sanitized

    def _format_duration(self, duration_str: str) -> str:
        """Format duration string into hours, minutes, seconds."""
        try:
            total_seconds = int(duration_str)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            parts = []
            if hours > 0:
                parts.append(f"{hours} hours")
            if minutes > 0:
                parts.append(f"{minutes} minutes")
            if seconds > 0 or not parts:  # Include seconds if it's the only component
                parts.append(f"{seconds} seconds")

            return ", ".join(parts)
        except (ValueError, TypeError):
            return duration_str
