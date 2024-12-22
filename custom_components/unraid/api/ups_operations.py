"""UPS operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, Any

import asyncio
import asyncssh # type: ignore

_LOGGER = logging.getLogger(__name__)

# UPS metric validation ranges
UPS_METRICS = {
    "NOMPOWER": {"min": 0, "max": 10000, "unit": "W"},
    "LOADPCT": {"min": 0, "max": 100, "unit": "%"},
    "CUMONKWHOURS": {"min": 0, "max": 1000000, "unit": "kWh"},
    "LOADAPNT": {"min": 0, "max": 10000, "unit": "VA"},
    "LINEV": {"min": 0, "max": 500, "unit": "V"},
    "POWERFACTOR": {"min": 0, "max": 1, "unit": None},
    "BCHARGE": {"min": 0, "max": 100, "unit": "%"},
    "TIMELEFT": {"min": 0, "max": 1440, "unit": "min"},
    "BATTV": {"min": 0, "max": 60, "unit": "V"},
}

class UPSOperationsMixin:
    """Mixin for UPS-related operations."""

    async def detect_ups(self) -> bool:
        """Attempt to detect if a UPS is connected."""
        try:
            result = await self.execute_command("which apcaccess")
            if result.exit_status == 0:
                # apcaccess is installed, now check if it can communicate with a UPS
                result = await self.execute_command("apcaccess status")
                return result.exit_status == 0
            return False
        except (asyncssh.Error, OSError):
            _LOGGER.debug("UPS detection result: %s", "detected" if result.exit_status == 0 else "not detected")
            return False

    async def get_ups_info(self) -> Dict[str, Any]:
        """Fetch UPS information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching UPS info")
            # Check if apcupsd is installed and running first
            check_result = await self.execute_command(
                "command -v apcaccess >/dev/null 2>&1 && "
                "pgrep apcupsd >/dev/null 2>&1 && "
                "echo 'running'"
            )

            if check_result.exit_status == 0 and "running" in check_result.stdout:
                result = await self.execute_command("apcaccess -u 2>/dev/null")
                if result.exit_status == 0:
                    ups_data = {}
                    for line in result.stdout.splitlines():
                        if ':' in line:
                            key, value = line.split(':', 1)
                            ups_data[key.strip()] = value.strip()
                    return ups_data

            # If not installed or not running, return empty dict without error
            return {}
        except (asyncssh.Error, OSError) as error:
            _LOGGER.debug("Error getting UPS info (apcupsd might not be installed): %s", str(error))
            return {}

    def _validate_ups_metric(self, metric: str, value: str) -> Any:
        """Validate and process UPS metric values.
        
        Args:
            metric: Metric name
            value: Raw value string
            
        Returns:
            Processed value or None if validation fails
        """
        if metric not in UPS_METRICS:
            return None

        try:
            # Clean up value string
            numeric_value = float(''.join(
                c for c in value if c.isdigit() or c in '.-'
            ))

            # Check range
            metric_info = UPS_METRICS[metric]
            if (
                numeric_value < metric_info["min"] or
                numeric_value > metric_info["max"]
            ):
                _LOGGER.warning(
                    "UPS metric %s value %f outside valid range [%f, %f]",
                    metric,
                    numeric_value,
                    metric_info["min"],
                    metric_info["max"]
                )
                return None

            # Convert to integer for specific metrics
            if metric in ["NOMPOWER", "TIMELEFT"]:
                return int(numeric_value)

            return numeric_value

        except (ValueError, TypeError) as err:
            _LOGGER.debug(
                "Error processing UPS metric %s value '%s': %s",
                metric,
                value,
                err
            )
            return None

    async def _validate_ups_connection(self) -> bool:
        """Validate UPS connection and communication.
        
        Returns:
            bool: True if UPS is properly connected and responding
        """
        try:
            # First check if apcupsd is installed and running
            service_check = await self.execute_command(
                "systemctl is-active apcupsd"
            )
            if service_check.exit_status != 0:
                _LOGGER.debug("apcupsd service not running")
                return False

            # Then verify we can actually communicate with a UPS
            result = await self.execute_command(
                "timeout 5 apcaccess status",
                timeout=10  # Allow some extra time for timeout command
            )

            if result.exit_status != 0:
                _LOGGER.debug("Cannot communicate with UPS")
                return False

            # Verify we got valid data
            for line in result.stdout.splitlines():
                if "STATUS" in line and "ONLINE" in line:
                    return True

            _LOGGER.debug("UPS status check failed")
            return False

        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.error("Error validating UPS connection: %s", err)
            return False

    async def get_ups_model(self) -> str:
        """Get UPS model information.
        
        Returns:
            str: UPS model name or 'Unknown' if not available
        """
        try:
            result = await self.execute_command(
                "apcaccess -u | grep '^MODEL'"
            )
            if result.exit_status == 0:
                return result.stdout.split(':', 1)[1].strip()
            return "Unknown"
        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.debug("Error getting UPS model: %s", err)
            return "Unknown"

    async def get_ups_status_summary(self) -> Dict[str, Any]:
        """Get a summary of critical UPS status information.
        
        Returns:
            Dict containing key UPS metrics and status
        """
        try:
            info = await self.get_ups_info()
            return {
                "status": info.get("STATUS", "Unknown"),
                "battery_charge": info.get("BCHARGE", 0),
                "runtime_left": info.get("TIMELEFT", 0),
                "load_percent": info.get("LOADPCT", 0),
                "nominal_power": info.get("NOMPOWER", 0),
                "line_voltage": info.get("LINEV", 0),
                "battery_voltage": info.get("BATTV", 0)
            }
        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.error("Error getting UPS status summary: %s", err)
            return {
                "status": "Error",
                "error": str(err)
            }
