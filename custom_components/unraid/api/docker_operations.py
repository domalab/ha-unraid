"""Docker operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, List, Any
from enum import Enum

import asyncio
import asyncssh # type: ignore

_LOGGER = logging.getLogger(__name__)

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

class DockerOperationsMixin:
    """Mixin for Docker-related operations."""

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Fetch information about Docker containers."""
        try:
            _LOGGER.debug("Fetching Docker container information")
            # Check if Docker service is running using Unraid's rc script
            service_check = await self.execute_command("/etc/rc.d/rc.docker status")
            if service_check.exit_status != 0 or "is currently running" not in service_check.stdout:
                _LOGGER.debug("Docker service is not running, no containers available")
                return []

            # Get basic container info with proven format
            result = await self.execute_command("docker ps -a --format '{{.Names}}|{{.State}}|{{.ID}}|{{.Image}}'")
            if result.exit_status != 0:
                _LOGGER.debug("No Docker containers found or docker command not available")
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

            return containers
        except (asyncssh.Error, OSError) as e:
            _LOGGER.debug("Error getting docker containers (this is normal if Docker is not configured): %s", str(e))
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
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
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
        except (asyncssh.Error, asyncio.TimeoutError, OSError) as e:
            _LOGGER.error("Error stopping container %s: %s", container_name, str(e))
            return False
            
    async def get_docker_proxy_url(self) -> str:
        """Get the URL for connecting to Docker socket proxy."""
        try:
            # Get IP address
            result = await self.execute_command(
                "ip -4 addr show | grep inet | grep -v '127.0.0.1' | awk '{print $2}' | cut -d'/' -f1"
            )

            if result.exit_status != 0:
                raise ValueError("Failed to get Unraid IP address")

            # Get first non-localhost IP
            ip_addresses = result.stdout.strip().split('\n')
            server_ip = next(
                (ip.strip() for ip in ip_addresses if ip and not ip.startswith('127.')),
                None
            )

            if not server_ip:
                raise ValueError("No valid IP address found")

            # Check if dockersocket proxy is running
            result = await self.execute_command(
                "docker ps --format '{{.Names}}' | grep -E 'dockersocket|dockerproxy'"
            )

            if result.exit_status != 0 or not result.stdout.strip():
                raise ValueError(
                    "Docker socket proxy not found. Please ensure 'dockersocket' or "
                    "'dockerproxy' container is running on your Unraid server"
                )

            # Verify proxy is accessible
            proxy_port = 2375  # Default proxy port
            proxy_url = f"http://{server_ip}:{proxy_port}"

            test_cmd = f"curl -s {proxy_url}/version"
            result = await self.execute_command(test_cmd)

            if result.exit_status != 0:
                raise ValueError(f"Docker proxy not accessible on {proxy_url}")

            _LOGGER.debug("Using Docker proxy URL: %s", proxy_url)
            return proxy_url

        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as err:
            _LOGGER.error("Error getting Docker proxy URL: %s", err)
            raise

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
        except (asyncssh.Error, OSError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.error("Error getting Docker vDisk usage: %s", str(err))
            return {}