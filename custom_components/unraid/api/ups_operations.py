"""UPS operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, Any

import asyncio
import asyncssh # type: ignore

from ..const import (
    UPS_METRICS,
    UPS_DEFAULT_POWER_FACTOR,
)

_LOGGER = logging.getLogger(__name__)

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
        except (asyncssh.Error, OSError) as err:
            _LOGGER.debug(
                "Error during UPS detection: %s",
                err
            )
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
                    
                    # Add power factor info if not present
                    if "POWERFACTOR" not in ups_data:
                        ups_data["POWERFACTOR"] = str(UPS_DEFAULT_POWER_FACTOR)
                    
                    return ups_data

            # If not installed or not running, return empty dict without error
            return {}
        except (asyncssh.Error, OSError) as error:
            _LOGGER.debug(
                "Error getting UPS info (apcupsd might not be installed): %s",
                str(error)
            )
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
            # Clean up value string and handle special cases
            if isinstance(value, str):
                # Remove any non-numeric characters except decimals and negatives
                numeric_value = float(''.join(
                    c for c in value if c.isdigit() or c in '.-'
                ))
            else:
                numeric_value = float(value)

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
            if result.exit_status == 0 and ':' in result.stdout:
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
            
            # Process each metric through validation
            validated_metrics = {
                metric: self._validate_ups_metric(metric, info.get(metric, "0"))
                for metric in ["BCHARGE", "TIMELEFT", "LOADPCT", "NOMPOWER", "LINEV", "BATTV"]
            }
            
            return {
                "status": info.get("STATUS", "Unknown"),
                "battery_charge": validated_metrics["BCHARGE"],
                "runtime_left": validated_metrics["TIMELEFT"],
                "load_percent": validated_metrics["LOADPCT"],
                "nominal_power": validated_metrics["NOMPOWER"],
                "line_voltage": validated_metrics["LINEV"],
                "battery_voltage": validated_metrics["BATTV"]
            }
        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.error("Error getting UPS status summary: %s", err)
            return {
                "status": "Error",
                "error": str(err)
            }
