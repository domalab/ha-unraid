"""System operations for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import asyncio
import asyncssh

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

class SystemOperationsMixin:
    """Mixin for system-related operations."""

    async def get_system_stats(self) -> Dict[str, Any]:
        """Fetch system statistics from the Unraid server."""
        _LOGGER.debug("Fetching system stats from Unraid server")

        # Get array state first
        array_state = await self._parse_array_state()

        # Get other stats...
        cpu_usage = await self._get_cpu_usage()
        memory_usage = await self._get_memory_usage()
        array_usage = await self.get_array_usage()
        individual_disks = await self.get_individual_disk_usage()
        cache_usage = await self._get_cache_usage()
        boot_usage = await self._get_boot_usage()
        uptime = await self._get_uptime()
        ups_info = await self.get_ups_info()
        temperature_data = await self.get_temperature_data()
        log_filesystem = await self._get_log_filesystem_usage()
        docker_vdisk = await self._get_docker_vdisk_usage()

        return {
            "array_state": {
                "state": array_state.state,
                "num_disks": array_state.num_disks,
                "num_disabled": array_state.num_disabled,
                "num_invalid": array_state.num_invalid,
                "num_missing": array_state.num_missing,
                "synced": array_state.synced,
                "sync_action": array_state.sync_action,
                "sync_progress": array_state.sync_progress,
                "sync_errors": array_state.sync_errors,
            },
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "array_usage": array_usage,
            "individual_disks": individual_disks,
            "cache_usage": cache_usage,
            "boot_usage": boot_usage,
            "uptime": uptime,
            "ups_info": ups_info,
            "temperature_data": temperature_data,
            "log_filesystem": log_filesystem,
            "docker_vdisk": docker_vdisk,
        }

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

    async def _get_cpu_usage(self) -> Optional[float]:
        """Fetch CPU usage information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching CPU usage")
            result = await self.execute_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'")
            if result.exit_status != 0:
                _LOGGER.error("CPU usage command failed with exit status %d", result.exit_status)
                return None

            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return round(float(match.group(1)), 2)
            else:
                _LOGGER.error("Failed to parse CPU usage from output: %s", result.stdout)
                return None
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting CPU usage: %s", str(e))
            return None

    async def _get_memory_usage(self) -> Dict[str, Optional[float]]:
        """Fetch RAM information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching memory usage")
            result = await self.execute_command("free | awk '/Mem:/ {print $3/$2 * 100.0}'")
            if result.exit_status != 0:
                _LOGGER.error("Memory usage command failed with exit status %d", result.exit_status)
                return {"percentage": None}

            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return {"percentage": float(match.group(1))}
            else:
                _LOGGER.error("Failed to parse memory usage from output: %s", result.stdout)
                return {"percentage": None}
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting memory usage: %s", str(e))
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
                "percentage": round(percentage, 2),
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
                "percentage": round(percentage, 2),
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

    async def get_temperature_data(self) -> Dict[str, Any]:
        """Fetch temperature information from the Unraid system."""
        temp_data = {}

        try:
            _LOGGER.debug("Fetching temperature data")
            result = await self.execute_command("sensors")
            if result.exit_status == 0:
                temp_data['sensors'] = self._parse_sensors_output(result.stdout)
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting sensors data: %s", str(e))

        try:
            result = await self.execute_command("paste <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp)")
            if result.exit_status == 0:
                temp_data['thermal_zones'] = self._parse_thermal_zones(result.stdout)
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error getting thermal zone data: %s", str(e))

        return temp_data

    async def get_network_stats(self) -> Dict[str, Any]:
            """Fetch network statistics from the Unraid system."""
            try:
                _LOGGER.debug("Fetching network statistics")

                network_stats = {}

                # Get active interfaces, include eth and bond interfaces
                result = await self.execute_command(
                    "ip -br link show | grep -E '^(eth|bond)' | awk '{print $1, $2}'"  # Match eth and bond interfaces
                )

                if result.exit_status != 0:
                    return {}

                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        interface = parts[0]
                        state = parts[1].lower()

                        # Only process interfaces that are UP and have carrier
                        if "up" in state and "no-carrier" not in state:
                            try:
                                # Get traffic stats
                                stats_result = await self.execute_command(
                                    f"cat /sys/class/net/{interface}/statistics/{{rx,tx}}_bytes"
                                )

                                if stats_result.exit_status == 0:
                                    rx_bytes, tx_bytes = map(int, stats_result.stdout.splitlines())

                                    # Get interface info and mode
                                    info_result = await self.execute_command(
                                        f"ethtool {interface} 2>/dev/null || echo 'No ethtool info'"
                                    )

                                    # For bond interfaces, get the bond mode
                                    if interface.startswith('bond'):
                                        mode_result = await self.execute_command(
                                            f"cat /sys/class/net/{interface}/bonding/mode"
                                        )
                                        if mode_result.exit_status == 0:
                                            speed_info = f"Bond Mode: {mode_result.stdout.strip()}, mtu 1500"
                                        else:
                                            speed_info = "Bond interface, mtu 1500"
                                    else:
                                        # For ethernet interfaces
                                        speed_info = "1000Mbps, full duplex, mtu 1500"
                                        if info_result.exit_status == 0 and "Speed: " in info_result.stdout:
                                            speed_info = info_result.stdout.split("Speed: ")[1].split("\n")[0]
                                            speed_info += ", full duplex, mtu 1500"

                                    network_stats[interface] = {
                                        "rx_bytes": rx_bytes,
                                        "tx_bytes": tx_bytes,
                                        "rx_speed": 0,  # Will be calculated in coordinator
                                        "tx_speed": 0,  # Will be calculated in coordinator
                                        "connected": True,
                                        "interface_info": speed_info
                                    }
                                    _LOGGER.debug(
                                        "Added network interface %s (state: %s, info: %s)",
                                        interface,
                                        state,
                                        speed_info
                                    )
                            except (asyncssh.Error, OSError, asyncio.TimeoutError, ValueError) as err:
                                _LOGGER.debug(
                                    "Error getting stats for interface %s: %s", 
                                    interface,
                                    err
                                )
                                continue

                return network_stats

            except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
                _LOGGER.error("Error getting network stats: %s", str(err))
                return {}

    async def get_interface_info(self, interface: str) -> str:
        """Get detailed interface info."""
        try:
            # Get interface details
            result = await self.execute_command(f"ip link show {interface}")
            if result.exit_status != 0:
                return "Interface Down"

            if "NO-CARRIER" in result.stdout:
                return "Interface Down"
            elif "state UP" in result.stdout:
                # Get speed and duplex info
                ethtool_result = await self.execute_command(f"ethtool {interface}")
                if ethtool_result.exit_status == 0 and "Speed: 1000Mb/s" in ethtool_result.stdout:
                    return "1000Mbps, full duplex, mtu 1500"
                return "Interface Up"
            else:
                return "Interface Down"
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error getting interface info for %s: %s", interface, err)
            return "Interface Down"

    def _parse_sensors_output(self, output: str) -> Dict[str, Dict[str, str]]:
        """Parse the output of the sensors command."""
        sensors_data = {}
        current_sensor = None
        for line in output.splitlines():
            if ':' not in line:
                current_sensor = line.strip()
                sensors_data[current_sensor] = {}
            else:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.split('(')[0].strip()
                sensors_data[current_sensor][key] = value
        return sensors_data

    def _parse_thermal_zones(self, output: str) -> Dict[str, float]:
        """Parse the output of the thermal zones command."""
        thermal_zones = {}
        for line in output.splitlines():
            zone_type, temp = line.split()
            thermal_zones[zone_type] = float(temp) / 1000  # Convert milli-Celsius to Celsius
        return thermal_zones

    async def system_reboot(self, delay: int = 0) -> bool:
        """Reboot the Unraid system.
        
        Args:
            delay: Delay in seconds before executing reboot
            
        Returns:
            bool: True if command was executed successfully
        """
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
        """Shutdown the Unraid system.
        
        Args:
            delay: Delay in seconds before executing shutdown
            
        Returns:
            bool: True if command was executed successfully
        """
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
        """Get the Unraid server hostname."""
        try:
            # Try multiple commands in case one fails
            commands = [
                "hostname -f",
                "uname -n"
            ]

            for cmd in commands:
                result = await self.execute_command(cmd)
                if result.exit_status == 0:
                    hostname = result.stdout.strip()
                    if hostname:
                        # Sanitize hostname
                        sanitized = self._sanitize_hostname(hostname)
                        if sanitized:
                            _LOGGER.debug("Retrieved hostname: %s (sanitized: %s)", hostname, sanitized)
                            return sanitized

            _LOGGER.warning("Could not retrieve valid hostname, using default name")
            return None
        except (asyncssh.Error, OSError, ValueError) as err:
            _LOGGER.error("Error getting hostname: %s", err)
            return None

    async def _get_system_timezone(self) -> str:
        """Get the system timezone."""
        try:
            # Get timezone from system
            tz_result = await self.execute_command("cat /etc/timezone")
            if tz_result.exit_status == 0:
                return tz_result.stdout.strip()

            # Fallback to timedatectl
            tz_result = await self.execute_command("timedatectl show --property=Timezone --value")
            if tz_result.exit_status == 0:
                return tz_result.stdout.strip()

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.debug("Error getting system timezone: %s", err)

        return "UTC"  # Default to UTC instead of PST

    def _sanitize_hostname(self, hostname: str) -> str:
        """Sanitize hostname for entity ID compatibility.
        
        Args:
            hostname: Raw hostname string
            
        Returns:
            Sanitized hostname string or None if invalid
        """
        # Remove invalid characters
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', hostname.lower())
        # Replace consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Trim to max length
        sanitized = sanitized[:32]  # Using constant would be better
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        # Capitalize first letter
        sanitized = sanitized.capitalize() if sanitized else None
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