"""API client for Unraid."""
from __future__ import annotations

import asyncio
import asyncssh
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import re
from async_timeout import timeout
from enum import Enum
import shlex

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

class VMState(Enum):
    """VM states matching Unraid/libvirt states."""
    RUNNING = 'running'
    STOPPED = 'shut off'
    PAUSED = 'paused'
    IDLE = 'idle'
    IN_SHUTDOWN = 'in shutdown'
    CRASHED = 'crashed'
    SUSPENDED = 'pmsuspended'

    @classmethod
    def is_running(cls, state: str) -> bool:
        """Check if the state represents a running VM."""
        return state.lower() == cls.RUNNING.value

    @classmethod
    def parse(cls, state: str) -> str:
        """Parse the VM state string."""
        state = state.lower().strip()
        try:
            return next(s.value for s in cls if s.value == state)
        except StopIteration:
            return state

class ContainerStates(Enum):
    """Docker container states."""
    RUNNING = 'running'
    EXITED = 'exited'
    PAUSED = 'paused'
    RESTARTING = 'restarting'
    DEAD = 'dead'
    CREATED = 'created'

    @classmethod
    def parse(cls, state: str) -> str:
        """Parse the container state string."""
        state = state.lower().strip()
        try:
            return next(s.value for s in cls if s.value == state)
        except StopIteration:
            return state

