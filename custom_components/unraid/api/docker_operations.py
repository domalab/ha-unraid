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

    async def check_docker_running(self) -> bool:
        """Check if Docker is running using multiple methods.

        Returns:
            bool: True if Docker service is running, False otherwise.
        """
        try:
            # Method 1: Traditional rc.d script check
            service_check = await self.execute_command("/etc/rc.d/rc.docker status")
            if service_check.exit_status == 0 and "is currently running" in service_check.stdout:
                _LOGGER.debug("Docker validated through rc.d script")
                return True

            # Method 2: Process check
            process_check = await self.execute_command("pgrep -f dockerd")
            if process_check.exit_status == 0:
                # Method 3: Socket file check
                sock_check = await self.execute_command("[ -S /var/run/docker.sock ]")
                if sock_check.exit_status == 0:
                    _LOGGER.debug("Docker validated through process and socket checks")
                    return True

            _LOGGER.debug(
                "Docker service checks failed - rc.d: %s, process: %s",
                service_check.exit_status,
                process_check.exit_status
            )
            return False
        except Exception as err:
            _LOGGER.debug("Error checking Docker status: %s", str(err))
            return False

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Fetch information about Docker containers using batched commands."""
        try:
            _LOGGER.debug("Fetching Docker container information")

            # Use new service check method
            if not await self.check_docker_running():
                _LOGGER.debug("Docker service is not running, no containers available")
                return []

            # Get container list with basic information in a single command
            # Note: Removed RunningFor, CPU, Memory, Network I/O, and Block I/O metrics as per optimization requirements
            result = await self.execute_command(
                "docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'"
            )

            if result.exit_status != 0:
                _LOGGER.error("Failed to get container list: %s", result.stderr)
                return []

            # Parse container list
            containers = []
            running_containers = []

            for line in result.stdout.splitlines():
                try:
                    parts = line.split('|')
                    if len(parts) != 4:  # Updated to match the new format (4 fields instead of 5)
                        continue

                    container_id, name, status, image = parts

                    # Determine container state
                    state = "unknown"
                    if status.startswith("Up"):
                        state = "running"
                        running_containers.append(container_id)
                    elif status.startswith("Exited"):
                        state = "exited"
                    elif status.startswith("Created"):
                        state = "created"
                    elif status.startswith("Restarting"):
                        state = "restarting"

                    # Store basic container info
                    # Note: Removed running_for, CPU, memory, network I/O, and block I/O metrics as per optimization requirements
                    container_info = {
                        "id": container_id,
                        "name": name,
                        "state": state,
                        "status": status,
                        "image": image
                    }

                    # Get container icon if available
                    icon_path = f"/var/lib/docker/unraid/images/{name}-icon.png"
                    icon_result = await self.execute_command(
                        f"[ -f {icon_path} ] && (base64 {icon_path}) || echo ''"
                    )
                    icon_data = icon_result.stdout[0] if icon_result.exit_status == 0 else ""
                    container_info["icon"] = icon_data

                    containers.append(container_info)
                except Exception as err:
                    _LOGGER.warning("Error parsing container line '%s': %s", line, err)

            return containers
        except (asyncssh.Error, OSError) as e:
            _LOGGER.debug("Error getting docker containers (this is normal if Docker is not configured): %s", str(e))
            return []

    async def execute_container_command(self, command: str, timeout: int = 30) -> asyncssh.SSHCompletedProcess:
        """Execute Docker container command with timeout."""
        try:
            async with asyncio.timeout(timeout):
                result = await self.execute_command(command)
                return result
        except asyncio.TimeoutError:
            _LOGGER.error("Docker command timed out")
            raise

    async def start_container(self, container_name: str) -> bool:
        """Start a Docker container."""
        try:
            _LOGGER.debug("Starting container: %s", container_name)
            result = await self.execute_container_command(f'docker start "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to start container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s started successfully", container_name)
            return True
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.error("Error starting container %s: %s", container_name, str(e))
            return False

    async def stop_container(self, container_name: str) -> bool:
        """Stop a Docker container."""
        try:
            _LOGGER.debug("Stopping container: %s", container_name)
            result = await self.execute_container_command(f'docker stop "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to stop container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s stopped successfully", container_name)
            return True
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.error("Error stopping container %s: %s", container_name, str(e))
            return False

    async def pause_container(self, container_name: str) -> bool:
        """Pause a Docker container."""
        try:
            _LOGGER.debug("Pausing container: %s", container_name)
            result = await self.execute_container_command(f'docker pause "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to pause container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s paused successfully", container_name)
            return True
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.error("Error pausing container %s: %s", container_name, str(e))
            return False

    async def resume_container(self, container_name: str) -> bool:
        """Resume a paused Docker container."""
        try:
            _LOGGER.debug("Resuming container: %s", container_name)
            result = await self.execute_container_command(f'docker unpause "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to resume container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s resumed successfully", container_name)
            return True
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.error("Error resuming container %s: %s", container_name, str(e))
            return False

    async def restart_container(self, container_name: str) -> bool:
        """Restart a Docker container."""
        try:
            _LOGGER.debug("Restarting container: %s", container_name)
            result = await self.execute_container_command(f'docker restart "{container_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to restart container %s: %s", container_name, result.stderr)
                return False
            _LOGGER.info("Container %s restarted successfully", container_name)
            return True
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.error("Error restarting container %s: %s", container_name, str(e))
            return False

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
