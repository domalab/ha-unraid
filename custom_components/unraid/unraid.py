"""API client for Unraid."""
import asyncio
import asyncssh
import logging
from typing import Dict, List, Any, Optional
import re

_LOGGER = logging.getLogger(__name__)

class UnraidAPI:
    def __init__(self, host: str, username: str, password: str, port: int = 22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.conn = None

    async def connect(self):
        self.conn = await asyncssh.connect(
            self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            known_hosts=None
        )

    async def disconnect(self):
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()

    async def ping(self) -> bool:
        """Check if the Unraid server is accessible via SSH."""
        try:
            async with asyncssh.connect(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                known_hosts=None,
                connect_timeout=10
            ) as conn:
                # If we can connect, the server is reachable
                return True
        except (asyncio.TimeoutError, asyncssh.Error) as e:
            _LOGGER.debug(f"Failed to connect to Unraid server: {e}")
            return False

    async def execute_command(self, command: str) -> asyncssh.SSHCompletedProcess:
        if not self.conn:
            await self.connect()
        return await self.conn.run(command)

    async def get_system_stats(self) -> Dict[str, Any]:
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
            result = await self.execute_command("df -k /mnt/disk* | awk 'NR>1 {print $6,$2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Individual disk usage command failed with exit status {result.exit_status}")
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

            return disks
        except Exception as e:
            _LOGGER.error(f"Error getting individual disk usage: {e}")
            return []

    async def _get_log_filesystem_usage(self) -> Dict[str, Any]:
        """Fetch log filesystem information from the Unraid system."""
        try:
            result = await self.execute_command("df -k /var/log | awk 'NR==2 {print $2,$3,$4,$5}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Log filesystem usage command failed with exit status {result.exit_status}")
                return {}

            total, used, free, percentage = result.stdout.strip().split()
            return {
                "total": int(total) * 1024,
                "used": int(used) * 1024,
                "free": int(free) * 1024,
                "percentage": float(percentage.strip('%'))
            }
        except Exception as e:
            _LOGGER.error(f"Error getting log filesystem usage: {e}")
            return {}

    async def _get_docker_vdisk_usage(self) -> Dict[str, Any]:
        """Fetch Docker vDisk information from the Unraid system."""
        try:
            result = await self.execute_command("df -k /var/lib/docker | awk 'NR==2 {print $2,$3,$4,$5}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Docker vDisk usage command failed with exit status {result.exit_status}")
                return {}

            total, used, free, percentage = result.stdout.strip().split()
            return {
                "total": int(total) * 1024,
                "used": int(used) * 1024,
                "free": int(free) * 1024,
                "percentage": float(percentage.strip('%'))
            }
        except Exception as e:
            _LOGGER.error(f"Error getting Docker vDisk usage: {e}")
            return {}

    async def _get_cpu_usage(self) -> Optional[float]:
        """Fetch CPU information from the Unraid system."""
        try:
            result = await self.execute_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'")
            if result.exit_status != 0:
                _LOGGER.error(f"CPU usage command failed with exit status {result.exit_status}")
                return None
            
            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return round(float(match.group(1)), 2)
            else:
                _LOGGER.error(f"Failed to parse CPU usage from output: {result.stdout}")
                return None
        except Exception as e:
            _LOGGER.error(f"Error getting CPU usage: {e}")
            return None

    async def _get_memory_usage(self) -> Dict[str, Optional[float]]:
        """Fetch RAM information from the Unraid system."""
        try:
            result = await self.execute_command("free | awk '/Mem:/ {print $3/$2 * 100.0}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Memory usage command failed with exit status {result.exit_status}")
                return {"percentage": None}
            
            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return {"percentage": float(match.group(1))}
            else:
                _LOGGER.error(f"Failed to parse memory usage from output: {result.stdout}")
                return {"percentage": None}
        except Exception as e:
            _LOGGER.error(f"Error getting memory usage: {e}")
            return {"percentage": None}

    async def _get_array_usage(self) -> Dict[str, Optional[float]]:
        """Fetch Array information from the Unraid system."""
        try:
            result = await self.execute_command("df -k /mnt/user | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Array usage command failed with exit status {result.exit_status}")
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
            _LOGGER.error(f"Error getting array usage: {e}")
            return {"percentage": None, "total": None, "used": None, "free": None}

    async def _get_cache_usage(self) -> Dict[str, Optional[float]]:
        """Fetch cache information from the Unraid system."""
        try:
            result = await self.execute_command("df -k /mnt/cache | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Cache usage command failed with exit status {result.exit_status}")
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
            _LOGGER.error(f"Error getting cache usage: {e}")
            return {"percentage": None, "total": None, "used": None, "free": None}

    async def _get_boot_usage(self) -> Dict[str, Optional[float]]:
        """Fetch boot information from the Unraid system."""
        try:
            result = await self.execute_command("df -k /boot | awk 'NR==2 {print $2,$3,$4}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Boot usage command failed with exit status {result.exit_status}")
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
            _LOGGER.error(f"Error getting boot usage: {e}")
            return {"percentage": None, "total": None, "used": None, "free": None}

    def _convert_to_bytes(self, size_str: str) -> float:
        """Convert a size string (e.g., '1.5P', '800T', '100G') to bytes."""
        units = {
            'B': 1,
            'K': 1024,
            'M': 1024**2,
            'G': 1024**3,
            'T': 1024**4,
            'P': 1024**5,
            'E': 1024**6,
        }
        match = re.match(r"([\d.]+)\s*([BKMGTPE])?", size_str, re.I)
        if not match:
            return 0.0
        
        number, unit = match.groups()
        number = float(number)
        unit = (unit or 'B').upper()  # Default to bytes if no unit is specified

        return number * units[unit]

    async def _get_uptime(self) -> Optional[float]:
        """Fetch Uptime information from the Unraid system."""
        try:
            result = await self.execute_command("awk '{print $1}' /proc/uptime")
            if result.exit_status != 0:
                _LOGGER.error(f"Uptime command failed with exit status {result.exit_status}")
                return None
            
            match = re.search(r'(\d+(\.\d+)?)', result.stdout)
            if match:
                return float(match.group(1))
            else:
                _LOGGER.error(f"Failed to parse uptime from output: {result.stdout}")
                return None
        except Exception as e:
            _LOGGER.error(f"Error getting uptime: {e}")
            return None

    async def get_ups_info(self) -> Dict[str, Any]:
        """Fetch UPS information from the Unraid system."""
        try:
            result = await self.execute_command("apcaccess status")
            if result.exit_status != 0:
                _LOGGER.error("UPS info command failed")
                return {}
            
            ups_data = {}
            for line in result.stdout.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    ups_data[key.strip()] = value.strip()
            return ups_data
        except Exception as e:
            _LOGGER.error(f"Error getting UPS info: {e}")
            return {}

    async def get_temperature_data(self):
        """Fetch temperature information from the Unraid system."""
        temp_data = {}
        
        # Get CPU and motherboard temperatures
        try:
            result = await self.execute_command("sensors")
            if result.exit_status == 0:
                temp_data['sensors'] = self._parse_sensors_output(result.stdout)
        except Exception as e:
            _LOGGER.error(f"Error getting sensors data: {e}")

        # Get thermal zone temperatures
        try:
            result = await self.execute_command("paste <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp)")
            if result.exit_status == 0:
                temp_data['thermal_zones'] = self._parse_thermal_zones(result.stdout)
        except Exception as e:
            _LOGGER.error(f"Error getting thermal zone data: {e}")

        return temp_data

    def _parse_sensors_output(self, output):
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

    def _parse_thermal_zones(self, output):
        thermal_zones = {}
        for line in output.splitlines():
            zone_type, temp = line.split()
            thermal_zones[zone_type] = float(temp) / 1000  # Convert milli-Celsius to Celsius
        return thermal_zones
    
    async def check_container_updates(self) -> List[Dict[str, str]]:
        """Check for available updates for Docker containers without updating them."""
        try:
            # Get list of running containers
            result = await self.execute_command("docker ps --format '{{.Image}}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Failed to get running containers. Exit status: {result.exit_status}, Stderr: {result.stderr}")
                return []

            running_images = result.stdout.splitlines()

            updates_available = []
            for image in running_images:
                # Get current image ID
                result = await self.execute_command(f"docker images {image} --format '{{{{.ID}}}}'")
                if result.exit_status != 0:
                    _LOGGER.error(f"Failed to get image ID for {image}. Exit status: {result.exit_status}, Stderr: {result.stderr}")
                    continue
                current_id = result.stdout.strip()

                # Pull the latest image
                result = await self.execute_command(f"docker pull {image}")
                if result.exit_status != 0:
                    _LOGGER.error(f"Failed to pull latest image for {image}. Exit status: {result.exit_status}, Stderr: {result.stderr}")
                    continue

                # Get new image ID
                result = await self.execute_command(f"docker images {image} --format '{{{{.ID}}}}'")
                if result.exit_status != 0:
                    _LOGGER.error(f"Failed to get new image ID for {image}. Exit status: {result.exit_status}, Stderr: {result.stderr}")
                    continue
                new_id = result.stdout.strip()

                # Compare IDs
                if current_id != new_id:
                    updates_available.append({"name": image, "current": current_id, "latest": new_id})

            return updates_available
        except Exception as e:
            _LOGGER.error(f"Error checking for container updates: {str(e)}")
            return []

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        try:
            result = await self.execute_command("docker ps -a --format '{{.Names}}|{{.State}}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Docker container list command failed with exit status {result.exit_status}")
                return []
            
            containers = []
            for line in result.stdout.splitlines():
                parts = line.split('|')
                if len(parts) == 2:
                    containers.append({"name": parts[0], "status": parts[1]})
                else:
                    _LOGGER.warning(f"Unexpected format in docker container output: {line}")
            return containers
        except Exception as e:
            _LOGGER.error(f"Error getting docker containers: {e}")
            return []
        
    async def start_container(self, container_name: str) -> bool:
        """Start a Docker container."""
        try:
            result = await self.execute_command(f"docker start {container_name}")
            if result.exit_status != 0:
                _LOGGER.error(f"Failed to start container {container_name}: {result.stderr}")
                return False
            _LOGGER.info(f"Container {container_name} started successfully")
            return True
        except Exception as e:
            _LOGGER.error(f"Error starting container {container_name}: {e}")
            return False
        
    async def stop_container(self, container_name: str) -> bool:
        """Stop a Docker container."""
        try:
            result = await self.execute_command(f"docker stop {container_name}")
            if result.exit_status != 0:
                _LOGGER.error(f"Failed to stop container {container_name}: {result.stderr}")
                return False
            _LOGGER.info(f"Container {container_name} stopped successfully")
            return True
        except Exception as e:
            _LOGGER.error(f"Error stopping container {container_name}: {e}")
            return False

    async def get_vms(self) -> List[Dict[str, Any]]:
        try:
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.error(f"VM list command failed with exit status {result.exit_status}")
                return []
            
            vms = []
            for line in result.stdout.splitlines():
                if line.strip():
                    name = line.strip()
                    status = await self._get_vm_status(name)
                    vms.append({"name": name, "status": status})
            return vms
        except Exception as e:
            _LOGGER.error(f"Error getting VMs: {e}")
            return []

    async def get_user_scripts(self) -> List[Dict[str, Any]]:
        try:
            result = await self.execute_command("ls -1 /boot/config/plugins/user.scripts/scripts")
            if result.exit_status != 0:
                _LOGGER.error(f"User scripts list command failed with exit status {result.exit_status}")
                return []
            return [{"name": script.strip()} for script in result.stdout.splitlines()]
        except Exception as e:
            _LOGGER.error(f"Error getting user scripts: {e}")
            return []

    async def execute_user_script(self, script_name: str, background: bool = False) -> str:
        try:
            command = f"/usr/local/emhttp/plugins/user.scripts/scripts/{script_name}"
            if background:
                command += " & > /dev/null 2>&1"
            result = await self.execute_command(command)
            if result.exit_status != 0:
                _LOGGER.error(f"User script {script_name} failed with exit status {result.exit_status}")
                return ""
            return result.stdout
        except Exception as e:
            _LOGGER.error(f"Error executing user script {script_name}: {e}")
            return ""

    async def stop_user_script(self, script_name: str) -> str:
        try:
            result = await self.execute_command(f"pkill -f '{script_name}'")
            if result.exit_status != 0:
                _LOGGER.error(f"Stopping user script {script_name} failed with exit status {result.exit_status}")
                return ""
            return result.stdout
        except Exception as e:
            _LOGGER.error(f"Error stopping user script {script_name}: {e}")
            return ""

    async def get_vms(self) -> List[Dict[str, Any]]:
        try:
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.error(f"VM list command failed with exit status {result.exit_status}")
                return []
            
            vms = []
            for line in result.stdout.splitlines():
                if line.strip():
                    name = line.strip()
                    status = await self._get_vm_status(name)
                    vms.append({"name": name, "status": status})
            return vms
        except Exception as e:
            _LOGGER.error(f"Error getting VMs: {e}")
            return []

    async def _get_vm_status(self, vm_name: str) -> str:
        try:
            result = await self.execute_command(f"virsh domstate {vm_name}")
            if result.exit_status != 0:
                _LOGGER.error(f"VM status command for {vm_name} failed with exit status {result.exit_status}")
                return "unknown"
            return result.stdout.strip()
        except Exception as e:
            _LOGGER.error(f"Error getting VM status for {vm_name}: {e}")
            return "unknown"

    async def start_vm(self, vm_name: str) -> bool:
        try:
            result = await self.execute_command(f"virsh start {vm_name}")
            return result.exit_status == 0 and "started" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error(f"Error starting VM {vm_name}: {e}")
            return False

    async def stop_vm(self, vm_name: str) -> bool:
        try:
            result = await self.execute_command(f"virsh shutdown {vm_name}")
            return result.exit_status == 0 and "shutting down" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error(f"Error stopping VM {vm_name}: {e}")
            return False

    async def pause_vm(self, vm_name: str) -> bool:
        try:
            result = await self.execute_command(f"virsh suspend {vm_name}")
            return result.exit_status == 0 and "suspended" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error(f"Error pausing VM {vm_name}: {e}")
            return False

    async def resume_vm(self, vm_name: str) -> bool:
        try:
            result = await self.execute_command(f"virsh resume {vm_name}")
            return result.exit_status == 0 and "resumed" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error(f"Error resuming VM {vm_name}: {e}")
            return False

    async def reboot_vm(self, vm_name: str) -> bool:
        try:
            result = await self.execute_command(f"virsh reboot {vm_name}")
            return result.exit_status == 0 and "rebooted" in result.stdout.lower()
        except Exception as e:
            _LOGGER.error(f"Error rebooting VM {vm_name}: {e}")
            return False