class UnraidAPI:
    """API client for interacting with Unraid servers."""

    def __init__(self, host: str, username: str, password: str, port: int = 22):
        """Initialize the Unraid API client."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.lock = asyncio.Lock()
        self.connect_timeout = 30
        self.command_timeout = 60

    async def ensure_connection(self):
        """Ensure that a connection to the Unraid server is established."""
        async with self.lock:
            if self.conn is None:
                try:
                    async with timeout(self.connect_timeout):
                        self.conn = await asyncssh.connect(
                            self.host,
                            username=self.username,
                            password=self.password,
                            port=self.port,
                            known_hosts=None,
                            keepalive_interval=60,
                            keepalive_count_max=5
                        )
                    _LOGGER.info("Connected to Unraid server at %s", self.host)
                except asyncio.TimeoutError:
                    _LOGGER.error("Connection to Unraid server at %s timed out", self.host)
                    raise
                except Exception as err:
                    _LOGGER.error("Failed to connect to Unraid server: %s", err)
                    raise

    async def execute_command(self, command: str) -> asyncssh.SSHCompletedProcess:
        """Execute a command on the Unraid server."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.ensure_connection()
                async with timeout(self.command_timeout):
                    result = await self.conn.run(command)
                _LOGGER.debug("Executed command on Unraid server: %s", command)
                return result
            except asyncio.TimeoutError:
                _LOGGER.error("Command execution timed out: %s", command)
                self.conn = None
                if attempt == max_retries - 1:
                    raise
            except asyncssh.Error as err:
                _LOGGER.warning("SSH error on attempt %d: %s", attempt + 1, err)
                self.conn = None
                if attempt == max_retries - 1:
                    raise
            except Exception as err:
                _LOGGER.error("Unexpected error while executing command: %s", err)
                self.conn = None
                raise

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        async with self.lock:
            if self.conn:
                self.conn.close()
                await self.conn.wait_closed()
                self.conn = None
                _LOGGER.info("Disconnected from Unraid server at %s", self.host)

    async def ping(self) -> bool:
        """Check if the Unraid server is accessible via SSH."""
        try:
            async with timeout(self.connect_timeout):
                await self.ensure_connection()
                await self.conn.run("echo")
            _LOGGER.debug("Successfully pinged Unraid server at %s", self.host)
            return True
        except Exception as e:
            _LOGGER.error("Failed to ping Unraid server at %s: %s", self.host, e)
            return False

    async def get_system_stats(self) -> Dict[str, Any]:
        """Fetch system statistics from the Unraid server."""
        _LOGGER.debug("Fetching system stats from Unraid server")
        cpu_usage = await self._get_cpu_usage()
        memory_usage = await self._get_memory_usage()
        array_usage = await self._get_array_usage()
        individual_disks = await self.get_individual_disk_usage()
        cache_usage = await self._get_cache_usage()
        boot_usage = await self._get_boot_usage()
        uptime = await self._get_uptime()
        ups_info = await self.get_ups_info()
        temperature_data = await self.get_temperature_data()
        log_filesystem = await self._get_log_filesystem_usage()
        docker_vdisk = await self._get_docker_vdisk_usage()

        return {
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
    
    async def get_disk_info(self) -> Dict[str, Dict[str, Any]]:
        """Get combined disk information for all physical disks."""
        try:
            # Get disk models
            model_cmd = "ls -l /dev/disk/by-id/ata-* | grep -v part"
            model_result = await self.execute_command(model_cmd)
            disk_info = {}
            
            if model_result.exit_status == 0:
                for line in model_result.stdout.splitlines():
                    if '->' in line and 'ata-' in line:
                        try:
                            model = line.split('ata-')[1].split()[0]
                            device = line.split('/')[-1]  # Gets sdX
                            
                            # Get disk size
                            size_cmd = f"blockdev --getsize64 /dev/{device}"
                            size_result = await self.execute_command(size_cmd)
                            size = int(size_result.stdout.strip()) if size_result.exit_status == 0 else 0
                            
                            disk_info[device] = {
                                "model": model,
                                "size": size,
                                "device": device,
                            }
                            _LOGGER.debug("Found disk %s: %s, size: %s bytes", device, model, size)
                        except Exception as err:
                            _LOGGER.debug("Error parsing disk info for line '%s': %s", line, err)
            
            # Get temperatures and status
            temp_result = await self.execute_command(
                "for disk in /dev/sd[a-z]; do "
                'echo "===START $disk==="; '
                'if ! smartctl -n standby $disk > /dev/null 2>&1; then '
                '  echo "STANDBY"; '
                'else '
                '  smartctl -H -A $disk 2>/dev/null; '  # Only get SMART status for active disks
                'fi; '
                'echo "===END $disk==="; done'
            )

            if temp_result.exit_status == 0:
                current_disk = None
                
                for line in temp_result.stdout.splitlines():
                    if line.startswith('===START /dev/'):
                        current_disk = line.split('/')[-1].rstrip('=').strip()
                        if current_disk not in disk_info:
                            disk_info[current_disk] = {"device": current_disk}
                    elif line == "STANDBY":
                        if current_disk:
                            disk_info[current_disk]["status"] = "standby"
                            disk_info[current_disk]["smart_status"] = "Standby"
                            disk_info[current_disk]["health"] = "Standby"
                            continue
                    elif "SMART overall-health self-assessment test result:" in line:
                        if current_disk:
                            smart_status = line.split(": ")[-1].strip()
                            disk_info[current_disk]["smart_status"] = smart_status
                            disk_info[current_disk]["health"] = smart_status
                            disk_info[current_disk]["status"] = "active"
                    elif 'Temperature_Celsius' in line:
                        if current_disk:
                            _LOGGER.debug("Parsing temperature from line: %s for disk %s", line, current_disk)
                            try:
                                temp_match = re.search(r'Temperature_Celsius.*?(\d+)\s*[(\[]', line)
                                if temp_match:
                                    temp = int(temp_match.group(1))
                                    disk_info[current_disk]["temperature"] = temp
                                    _LOGGER.debug("Found temperature %d°C for disk %s", temp, current_disk)
                            except Exception as err:
                                _LOGGER.debug("Error parsing temperature for disk %s: %s", current_disk, err)
                    elif '===END' in line:
                        if current_disk and "status" not in disk_info[current_disk]:
                            disk_info[current_disk]["status"] = "unknown"
                            disk_info[current_disk]["smart_status"] = "Unknown"
                            disk_info[current_disk]["health"] = "Unknown"
                        current_disk = None

                _LOGGER.debug("Disk info after collection: %s", disk_info)
            
            return disk_info
        except Exception as err:
            _LOGGER.error("Error getting disk info: %s", str(err))
            return {}
        
    async def get_disk_spin_down_settings(self) -> dict[str, int]:
        """Fetch disk spin down delay settings from Unraid."""
        try:
            settings = await self.execute_command("cat /boot/config/disk.cfg")
            default_delay = 0  # Default to Never (0 minutes) if not found
            disk_delays = {}
            
            if settings.exit_status == 0:
                for line in settings.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                            
                    if line.startswith("spindownDelay="):
                        # Get the default delay, removing quotes and spaces
                        delay_value = line.split("=")[1].strip().strip('"')
                        try:
                            default_delay = int(delay_value)
                        except ValueError:
                            _LOGGER.warning("Invalid default spin down delay value: %s", delay_value)
                            
                    elif line.startswith("diskSpindownDelay."):
                        # Format is diskSpindownDelay.N=value where N is disk number
                        try:
                            disk_num = line.split(".")[1].split("=")[0]
                            delay_value = line.split("=")[1].strip().strip('"')
                            delay = int(delay_value)
                            
                            # -1 means use default delay
                            disk_delays[f"disk{disk_num}"] = default_delay if delay < 0 else delay
                            
                        except (IndexError, ValueError) as err:
                            _LOGGER.warning("Error parsing disk spin down setting '%s': %s", line, err)

                _LOGGER.debug(
                    "Disk spin down settings - Default: %s, Per-disk: %s",
                    "Never" if default_delay == 0 else f"{default_delay} minutes",
                    disk_delays
                )
                
            return {"default": default_delay, **disk_delays}
            
        except Exception as err:
            _LOGGER.error("Error getting disk spin down settings: %s", err)
            return {"default": 0}  # Return Never (0 minutes) if error
    
    async def get_individual_disk_usage(self) -> List[Dict[str, Any]]:
        """Fetch Individual Disk information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching individual disk usage and temperatures")
            # Get disk info (includes models, temps, and SMART status)
            disk_info = await self.get_disk_info()
            
            # Get spin down settings
            spin_down_settings = await self.get_disk_spin_down_settings()
            default_delay = spin_down_settings.get("default", 0)  # Default to Never
            
            # Sort disks by size (excluding cache)
            data_disks = {k: v for k, v in disk_info.items()
                        if k != 'sda' and k != 'sdb' and 'size' in v}
            sorted_disks = sorted(data_disks.items(), key=lambda x: x[1]['size'])
            
            disks = []
            disk_num = 1  # Counter for disk1, disk2, etc.
            
            # Get disk usage info
            disk_command = (
                "df -k /mnt/disk[0-9]* 2>/dev/null | "
                "awk 'NR>1 && $1 !~ /tmpfs/ {printf \"%s;%s;%s;%s;%s\\n\", $6,$2,$3,$4,$1}'"
            )
            result = await self.execute_command(disk_command)
            if result.exit_status != 0:
                return []

            for line in result.stdout.splitlines():
                try:
                    mount_point, total, used, free, device = line.split(';')
                    disk_name = mount_point.split('/')[-1]
                    
                    if not disk_name.replace('disk', '').isdigit():
                        continue
                        
                    total = int(total) * 1024  # Convert to bytes
                    used = int(used) * 1024
                    free = int(free) * 1024
                    percentage = (used / total) * 100 if total > 0 else 0

                    # Map to physical device based on size/position
                    if 0 <= disk_num - 1 < len(sorted_disks):
                        physical_device, device_info = sorted_disks[disk_num - 1]
                    else:
                        physical_device = "unknown"
                        device_info = {}

                    disk_data = {
                        "name": disk_name,
                        "device": physical_device,
                        "model": device_info.get("model", "Unknown"),
                        "mount_point": mount_point,
                        "percentage": round(percentage, 2),
                        "total": total,
                        "used": used,
                        "free": free,
                        "status": device_info.get("status", "unknown"),
                        "health": device_info.get("smart_status", "Unknown"),  # Map smart_status to health
                        "spin_down_delay": spin_down_settings.get(disk_name, default_delay),
                    }

                    # Add temperature if available
                    if "temperature" in device_info:
                        disk_data["temperature"] = device_info["temperature"]

                    disks.append(disk_data)
                    _LOGGER.debug(
                        "Disk mapping: %s -> %s (Temp: %s, Status: %s, Health: %s, Spin down: %d min)",
                        disk_name,
                        physical_device,
                        f"{device_info.get('temperature', 'N/A')}°C" if device_info.get('temperature') is not None else 'N/A',
                        device_info.get('status', 'unknown'),
                        device_info.get('smart_status', 'Unknown'),
                        spin_down_settings.get(disk_name, default_delay)
                    )
                    disk_num += 1
                    
                except Exception as err:
                    _LOGGER.debug("Error processing disk %s: %s", disk_name, err)
                    continue

            return disks
        except Exception as e:
            _LOGGER.error("Error getting individual disk usage: %s", str(e))
            return []

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
        except Exception as e:
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
        except Exception as e:
            _LOGGER.error("Error getting memory usage: %s", str(e))
            return {"percentage": None}

    async def _get_array_usage(self) -> Dict[str, Optional[float]]:
        """Fetch Array information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching array usage")
            result = await self.execute_command("df -k /mnt/user | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error("Array usage command failed with exit status %d", result.exit_status)
                return {"percentage": None, "total": None, "used": None, "free": None}
            
            total, used, free = map(int, result.stdout.strip().split())
            percentage = (used / total) * 100
            
            return {
                "percentage": round(percentage, 2),
                "total": total * 1024,  # Convert to bytes
                "used": used * 1024,    # Convert to bytes
                "free": free * 1024     # Convert to bytes
            }
        except Exception as e:
            _LOGGER.error("Error getting array usage: %s", str(e))
            return {"percentage": None, "total": None, "used": None, "free": None}
        
    async def _get_cache_usage(self) -> Dict[str, Optional[float]]:
        """Fetch cache information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching cache usage")
            result = await self.execute_command("df -k /mnt/cache | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error("Cache usage command failed with exit status %d", result.exit_status)
                return {"percentage": None, "total": None, "used": None, "free": None}
            
            total, used, free = map(int, result.stdout.strip().split())
            percentage = (used / total) * 100
            
            return {
                "percentage": round(percentage, 2),
                "total": total * 1024,  # Convert to bytes
                "used": used * 1024,    # Convert to bytes
                "free": free * 1024     # Convert to bytes
            }
        except Exception as e:
            _LOGGER.error("Error getting cache usage: %s", str(e))
            return {"percentage": None, "total": None, "used": None, "free": None}

    async def _get_boot_usage(self) -> Dict[str, Optional[float]]:
        """Fetch boot information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching boot usage")
            result = await self.execute_command("df -k /boot | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error("Boot usage command failed with exit status %d", result.exit_status)
                return {"percentage": None, "total": None, "used": None, "free": None}
            
            total, used, free = map(int, result.stdout.strip().split())
            percentage = (used / total) * 100
            
            return {
                "percentage": round(percentage, 2),
                "total": total * 1024,  # Convert to bytes
                "used": used * 1024,    # Convert to bytes
                "free": free * 1024     # Convert to bytes
            }
        except Exception as e:
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
        except Exception as e:
            _LOGGER.error("Error getting uptime: %s", str(e))
            return None

    async def detect_ups(self) -> bool:
        """Attempt to detect if a UPS is connected."""
        try:
            result = await self.execute_command("which apcaccess")
            if result.exit_status == 0:
                # apcaccess is installed, now check if it can communicate with a UPS
                result = await self.execute_command("apcaccess status")
                return result.exit_status == 0
            return False
        except Exception as e:
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
        except Exception as e:
            _LOGGER.debug("Error getting UPS info (apcupsd might not be installed): %s", str(e))
            return {}

    async def get_temperature_data(self) -> Dict[str, Any]:
        """Fetch temperature information from the Unraid system."""
        temp_data = {}
        
        try:
            _LOGGER.debug("Fetching temperature data")
            result = await self.execute_command("sensors")
            if result.exit_status == 0:
                temp_data['sensors'] = self._parse_sensors_output(result.stdout)
        except Exception as e:
            _LOGGER.error("Error getting sensors data: %s", str(e))

        try:
            result = await self.execute_command("paste <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp)")
            if result.exit_status == 0:
                temp_data['thermal_zones'] = self._parse_thermal_zones(result.stdout)
        except Exception as e:
            _LOGGER.error("Error getting thermal zone data: %s", str(e))

        return temp_data

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
        except Exception as err:
            _LOGGER.error("Error getting interface info for %s: %s", interface, err)
            return "Interface Down"

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
                        except Exception as err:
                            _LOGGER.debug(
                                "Error getting stats for interface %s: %s", 
                                interface, 
                                err
                            )
                            continue

            return network_stats
                
        except Exception as err:
            _LOGGER.error("Error getting network stats: %s", str(err))
            return {}

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
                
        except Exception as err:
            _LOGGER.debug("Error getting system timezone: %s", err)
        
        return "UTC"  # Default to UTC instead of PST

    async def _parse_parity_log_line(self, line: str) -> tuple[datetime, int, float, int]:
        """Parse a parity check log line.
        
        Format: timestamp|duration|speed|errors|unknown|type|size
        Returns: (timestamp, duration_seconds, speed_kbs, errors)
        """
        try:
            parts = line.strip().split('|')
            if len(parts) >= 7:
                # Parse timestamp
                ts_str = parts[0]
                timestamp = datetime.strptime(ts_str, "%Y %b %d %H:%M:%S")
                
                # Parse other fields
                duration_secs = int(parts[1])
                speed_kbs = float(parts[2])
                errors = int(parts[3])
                
                return timestamp, duration_secs, speed_kbs, errors
        except Exception as err:
            _LOGGER.debug("Error parsing parity log line: %s", err)
        return None

    async def has_parity_configured(self) -> bool:
        """Check if the system has parity configured."""
        try:
            # Check mdstat for parity info
            mdstat_result = await self.execute_command("cat /proc/mdstat")
            if mdstat_result.exit_status == 0:
                mdstat_lines = mdstat_result.stdout.splitlines()
                
                # Look for parity indicators
                for line in mdstat_lines:
                    # Check for parity resync action
                    if line.startswith("mdResyncAction="):
                        action = line.split("=")[1].strip()
                        if "P" in action:  # Either "check P" or similar
                            return True
                            
                    # Also check for disk0 being a parity device
                    elif line.startswith("diskNumber.0="):
                        next_lines = mdstat_lines[mdstat_lines.index(line):mdstat_lines.index(line)+5]
                        # Check if disk0 exists and is active (state 7)
                        if any("diskState.0=7" in nl for nl in next_lines):
                            return True

            return False
            
        except Exception as err:
            _LOGGER.debug("Error checking parity configuration: %s", err)
            return False

    async def get_parity_status(self) -> Dict[str, Any]:
        """Fetch parity check information from the Unraid system."""
        try:
            data = {
                "has_parity": False,  # Default to no parity
                "is_active": False,
                "last_check": None,
                "next_check": None,
                "speed": None,
                "avg_speed": None,
                "progress": 0.0,  # Default to 0%
                "status": "unknown",
                "errors": 0,
                "duration": None,
                "estimated_completion": None,
            }

            # Check mdstat for active check
            mdstat_result = await self.execute_command("cat /proc/mdstat")
            if mdstat_result.exit_status == 0:
                mdstat_lines = mdstat_result.stdout.splitlines()
                for line in mdstat_lines:
                    if line.startswith("mdResyncAction="):
                        action = line.split("=")[1].strip()
                        if "check P" in action:
                            data["is_active"] = True
                            data["status"] = "checking"
                            data["has_parity"] = True
                    elif data["is_active"] and line.startswith("mdResyncPos="):
                        try:
                            pos = int(line.split("=")[1])
                            size = next(
                                (int(l.split("=")[1]) for l in mdstat_lines if l.startswith("mdResyncSize=")),
                                0
                            )
                            if size > 0:
                                data["progress"] = (pos / size) * 100
                        except (ValueError, TypeError):
                            pass
                    elif data["is_active"] and line.startswith("mdResyncDt="):
                        try:
                            dt = int(line.split("=")[1])
                            if dt > 0:
                                data["speed"] = (dt * 512) / (1024 * 1024)  # Convert to MB/s
                        except (ValueError, TypeError):
                            pass

            # Get history information
            if history := await self.execute_command("cat /boot/config/parity-checks.log"):
                if history.exit_status == 0 and history.stdout.strip():
                    try:
                        last_line = history.stdout.strip().split('\n')[-1]
                        if last_line:
                            parts = last_line.split('|')
                            if len(parts) >= 4:
                                data["last_check"] = datetime.strptime(parts[0], "%Y %b %d %H:%M:%S")
                                data["duration"] = self._format_duration(parts[1])
                                data["avg_speed"] = float(parts[2]) / 1024  # Convert to MB/s
                                data["errors"] = int(parts[3])
                    except Exception as err:
                        _LOGGER.debug("Error parsing history: %s", err)

            return data

        except Exception as err:
            _LOGGER.error("Error getting parity status: %s", str(err))
            return None

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
        except Exception as e:
            _LOGGER.error("Error getting log filesystem usage: %s", str(e))
            return {}

    async def _get_docker_vdisk_usage(self) -> Dict[str, Any]:
        """Fetch Docker vDisk information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching Docker vDisk usage")
            result = await self.execute_command("df -k /var/lib/docker | awk 'NR==2 {print $2,$3,$4,$5}'")
            if result.exit_status != 0:
                _LOGGER.error("Docker vDisk usage command failed with exit status %d", result.exit_status)
                return {}

            total, used, free, percentage = result.stdout.strip().split()
            return {
                "total": int(total) * 1024,
                "used": int(used) * 1024,
                "free": int(free) * 1024,
                "percentage": float(percentage.strip('%'))
            }
        except Exception as e:
            _LOGGER.error("Error getting Docker vDisk usage: %s", str(e))
            return {}

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Fetch information about Docker containers."""
        try:
            _LOGGER.debug("Fetching Docker container information")
            # Get basic container info with proven format
            result = await self.execute_command("docker ps -a --format '{{.Names}}|{{.State}}|{{.ID}}|{{.Image}}'")
            if result.exit_status != 0:
                _LOGGER.error("Docker container list command failed with exit status %d", result.exit_status)
                return []

            containers = []
            for line in result.stdout.splitlines():
                parts = line.split('|')
                if len(parts) == 4:  # Now expecting 4 parts
                    container_name = parts[0].strip()
                    # Get container icon if available
                    icon_path = f"/var/lib/docker/unraid/images/{container_name}-icon.png"
                    icon_result = await self.execute_command(
                        f"[ -f {icon_path} ] && (base64 {icon_path}) || echo ''"
                    )
                    icon_data = icon_result.stdout[0] if icon_result.exit_status == 0 else ""

                    containers.append({
                        "name": container_name,
                        "state": ContainerStates.parse(parts[1].strip()),
                        "status": parts[1].strip(),
                        "id": parts[2].strip(),
                        "image": parts[3].strip(),
                        "icon": icon_data
                    })
                else:
                    _LOGGER.warning("Unexpected format in docker container output: %s", line)

            return containers
        except Exception as e:
            _LOGGER.error("Error getting docker containers: %s", str(e))
            return []
        
    async def start_container(self, container_name: str) -> bool:
        """Start a Docker container."""
        try:
            _LOGGER.debug("Starting container: %s", container_name)
            result = await self.execute_command(f'docker start "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to start container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s started successfully", container_name)
            return True
        except Exception as e:
            _LOGGER.error("Error starting container %s: %s", container_name, str(e))
            return False

    async def stop_container(self, container_name: str) -> bool:
        """Stop a Docker container."""
        try:
            _LOGGER.debug("Stopping container: %s", container_name)
            result = await self.execute_command(f'docker stop "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to stop container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s stopped successfully", container_name)
            return True
        except Exception as e:
            _LOGGER.error("Error stopping container %s: %s", container_name, str(e))
            return False

    async def get_vms(self) -> List[Dict[str, Any]]:
        """Fetch information about virtual machines."""
        try:
            _LOGGER.debug("Fetching VM information")
            # Use list --all with a more reliable format
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.error("VM list command failed with exit status %d", result.exit_status)
                return []

            vms = []
            for line in result.stdout.splitlines():
                # Skip empty lines
                if not line.strip():
                    continue

                try:
                    vm_name = line.strip()
                    # Get status directly using the exact name
                    status = await self.get_vm_status(vm_name)
                    os_type = await self.get_vm_os_info(vm_name)
                    
                    vms.append({
                        "name": vm_name,
                        "status": status,
                        "os_type": os_type
                    })

                except Exception as parse_error:
                    _LOGGER.warning("Error processing VM '%s': %s", line.strip(), str(parse_error))
                    continue

            return vms

        except Exception as e:
            _LOGGER.error("Error getting VMs: %s", str(e))
            return []
        
    async def get_vm_os_info(self, vm_name: str) -> str:
        """Get the OS type of a VM."""
        try:
            escaped_name = shlex.quote(vm_name)
            
            # Try to get OS info from multiple sources
            xml_result = await self.execute_command(
                f'virsh dumpxml {escaped_name} | grep -A5 "<os>"'
            )
            
            if xml_result.exit_status == 0:
                xml_output = xml_result.stdout.lower()
                if 'windows' in xml_output or 'win' in xml_output:
                    return 'windows'
                if 'linux' in xml_output:
                    return 'linux'

            # Check VM name patterns
            name_lower = vm_name.lower()
            name_clean = name_lower.replace('-', ' ').replace('_', ' ')
            
            # Check for Windows indicators
            if any(term in name_clean for term in ['windows', 'win']):
                return 'windows'
            
            # Check for Linux indicators
            if any(term in name_clean for term in [
                'ubuntu', 'linux', 'debian', 'centos', 
                'fedora', 'rhel', 'suse', 'arch'
            ]):
                return 'linux'
            
            return 'unknown'
            
        except Exception as e:
            _LOGGER.debug(
                "Error getting OS info for VM '%s': %s", 
                vm_name, 
                str(e)
            )
            return 'unknown'

    async def get_vm_status(self, vm_name: str) -> str:
        """Get detailed status of a specific virtual machine."""
        try:
            # Double-quote the VM name for virsh
            quoted_name = f'"{vm_name}"'
            result = await self.execute_command(f"virsh domstate {quoted_name}")
            if result.exit_status != 0:
                _LOGGER.error("Failed to get VM status for '%s': %s", vm_name, result.stderr)
                return VMState.CRASHED.value
            return VMState.parse(result.stdout.strip())
        except Exception as e:
            _LOGGER.error("Error getting VM status for '%s': %s", vm_name, str(e))
            return VMState.CRASHED.value

    async def start_vm(self, vm_name: str) -> bool:
        """Start a virtual machine."""
        try:
            _LOGGER.debug("Starting VM: %s", vm_name)
            quoted_name = f'"{vm_name}"'
            
            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "running":
                _LOGGER.info("VM '%s' is already running", vm_name)
                return True
                
            result = await self.execute_command(f"virsh start {quoted_name}")
            success = result.exit_status == 0
            
            if not success:
                _LOGGER.error("Failed to start VM '%s': %s", vm_name, result.stderr)
                return False
                
            # Wait for VM to start
            for _ in range(15):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "running":
                    _LOGGER.info("Successfully started VM '%s'", vm_name)
                    return True
                    
            _LOGGER.error("VM '%s' did not reach running state in time", vm_name)
            return False
            
        except Exception as e:
            _LOGGER.error("Error starting VM '%s': %s", vm_name, str(e))
            return False

    async def stop_vm(self, vm_name: str) -> bool:
        """Stop a virtual machine using ACPI shutdown."""
        try:
            _LOGGER.debug("Stopping VM: %s", vm_name)
            quoted_name = f'"{vm_name}"'
            
            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "shut off":
                _LOGGER.info("VM '%s' is already shut off", vm_name)
                return True
                
            result = await self.execute_command(f"virsh shutdown {quoted_name}")
            success = result.exit_status == 0
            
            if not success:
                _LOGGER.error("Failed to stop VM '%s': %s", vm_name, result.stderr)
                return False
                
            # Wait for VM to stop
            for _ in range(30):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "shut off":
                    _LOGGER.info("Successfully stopped VM '%s'", vm_name)
                    return True
                    
            _LOGGER.error("VM '%s' did not shut off in time", vm_name)
            return False
            
        except Exception as e:
            _LOGGER.error("Error stopping VM '%s': %s", vm_name, str(e))
            return False

    async def get_user_scripts(self) -> List[Dict[str, Any]]:
        """Fetch information about user scripts."""
        try:
            _LOGGER.debug("Fetching user scripts")
            # Check if user scripts plugin is installed first
            check_result = await self.execute_command(
                "[ -d /boot/config/plugins/user.scripts/scripts ] && echo 'exists'"
            )
            
            if check_result.exit_status == 0 and "exists" in check_result.stdout:
                result = await self.execute_command(
                    "ls -1 /boot/config/plugins/user.scripts/scripts 2>/dev/null"
                )
                if result.exit_status == 0:
                    return [{"name": script.strip()} for script in result.stdout.splitlines()]
                
            # If not installed or no scripts, return empty list without error
            return []
        except Exception as e:
            _LOGGER.debug("Error getting user scripts (plugin might not be installed): %s", str(e))
            return []

    async def execute_user_script(self, script_name: str, background: bool = False) -> str:
        """Execute a user script."""
        try:
            _LOGGER.debug("Executing user script: %s", script_name)
            command = f"/usr/local/emhttp/plugins/user.scripts/scripts/{script_name}"
            if background:
                command += " & > /dev/null 2>&1"
            result = await self.execute_command(command)
            if result.exit_status != 0:
                _LOGGER.error("User script %s failed with exit status %d", script_name, result.exit_status)
                return ""
            return result.stdout
        except Exception as e:
            _LOGGER.error("Error executing user script %s: %s", script_name, str(e))
            return ""

    async def stop_user_script(self, script_name: str) -> str:
        """Stop a user script."""
        try:
            _LOGGER.debug("Stopping user script: %s", script_name)
            result = await self.execute_command(f"pkill -f '{script_name}'")
            if result.exit_status != 0:
                _LOGGER.error("Stopping user script %s failed with exit status %d", script_name, result.exit_status)
                return ""
            return result.stdout
        except Exception as e:
            _LOGGER.error("Error stopping user script %s: %s", script_name, str(e))
            return ""

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
                msg = f"Reboot command failed: {result.stderr}"
                _LOGGER.error(msg)
                raise HomeAssistantError(msg)

            _LOGGER.info("Reboot command executed successfully")
            return True

        except Exception as err:
            msg = f"Error during reboot: {str(err)}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg) from err

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
                msg = f"Shutdown command failed: {result.stderr}"
                _LOGGER.error(msg)
                raise HomeAssistantError(msg)

            _LOGGER.info("Shutdown command executed successfully")
            return True

        except Exception as err:
            msg = f"Error during shutdown: {str(err)}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg) from err

    async def __aenter__(self):
        await self.ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()