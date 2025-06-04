"""CPU power monitoring for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

@dataclass
class PowerReading:
    """Power reading data."""
    domain: str
    value: float  # Watts
    max_value: Optional[float] = None
    source: str = "unknown"

@dataclass
class CPUPowerInfo:
    """CPU power information."""
    package_power: Optional[float] = None
    core_power: Optional[float] = None
    uncore_power: Optional[float] = None
    dram_power: Optional[float] = None
    total_power: Optional[float] = None
    power_limit: Optional[float] = None
    source: str = "unknown"
    supported: bool = False

class CPUPowerMonitor:
    """Monitor CPU power consumption using RAPL and AMD sensors."""
    
    # Intel RAPL paths
    INTEL_RAPL_PATHS = {
        "package": "/sys/class/powercap/intel-rapl:0/energy_uj",
        "cores": "/sys/class/powercap/intel-rapl:0:0/energy_uj", 
        "uncore": "/sys/class/powercap/intel-rapl:0:1/energy_uj",
        "dram": "/sys/class/powercap/intel-rapl:0:2/energy_uj",
        "package_limit": "/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"
    }
    
    # AMD power sensor patterns
    AMD_POWER_PATTERNS = {
        "package": [r"Tctl", r"Package.*Power", r"CPU.*Power"],
        "cores": [r"Core.*Power", r"CCD.*Power"],
        "soc": [r"SoC.*Power", r"APU.*Power"],
        "memory": [r"Memory.*Power", r"DDR.*Power"]
    }

    def __init__(self, execute_command_func):
        """Initialize CPU power monitor."""
        self.execute_command = execute_command_func
        self._last_energy_readings: Dict[str, int] = {}
        self._last_timestamp: Optional[float] = None
        self._power_support_detected: Optional[str] = None

    async def detect_power_monitoring_support(self) -> str:
        """
        Detect what type of power monitoring is available.
        
        Returns:
            "intel_rapl", "amd_sensors", "none", or "unknown"
        """
        if self._power_support_detected is not None:
            return self._power_support_detected

        try:
            # Check for Intel RAPL support
            rapl_check = await self.execute_command("ls /sys/class/powercap/intel-rapl* 2>/dev/null")
            if rapl_check.exit_status == 0 and rapl_check.stdout.strip():
                _LOGGER.debug("Intel RAPL power monitoring detected")
                self._power_support_detected = "intel_rapl"
                return "intel_rapl"

            # Check for AMD power sensors
            sensors_check = await self.execute_command("sensors -j 2>/dev/null")
            if sensors_check.exit_status == 0:
                sensors_output = sensors_check.stdout.lower()
                amd_indicators = ["k10temp", "zenpower", "amd", "ryzen"]
                power_indicators = ["power", "watt", "energy"]
                
                has_amd = any(indicator in sensors_output for indicator in amd_indicators)
                has_power = any(indicator in sensors_output for indicator in power_indicators)
                
                if has_amd and has_power:
                    _LOGGER.debug("AMD power sensors detected")
                    self._power_support_detected = "amd_sensors"
                    return "amd_sensors"

            # Check for generic power sensors
            hwmon_check = await self.execute_command("find /sys/class/hwmon -name '*power*' 2>/dev/null")
            if hwmon_check.exit_status == 0 and hwmon_check.stdout.strip():
                _LOGGER.debug("Generic power sensors detected")
                self._power_support_detected = "generic"
                return "generic"

            _LOGGER.debug("No power monitoring support detected")
            self._power_support_detected = "none"
            return "none"

        except Exception as err:
            _LOGGER.debug("Error detecting power monitoring support: %s", err)
            self._power_support_detected = "unknown"
            return "unknown"

    async def get_cpu_power_info(self) -> CPUPowerInfo:
        """Get comprehensive CPU power information."""
        support_type = await self.detect_power_monitoring_support()
        
        if support_type == "intel_rapl":
            return await self._get_intel_rapl_power()
        elif support_type == "amd_sensors":
            return await self._get_amd_sensor_power()
        elif support_type == "generic":
            return await self._get_generic_power()
        else:
            return CPUPowerInfo(supported=False, source="none")

    async def _get_intel_rapl_power(self) -> CPUPowerInfo:
        """Get Intel RAPL power information."""
        try:
            import time
            current_time = time.time()
            
            # Read current energy values
            energy_readings = {}
            for domain, path in self.INTEL_RAPL_PATHS.items():
                if domain.endswith("_limit"):
                    continue
                    
                try:
                    result = await self.execute_command(f"cat {path} 2>/dev/null")
                    if result.exit_status == 0:
                        energy_readings[domain] = int(result.stdout.strip())
                except (ValueError, OSError):
                    continue

            # Calculate power if we have previous readings
            power_info = CPUPowerInfo(supported=True, source="intel_rapl")
            
            if self._last_energy_readings and self._last_timestamp:
                time_delta = current_time - self._last_timestamp
                if time_delta > 0:
                    # Calculate power for each domain
                    for domain, current_energy in energy_readings.items():
                        if domain in self._last_energy_readings:
                            energy_delta = current_energy - self._last_energy_readings[domain]
                            # Convert microjoules to watts
                            power_watts = (energy_delta / 1_000_000) / time_delta
                            
                            if domain == "package":
                                power_info.package_power = max(0, power_watts)
                            elif domain == "cores":
                                power_info.core_power = max(0, power_watts)
                            elif domain == "uncore":
                                power_info.uncore_power = max(0, power_watts)
                            elif domain == "dram":
                                power_info.dram_power = max(0, power_watts)

            # Get power limit
            try:
                limit_result = await self.execute_command(f"cat {self.INTEL_RAPL_PATHS['package_limit']} 2>/dev/null")
                if limit_result.exit_status == 0:
                    # Convert microwatts to watts
                    power_info.power_limit = int(limit_result.stdout.strip()) / 1_000_000
            except (ValueError, OSError):
                pass

            # Calculate total power
            if power_info.package_power is not None:
                power_info.total_power = power_info.package_power
            elif power_info.core_power is not None and power_info.uncore_power is not None:
                power_info.total_power = power_info.core_power + power_info.uncore_power

            # Store current readings for next calculation
            self._last_energy_readings = energy_readings
            self._last_timestamp = current_time

            return power_info

        except Exception as err:
            _LOGGER.debug("Error getting Intel RAPL power: %s", err)
            return CPUPowerInfo(supported=False, source="intel_rapl_error")

    async def _get_amd_sensor_power(self) -> CPUPowerInfo:
        """Get AMD sensor power information."""
        try:
            result = await self.execute_command("sensors -j 2>/dev/null")
            if result.exit_status != 0:
                return CPUPowerInfo(supported=False, source="amd_sensors_unavailable")

            import json
            sensors_data = json.loads(result.stdout)
            
            power_info = CPUPowerInfo(supported=True, source="amd_sensors")
            
            # Search for power readings in sensor data
            for chip_name, chip_data in sensors_data.items():
                if not isinstance(chip_data, dict):
                    continue
                    
                chip_lower = chip_name.lower()
                if any(amd_term in chip_lower for amd_term in ["k10temp", "zenpower", "amd"]):
                    # Look for power readings
                    for sensor_name, sensor_data in chip_data.items():
                        if not isinstance(sensor_data, dict):
                            continue
                            
                        sensor_lower = sensor_name.lower()
                        
                        # Check for package power
                        if any(pattern.lower() in sensor_lower for pattern in self.AMD_POWER_PATTERNS["package"]):
                            if "input" in sensor_data:
                                power_info.package_power = float(sensor_data["input"])
                        
                        # Check for core power
                        elif any(pattern.lower() in sensor_lower for pattern in self.AMD_POWER_PATTERNS["cores"]):
                            if "input" in sensor_data:
                                power_info.core_power = float(sensor_data["input"])
                        
                        # Check for SoC power
                        elif any(pattern.lower() in sensor_lower for pattern in self.AMD_POWER_PATTERNS["soc"]):
                            if "input" in sensor_data:
                                if power_info.package_power is None:
                                    power_info.package_power = float(sensor_data["input"])

            # Calculate total power
            if power_info.package_power is not None:
                power_info.total_power = power_info.package_power
            elif power_info.core_power is not None:
                power_info.total_power = power_info.core_power

            return power_info

        except (json.JSONDecodeError, ValueError, KeyError) as err:
            _LOGGER.debug("Error parsing AMD sensor power data: %s", err)
            return CPUPowerInfo(supported=False, source="amd_sensors_error")

    async def _get_generic_power(self) -> CPUPowerInfo:
        """Get power information from generic hwmon sensors."""
        try:
            # Look for power sensors in hwmon
            result = await self.execute_command("find /sys/class/hwmon -name 'power*_input' 2>/dev/null")
            if result.exit_status != 0:
                return CPUPowerInfo(supported=False, source="generic_unavailable")

            power_files = result.stdout.strip().splitlines()
            if not power_files:
                return CPUPowerInfo(supported=False, source="generic_no_sensors")

            power_info = CPUPowerInfo(supported=True, source="generic")
            total_power = 0
            power_count = 0

            # Read power values
            for power_file in power_files:
                try:
                    power_result = await self.execute_command(f"cat {power_file} 2>/dev/null")
                    if power_result.exit_status == 0:
                        # Convert microwatts to watts
                        power_watts = int(power_result.stdout.strip()) / 1_000_000
                        total_power += power_watts
                        power_count += 1
                except (ValueError, OSError):
                    continue

            if power_count > 0:
                power_info.total_power = total_power
                power_info.package_power = total_power  # Assume it's package power

            return power_info

        except Exception as err:
            _LOGGER.debug("Error getting generic power: %s", err)
            return CPUPowerInfo(supported=False, source="generic_error")

    async def get_power_summary(self) -> Dict[str, Any]:
        """Get a summary of CPU power information for sensors."""
        power_info = await self.get_cpu_power_info()
        
        summary = {
            "supported": power_info.supported,
            "source": power_info.source,
            "total_power": power_info.total_power,
            "package_power": power_info.package_power,
            "core_power": power_info.core_power,
            "uncore_power": power_info.uncore_power,
            "dram_power": power_info.dram_power,
            "power_limit": power_info.power_limit
        }
        
        # Add efficiency metrics if we have the data
        if power_info.total_power is not None and power_info.power_limit is not None:
            summary["power_efficiency"] = (power_info.total_power / power_info.power_limit) * 100
        
        return summary
