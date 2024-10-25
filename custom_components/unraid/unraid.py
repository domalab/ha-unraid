"""API client for Unraid."""
import asyncio
import asyncssh
import logging
from typing import Dict, List, Any, Optional
import re
from async_timeout import timeout
from enum import Enum
import json

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
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.error("VM list command failed with exit status %d", result.exit_status)
                return []
            
            vms = []
            for line in result.stdout.splitlines():
                if line.strip():
                    name = line.strip()
                    status = await self.get_vm_status(name)
                    os_type = await self.get_vm_os_info(name)
                    vms.append({
                        "name": name, 
                        "status": status,
                        "os_type": os_type
                    })
            return vms
        except Exception as e:
            _LOGGER.error("Error getting VMs: %s", str(e))
            return []
        
    async def get_vm_os_info(self, vm_name: str) -> str:
        """Get the OS type of a VM."""
        try:
            # First try to get OS info from VM XML
            result = await self.execute_command(f'virsh dumpxml "{vm_name}" | grep "<os>"')
            xml_output = result.stdout

            # Check for Windows-specific indicators
            if any(indicator in '\n'.join(xml_output).lower() for indicator in ['windows', 'win', 'microsoft']):
                return 'windows'
            
            # Try to get detailed OS info if available
            result = await self.execute_command(f'virsh domosinfo "{vm_name}" 2>/dev/null')
            if result.exit_status == 0:
                os_info = '\n'.join(result.stdout).lower()
                if any(indicator in os_info for indicator in ['windows', 'win', 'microsoft']):
                    return 'windows'
                elif any(indicator in os_info for indicator in ['linux', 'unix', 'ubuntu', 'debian', 'centos', 'fedora', 'rhel']):
                    return 'linux'
            
            # Default to checking common paths in VM name
            vm_name_lower = vm_name.lower()
            if any(win_term in vm_name_lower for win_term in ['windows', 'win']):
                return 'windows'
            elif any(linux_term in vm_name_lower for linux_term in ['linux', 'ubuntu', 'debian', 'centos', 'fedora', 'rhel']):
                return 'linux'
            
            return 'unknown'
        except Exception as e:
            _LOGGER.debug("Error getting OS info for VM %s: %s", vm_name, str(e))
            return 'unknown'

    async def get_vm_status(self, vm_name: str) -> str:
        """Get detailed status of a specific virtual machine."""
        try:
            result = await self.execute_command(f"virsh domstate {vm_name}")
            if result.exit_status != 0:
                _LOGGER.error("Failed to get VM status for %s: %s", vm_name, result.stderr)
                return VMState.CRASHED.value
            return VMState.parse(result.stdout.strip())
        except Exception as e:
            _LOGGER.error("Error getting VM status for %s: %s", vm_name, str(e))
            return VMState.CRASHED.value

    async def stop_vm(self, vm_name: str) -> bool:
        """Stop a virtual machine using ACPI shutdown."""
        try:
            _LOGGER.debug("Stopping VM: %s", vm_name)
            result = await self.execute_command(f'virsh shutdown "{vm_name}" --mode acpi')
            success = result.exit_status == 0
            
            if success:
                # Wait for the VM to actually shut down
                for _ in range(30):  # Wait up to 60 seconds
                    await asyncio.sleep(2)
                    status = await self.get_vm_status(vm_name)
                    if status == VMState.STOPPED.value:
                        return True
                return False
            return False
        except Exception as e:
            _LOGGER.error("Error stopping VM %s: %s", vm_name, str(e))
            return False

    async def start_vm(self, vm_name: str) -> bool:
        """Start a virtual machine and wait for it to be running."""
        try:
            _LOGGER.debug("Starting VM: %s", vm_name)
            result = await self.execute_command(f'virsh start "{vm_name}"')
            success = result.exit_status == 0
            
            if success:
                # Wait for the VM to actually start
                for _ in range(15):  # Wait up to 30 seconds
                    await asyncio.sleep(2)
                    status = await self.get_vm_status(vm_name)
                    if status == VMState.RUNNING.value:
                        return True
                return False
            return False
        except Exception as e:
            _LOGGER.error("Error starting VM %s: %s", vm_name, str(e))
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
        
    async def get_array_status(self) -> str:
        """Get current array status."""
        try:
            result = await self.execute_command("/usr/local/sbin/emcmd status")
            if result.exit_status != 0:
                _LOGGER.error("Failed to get array status: %s", result.stderr)
                return "unknown"
            # Array states: Started, Stopped, Starting, Stopping
            status = result.stdout.strip().lower()
            return status
        except Exception as e:
            _LOGGER.error("Error getting array status: %s", str(e))
            return "unknown"

    async def array_stop(self, ignore_lock: bool = False) -> bool:
        """Stop the Unraid array with safety checks."""
        try:
            # Check if array is already stopped
            status = await self.get_array_status()
            if status == "stopped":
                _LOGGER.warning("Array is already stopped")
                return True
            
            if status == "stopping":
                _LOGGER.warning("Array is already in the process of stopping")
                return True

            # Check for active transfers/mover operations
            result = await self.execute_command("ps aux | grep -E 'mover|rsync|cp|mv' | grep -v grep")
            if result.stdout.strip() and not ignore_lock:
                _LOGGER.error("Active file operations detected. Cannot safely stop array")
                raise HomeAssistantError("Cannot stop array: Active file operations detected")

            _LOGGER.info("Stopping Unraid array")
            result = await self.execute_command("/usr/local/sbin/emcmd stop")
            
            if result.exit_status != 0:
                _LOGGER.error("Failed to stop array: %s", result.stderr)
                raise HomeAssistantError(f"Failed to stop array: {result.stderr}")

            # Wait for array to begin stopping
            for _ in range(5):  # 5 second timeout
                if await self.get_array_status() in ["stopping", "stopped"]:
                    _LOGGER.info("Array stop command executed successfully")
                    return True
                await asyncio.sleep(1)

            raise HomeAssistantError("Array did not enter stopping state")

        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error("Error stopping array: %s", str(e))
            raise HomeAssistantError(f"Unexpected error stopping array: {str(e)}")

    async def system_reboot(self, delay: int = 0) -> bool:
        """Reboot the Unraid system with safety checks."""
        try:
            # Check for active transfers/mover operations
            result = await self.execute_command("ps aux | grep -E 'mover|rsync|cp|mv' | grep -v grep")
            if result.stdout.strip():
                _LOGGER.error("Active file operations detected. Cannot safely reboot")
                raise HomeAssistantError("Cannot reboot: Active file operations detected")

            # Check VM status
            vms = await self.get_vms()
            running_vms = [vm["name"] for vm in vms if vm["status"] == "running"]
            if running_vms:
                _LOGGER.error("Running VMs detected: %s", ", ".join(running_vms))
                raise HomeAssistantError(f"Cannot reboot: Running VMs detected: {', '.join(running_vms)}")

            # Check Docker container status
            containers = await self.get_docker_containers()
            running_containers = [c["name"] for c in containers if c["state"] == "running"]
            if running_containers:
                _LOGGER.warning("Running containers will be stopped: %s", ", ".join(running_containers))

            if delay > 0:
                _LOGGER.info("Scheduled reboot in %d seconds", delay)
                reboot_cmd = f"shutdown -r +{delay//60}"
            else:
                reboot_cmd = "shutdown -r now"

            _LOGGER.info("Executing reboot command: %s", reboot_cmd)
            result = await self.execute_command(reboot_cmd)
            
            if result.exit_status != 0:
                _LOGGER.error("Failed to reboot system: %s", result.stderr)
                raise HomeAssistantError(f"Failed to reboot system: {result.stderr}")

            _LOGGER.info("System reboot command executed successfully")
            return True

        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error("Error rebooting system: %s", str(e))
            raise HomeAssistantError(f"Unexpected error rebooting system: {str(e)}")

    async def system_shutdown(self, delay: int = 0) -> bool:
        """Shutdown the Unraid system with safety checks."""
        try:
            # Check for active transfers/mover operations
            result = await self.execute_command("ps aux | grep -E 'mover|rsync|cp|mv' | grep -v grep")
            if result.stdout.strip():
                _LOGGER.error("Active file operations detected. Cannot safely shutdown")
                raise HomeAssistantError("Cannot shutdown: Active file operations detected")

            # Check array status
            array_status = await self.get_array_status()
            if array_status not in ["stopped", "stopping"]:
                _LOGGER.error("Array must be stopped before shutdown")
                raise HomeAssistantError("Cannot shutdown: Array must be stopped first")

            # Check VM status
            vms = await self.get_vms()
            running_vms = [vm["name"] for vm in vms if vm["status"] == "running"]
            if running_vms:
                _LOGGER.error("Running VMs detected: %s", ", ".join(running_vms))
                raise HomeAssistantError(f"Cannot shutdown: Running VMs detected: {', '.join(running_vms)}")

            # Check Docker container status
            containers = await self.get_docker_containers()
            running_containers = [c["name"] for c in containers if c["state"] == "running"]
            if running_containers:
                _LOGGER.warning("Running containers will be stopped: %s", ", ".join(running_containers))

            if delay > 0:
                _LOGGER.info("Scheduled shutdown in %d seconds", delay)
                shutdown_cmd = f"shutdown +{delay//60}"
            else:
                shutdown_cmd = "shutdown now"

            _LOGGER.info("Executing shutdown command: %s", shutdown_cmd)
            result = await self.execute_command(shutdown_cmd)
            
            if result.exit_status != 0:
                _LOGGER.error("Failed to shutdown system: %s", result.stderr)
                raise HomeAssistantError(f"Failed to shutdown system: {result.stderr}")

            _LOGGER.info("System shutdown command executed successfully")
            return True

        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error("Error shutting down system: %s", str(e))
            raise HomeAssistantError(f"Unexpected error shutting down system: {str(e)}")

    async def __aenter__(self):
        await self.ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()