"""API client for Unraid."""
import asyncio
import asyncssh
import logging
from typing import Dict, List, Any, Optional
import re
from async_timeout import timeout

_LOGGER = logging.getLogger(__name__)

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
    
    async def get_individual_disk_usage(self) -> List[Dict[str, Any]]:
        """Fetch Individual Disk information from the Unraid system."""
        try:
            _LOGGER.debug("Fetching individual disk usage")
            result = await self.execute_command("df -k /mnt/disk* | awk 'NR>1 {print $6,$2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error("Individual disk usage command failed with exit status %d", result.exit_status)
                return []

            disks = []
            for line in result.stdout.splitlines():
                mount_point, total, used, free = line.split()
                disk_name = mount_point.split('/')[-1]
                if disk_name.startswith('disk'):  # Only include actual disks, not tmpfs
                    total = int(total) * 1024  # Convert to bytes
                    used = int(used) * 1024    # Convert to bytes
                    free = int(free) * 1024    # Convert to bytes
                    percentage = (used / total) * 100 if total > 0 else 0

                    disks.append({
                        "name": disk_name,
                        "mount_point": mount_point,
                        "percentage": round(percentage, 2),
                        "total": total,
                        "used": used,
                        "free": free
                    })

            _LOGGER.debug("Retrieved information for %d disks", len(disks))
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
            result = await self.execute_command("apcaccess status")
            if result.exit_status != 0:
                _LOGGER.error("UPS info command failed with exit status %d", result.exit_status)
                return {}
            
            ups_data = {}
            for line in result.stdout.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    ups_data[key.strip()] = value.strip()
            return ups_data
        except Exception as e:
            _LOGGER.error("Error getting UPS info: %s", str(e))
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
            result = await self.execute_command("docker ps -a --format '{{.Names}}|{{.State}}'")
            if result.exit_status != 0:
                _LOGGER.error("Docker container list command failed with exit status %d", result.exit_status)
                return []
            
            containers = []
            for line in result.stdout.splitlines():
                parts = line.split('|')
                if len(parts) == 2:
                    containers.append({"name": parts[0], "status": parts[1]})
                else:
                    _LOGGER.warning("Unexpected format in docker container output: %s", line)
            return containers
        except Exception as e:
            _LOGGER.error("Error getting docker containers: %s", str(e))
            return []
        
    async def start_container(self, container_name: str) -> bool:
        """Start a Docker container."""
        try:
            _LOGGER.debug("Starting Docker container: %s", container_name)
            result = await self.execute_command(f"docker start {container_name}")
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
            _LOGGER.debug("Stopping Docker container: %s", container_name)
            result = await self.execute_command(f"docker stop {container_name}")
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
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.error("VM list command failed with exit status %d", result.exit_status)
                return []
            
            vms = []
            for line in result.stdout.splitlines():
                if line.strip():
                    name = line.strip()
                    status = await self._get_vm_status(name)
                    vms.append({"name": name, "status": status})
            return vms
        except Exception as e:
            _LOGGER.error("Error getting VMs: %s", str(e))
            return []

    async def _get_vm_status(self, vm_name: str) -> str:
        """Get the status of a specific virtual machine."""
        try:
            result = await self.execute_command(f"virsh domstate {vm_name}")
            if result.exit_status != 0:
                _LOGGER.error("VM status command for %s failed with exit status %d", vm_name, result.exit_status)
                return "unknown"
            return result.stdout.strip()
        except Exception as e:
            _LOGGER.error("Error getting VM status for %s: %s", vm_name, str(e))
            return "unknown"

    async def start_vm(self, vm_name: str) -> bool:
        """Start a virtual machine."""
        try:
            _LOGGER.debug("Starting VM: %s", vm_name)
            result = await self.execute_command(f"virsh start {vm_name}")
            return result.exit_status == 0 and "started" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error("Error starting VM %s: %s", vm_name, str(e))
            return False

    async def stop_vm(self, vm_name: str) -> bool:
        """Stop a virtual machine."""
        try:
            _LOGGER.debug("Stopping VM: %s", vm_name)
            result = await self.execute_command(f"virsh shutdown {vm_name}")
            return result.exit_status == 0 and "shutting down" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error("Error stopping VM %s: %s", vm_name, str(e))
            return False

    async def get_user_scripts(self) -> List[Dict[str, Any]]:
        """Fetch information about user scripts."""
        try:
            _LOGGER.debug("Fetching user scripts")
            result = await self.execute_command("ls -1 /boot/config/plugins/user.scripts/scripts")
            if result.exit_status != 0:
                _LOGGER.error("User scripts list command failed with exit status %d", result.exit_status)
                return []
            return [{"name": script.strip()} for script in result.stdout.splitlines()]
        except Exception as e:
            _LOGGER.error("Error getting user scripts: %s", str(e))
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

    async def __aenter__(self):
        await self.ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()