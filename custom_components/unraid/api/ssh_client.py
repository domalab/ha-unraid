"""Compatibility layer for the old UnraidSSHClient class."""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict, List, Optional, Union

import asyncssh

from .connection_manager import SSHConnection

_LOGGER = logging.getLogger(__name__)

class UnraidSSHClient:
    """Legacy SSH client for Unraid servers - compatibility layer."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22
    ) -> None:
        """Initialize the SSH client."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self._connection: Optional[asyncssh.SSHClientConnection] = None
        self._connected = False
        
        # Create an SSHConnection instance for actual operations
        self._ssh_connection = SSHConnection(host, username, password, port)

    async def connect(self) -> bool:
        """Connect to the Unraid server."""
        try:
            await self._ssh_connection.connect()
            self._connected = True
            self._connection = self._ssh_connection.conn
            return True
        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        await self._ssh_connection.disconnect()
        self._connected = False
        self._connection = None

    def is_connected(self) -> bool:
        """Check if connected to the Unraid server."""
        return self._connected and self._ssh_connection.state.name == "ACTIVE"

    async def run_command(self, command: str) -> asyncssh.SSHCompletedProcess:
        """Run a command on the Unraid server."""
        if not self.is_connected():
            raise RuntimeError("Not connected to the Unraid server")
        
        return await self._ssh_connection.execute_command(command)

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics from the Unraid server."""
        if not self.is_connected():
            await self.connect()
            
        # CPU info
        cpu_info_cmd = "cat /proc/stat | grep '^cpu '"
        cpu_result = await self.run_command(cpu_info_cmd)
        cpu_parts = cpu_result.stdout.strip().split()
        cpu_total = sum(int(x) for x in cpu_parts[1:])
        cpu_idle = int(cpu_parts[4])
        cpu_usage = 100 - (cpu_idle * 100 / cpu_total)
        
        # Memory info
        mem_info_cmd = "cat /proc/meminfo"
        mem_result = await self.run_command(mem_info_cmd)
        mem_lines = mem_result.stdout.strip().split('\n')
        mem_total = int(mem_lines[0].split()[1])
        mem_free = int(mem_lines[1].split()[1])
        mem_available = int(mem_lines[2].split()[1])
        mem_used = mem_total - mem_available
        mem_percentage = (mem_used / mem_total) * 100
        
        # Uptime
        uptime_cmd = "uptime"
        uptime_result = await self.run_command(uptime_cmd)
        uptime_parts = uptime_result.stdout.strip().split(',')
        uptime_str = uptime_parts[0].split('up ')[1].strip()
        
        # Kernel version
        kernel_cmd = "uname -r"
        kernel_result = await self.run_command(kernel_cmd)
        kernel_version = kernel_result.stdout.strip()
        
        # Unraid version
        unraid_cmd = "cat /etc/unraid-version"
        unraid_result = await self.run_command(unraid_cmd)
        unraid_version = unraid_result.stdout.strip()
        
        # CPU temperature
        temp_cmd = "sensors"
        temp_result = await self.run_command(temp_cmd)
        temp_lines = temp_result.stdout.strip().split('\n')
        cpu_temp = None
        for line in temp_lines:
            if "Package id 0" in line:
                temp_parts = line.split('+')
                if len(temp_parts) > 1:
                    temp_str = temp_parts[1].split('°')[0]
                    cpu_temp = float(temp_str)
                    break
        
        # Get actual CPU information dynamically
        cpu_model = "Unknown CPU"
        cpu_cores = 1  # Default fallback

        try:
            # Get CPU model from /proc/cpuinfo
            cpu_info_cmd = "grep 'model name' /proc/cpuinfo | head -1 | cut -d':' -f2 | sed 's/^ *//'"
            cpu_info_result = await self.run_command(cpu_info_cmd)
            if cpu_info_result.exit_code == 0 and cpu_info_result.stdout.strip():
                cpu_model = cpu_info_result.stdout.strip()

            # Get actual CPU core count
            core_count_cmd = "nproc"
            core_result = await self.run_command(core_count_cmd)
            if core_result.exit_code == 0 and core_result.stdout.strip():
                cpu_cores = int(core_result.stdout.strip())
        except (ValueError, AttributeError) as err:
            _LOGGER.debug("Error getting CPU info: %s", err)

        return {
            "cpu_model": cpu_model,
            "cpu_cores": cpu_cores,
            "cpu_usage": cpu_usage,
            "memory_total": mem_total,
            "memory_free": mem_free,
            "memory_used": mem_used,
            "memory_usage_percentage": mem_percentage,
            "uptime": uptime_str,
            "kernel_version": kernel_version,
            "unraid_version": unraid_version,
            "cpu_temp": cpu_temp,
        }

    async def get_disk_info(self) -> List[Dict[str, Any]]:
        """Get disk information from the Unraid server."""
        if not self.is_connected():
            await self.connect()
            
        # Get disk usage
        df_cmd = "df -h"
        df_result = await self.run_command(df_cmd)
        df_lines = df_result.stdout.strip().split('\n')[1:]  # Skip header
        
        disks = []
        for line in df_lines:
            parts = line.split()
            if len(parts) >= 6:
                device = parts[0]
                size = parts[1]
                used = parts[2]
                available = parts[3]
                use_percentage = parts[4]
                mounted_on = parts[5]
                
                # Get disk temperature
                temp = None
                if device.startswith('/dev/'):
                    disk_name = device.split('/')[-1]
                    temp_cmd = f"smartctl -a {device}"
                    try:
                        temp_result = await self.run_command(temp_cmd)
                        temp_lines = temp_result.stdout.strip().split('\n')
                        for temp_line in temp_lines:
                            if "Temperature_Celsius" in temp_line:
                                temp_parts = temp_line.split()
                                temp = float(temp_parts[-2])
                                break
                    except Exception:
                        # Ignore errors for temperature retrieval
                        pass
                
                disks.append({
                    "device": device,
                    "size": size,
                    "used": used,
                    "available": available,
                    "use_percentage": use_percentage,
                    "mounted_on": mounted_on,
                    "temp": temp,
                })
        
        return disks

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Get Docker container information from the Unraid server."""
        if not self.is_connected():
            await self.connect()
            
        # Get Docker containers
        docker_cmd = "docker ps --format '{{.ID}}|{{.Image}}|{{.Status}}|{{.Names}}'"
        docker_result = await self.run_command(docker_cmd)
        docker_lines = docker_result.stdout.strip().split('\n')
        
        containers = []
        for line in docker_lines:
            if not line.strip():
                continue
                
            parts = line.split('|')
            if len(parts) >= 4:
                container_id = parts[0]
                image = parts[1]
                status = parts[2]
                name = parts[3]
                
                # Determine state from status
                state = "unknown"
                if "running" in status.lower():
                    state = "running"
                elif "exited" in status.lower():
                    state = "stopped"
                
                containers.append({
                    "container_id": container_id,
                    "name": name,
                    "image": image,
                    "status": status,
                    "state": state,
                })
        
        return containers

    async def get_vms(self) -> List[Dict[str, Any]]:
        """Get VM information from the Unraid server."""
        if not self.is_connected():
            await self.connect()
            
        # Get VMs
        vm_cmd = "virsh list --all"
        vm_result = await self.run_command(vm_cmd)
        vm_lines = vm_result.stdout.strip().split('\n')[2:]  # Skip header
        
        vms = []
        for line in vm_lines:
            parts = line.strip().split()
            if len(parts) >= 3:
                vm_id = parts[0]
                name = parts[1]
                state = ' '.join(parts[2:])
                
                vms.append({
                    "id": vm_id,
                    "name": name,
                    "state": state,
                })
        
        return vms
