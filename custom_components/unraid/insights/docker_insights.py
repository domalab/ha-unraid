"""Docker insights module for monitoring Docker containers using API.

This module provides comprehensive container monitoring through a single sensor
per container, including state, resource usage, and network statistics.
"""
from __future__ import annotations

import logging
import aiodocker # type: ignore
import asyncio
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Callable, TYPE_CHECKING, Type
from contextlib import suppress

from ..unraid import UnraidAPI

if TYPE_CHECKING:
    from . import UnraidDockerInsights

_LOGGER = logging.getLogger(__name__)

@dataclass
class DockerContainerStats:
    """Docker container statistics."""
    state: str
    status: str
    health: str
    image: str
    version: str
    
    cpu_percentage: float
    cpu_1core_percentage: float
    memory_usage: float  # MB
    memory_limit: float  # MB
    memory_percentage: float
    
    network_speed_up: float  # KB/s
    network_speed_down: float  # KB/s
    network_total_up: float  # MB
    network_total_down: float  # MB
    
    uptime: Optional[datetime]
    created: Optional[datetime]
    last_updated: datetime

class DockerSessionManager:
    """Manages Docker client sessions with automatic cleanup and reconnection."""
    
    def __init__(
        self,
        connection_factory: Callable[[], aiodocker.Docker],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session_timeout: int = 3600
    ) -> None:
        """Initialize the session manager."""
        self._connection_factory = connection_factory
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._session_timeout = timedelta(seconds=session_timeout)
        
        self._client: Optional[aiodocker.Docker] = None
        self._last_used: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def get_client(self) -> aiodocker.Docker:
        """Get a Docker client, creating a new one if necessary."""
        async with self._lock:
            if self._should_refresh():
                await self._refresh_client()
            self._last_used = datetime.now()
            return self._client

    def _should_refresh(self) -> bool:
        """Check if the client session should be refreshed."""
        if self._client is None or self._closed:
            return True
            
        if self._last_used is None:
            return True
            
        age = datetime.now() - self._last_used
        return age > self._session_timeout

    async def _refresh_client(self) -> None:
        """Refresh the Docker client connection."""
        if self._client:
            await self._cleanup_client(self._client)
            
        for attempt in range(self._max_retries):
            try:
                self._client = self._connection_factory()
                # Test connection
                await self._client.containers.list()
                self._closed = False
                _LOGGER.debug("Successfully established new Docker connection")
                return
            except Exception as err:
                _LOGGER.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    err
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay)
                    
        raise ConnectionError("Failed to establish Docker connection")

    async def _cleanup_client(self, client: aiodocker.Docker) -> None:
        """Clean up a Docker client instance."""
        try:
            # Close client first
            if hasattr(client, 'close'):
                await client.close()
            
            # Ensure the Docker client's session is closed
            if hasattr(client, 'docker') and hasattr(client.docker, 'session'):
                await client.docker.session.close()
            
            # Close connector
            if hasattr(client, 'connector') and client.connector:
                await client.connector.close()
                
            # Close session explicitly
            if hasattr(client, 'session') and client.session:
                await client.session.close()
            
            # Force cleanup of any remaining sessions
            for attr in dir(client):
                if 'session' in attr.lower():
                    session = getattr(client, attr)
                    if session and hasattr(session, 'close'):
                        await session.close()
                
        except Exception as err:
            _LOGGER.debug("Error during Docker client cleanup: %s", err)
        finally:
            # Clear references
            self._client = None

    async def close(self) -> None:
        """Close the session manager and cleanup resources."""
        self._closed = True
        if self._client:
            await self._cleanup_client(self._client)
            self._client = None

    async def __aenter__(self) -> DockerSessionManager:
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        try:
            await self.close()
        except Exception as err:
            _LOGGER.error("Error during context exit cleanup: %s", err)

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return bool(self._client and not self._closed)

    async def execute_with_retry(
        self,
        operation: Callable[[aiodocker.Docker], Any]
    ) -> Any:
        """Execute an operation with automatic retry on failure."""
        for attempt in range(self._max_retries):
            try:
                client = await self.get_client()
                return await operation(client)
            except Exception as err:
                _LOGGER.error(
                    "Operation failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries,
                    err
                )
                if attempt < self._max_retries - 1:
                    await self._refresh_client()
                    await asyncio.sleep(self._retry_delay)
                else:
                    raise

class UnraidDockerInsights:
    """Class to monitor Docker containers on Unraid using HTTP API."""

    def __init__(self, api: "UnraidAPI") -> None:
        """Initialize Docker insights."""
        self._api = api
        self._prev_stats: dict[str, dict] = {}
        self._prev_network: dict[str, dict] = {}
        self._prev_time: dict[str, datetime] = {}
        self._docker_proxy_port = 2375
        self._closed = False
        self._proxy_url: Optional[str] = None
        self._monitor_ready = asyncio.Event()

        # Initialize session manager
        self._session_manager: Optional[DockerSessionManager] = None

    def _create_proxy_client(self) -> aiodocker.Docker:  
        """Create a Docker client using proxy."""
        if not self._proxy_url:
            raise RuntimeError("Proxy URL not initialized")
        return aiodocker.Docker(url=self._proxy_url)

    async def _detect_and_connect(self) -> None:
        """Detect and establish Docker connection through proxy."""
        try:
            # First verify proxy is available
            if not await self._verify_docker_proxy():
                raise ConnectionError("Docker socket proxy not found or not accessible")
            
            self._proxy_url = await self._get_docker_proxy_url()
            self._session_manager = DockerSessionManager(
                connection_factory=self._create_proxy_client,
                max_retries=3,
                retry_delay=1.0,
                session_timeout=3600
            )
            
            # Test connection
            await self._session_manager.get_client()
            _LOGGER.info("Successfully established Docker connection via proxy")

        except Exception as err:
            self._session_manager = None
            raise ConnectionError(
                "Could not establish Docker connection. Make sure Docker socket "
                "proxy container is running"
            ) from err

    async def connect(self) -> None:
        """Connect to Docker daemon."""
        if not self._session_manager and not self._closed:
            try:
                await self._detect_and_connect()
            except Exception as err:
                _LOGGER.error("Failed to establish Docker connection: %s", err)
                await self.close()
                raise

    async def close(self) -> None:
        """Close the Docker connection and cleanup resources."""
        self._closed = True
        await self.cleanup()

    async def cleanup(self) -> None:
        """Clean up all resources."""
        try:
            if self._session_manager:
                await self._session_manager.close()
                self._session_manager = None

            # Force cleanup any remaining sessions
            tasks = [
                task for task in asyncio.all_tasks()
                if 'aiodocker' in str(task) and not task.done()
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as err:
            _LOGGER.error("Error during Docker insights cleanup: %s", err)
        finally:
            self._session_manager = None

    @property
    def is_connected(self) -> bool:
        """Check if Docker client is connected."""
        return bool(self._session_manager and self._session_manager.is_connected())

    async def __aenter__(self) -> 'UnraidDockerInsights':
        """Enter async context."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        await self.close()

    async def _verify_docker_proxy(self) -> bool:
        """Verify if dockersocket proxy is running."""
        try:
            result = await self._api.execute_command(
                "docker ps --format '{{.Names}}' | grep -E 'dockersocket|dockerproxy'"
            )
            if result.exit_status == 0 and ('dockersocket' in result.stdout or 'dockerproxy' in result.stdout):
                _LOGGER.debug("Found running Docker socket proxy container")
                return True
                
            _LOGGER.error(
                "Docker socket proxy container not found. Please ensure 'dockersocket' container "
                "is running on your Unraid server. See documentation for setup instructions."
            )
            return False
            
        except Exception as err:
            _LOGGER.error("Error checking for Docker socket proxy: %s", err)
            return False

    async def _get_docker_proxy_url(self) -> str:
        """Get the URL for connecting to Docker socket proxy."""
        try:
            # Verify proxy is running
            if not await self._verify_docker_proxy():
                raise Exception("Docker socket proxy not found")

            # Get IP address
            result = await self._api.execute_command(
                "ip -4 addr show | grep inet | grep -v '127.0.0.1' | awk '{print $2}' | cut -d'/' -f1"
            )
            
            if result.exit_status != 0:
                raise Exception("Failed to get Unraid IP address")

            # Get first non-localhost IP
            ip_addresses = result.stdout.strip().split('\n')
            server_ip = next(
                (ip.strip() for ip in ip_addresses if ip and not ip.startswith('127.')),
                None
            )
                    
            if not server_ip:
                raise Exception("No valid IP address found")

            # Verify proxy is accessible
            test_cmd = f"curl -s http://{server_ip}:{self._docker_proxy_port}/version"
            result = await self._api.execute_command(test_cmd)
            
            if result.exit_status != 0:
                raise Exception(f"Docker proxy not accessible on {server_ip}:{self._docker_proxy_port}")

            proxy_url = f"http://{server_ip}:{self._docker_proxy_port}"
            _LOGGER.debug("Using Docker proxy URL: %s", proxy_url)
            
            return proxy_url

        except Exception as err:
            _LOGGER.error("Error setting up Docker proxy connection: %s", err)
            raise

    async def get_container_stats(self) -> Dict[str, Any]:
        """Get Docker container statistics."""
        # Check if monitor is ready
        if not self._monitor_ready.is_set():
            _LOGGER.debug("Docker monitor not yet ready, skipping stats collection")
            return {"containers": {}, "summary": {}}

        if not self._session_manager:
            await self.connect()
            
        async def _get_stats(docker: aiodocker.Docker):
            try:
                containers_stats = {}
                summary = {
                    "containers_running": 0,
                    "containers_paused": 0,
                    "containers_stopped": 0,
                    "total_containers": 0,
                    "total_cpu_percentage": 0.0,
                    "total_memory_percentage": 0.0
                }

                containers = await docker.containers.list(all=True)
                for container in containers:
                    try:
                        # Get container details
                        info = await container.show()
                        stats = await container.stats(stream=False)
                        
                        state = info["State"]
                        config = info["Config"]
                        container_name = info["Name"].lstrip("/")
                        
                        # Create allinone stats dictionary
                        container_stats = {
                            "state": state["Status"],
                            "status": self._get_status_string(state),
                            "health": state.get("Health", {}).get("Status", "none"),
                            "image": config["Image"],
                            "version": config["Image"].split(":")[-1] if ":" in config["Image"] else "latest"
                        }

                        # Add runtime stats if container is running
                        if state["Status"] == "running" and stats:
                            stats_obj = stats[0]
                            
                            # CPU stats
                            cpu_stats = stats_obj["cpu_stats"]
                            precpu_stats = stats_obj["precpu_stats"]
                            
                            cpu_delta = float(cpu_stats["cpu_usage"]["total_usage"] - 
                                        precpu_stats["cpu_usage"]["total_usage"])
                            system_delta = float(cpu_stats["system_cpu_usage"] - 
                                            precpu_stats["system_cpu_usage"])
                            num_cpus = len(cpu_stats["cpu_usage"].get("percpu_usage", [])) or 1
                            
                            if system_delta > 0:
                                container_stats["cpu_percentage"] = round((cpu_delta / system_delta) * 100.0 * num_cpus, 2)
                                container_stats["cpu_1core_percentage"] = round(container_stats["cpu_percentage"] / num_cpus, 2)

                            # Memory stats
                            mem_stats = stats_obj["memory_stats"]
                            memory_limit = mem_stats["limit"] / (1024 * 1024)  # Convert to MB
                            
                            used_memory = mem_stats["usage"]
                            if "total_inactive_file" in mem_stats.get("stats", {}):
                                used_memory -= mem_stats["stats"]["total_inactive_file"]
                            elif "cache" in mem_stats.get("stats", {}):
                                used_memory -= mem_stats["stats"]["cache"]
                            
                            memory_usage = used_memory / (1024 * 1024)  # Convert to MB
                            container_stats["memory_usage"] = round(memory_usage, 2)
                            container_stats["memory_limit"] = round(memory_limit, 2)
                            container_stats["memory_percentage"] = round((memory_usage / memory_limit) * 100.0, 2)

                            # Network stats if available
                            if "networks" in stats_obj:
                                net_stats = stats_obj["networks"]
                                total_rx = 0
                                total_tx = 0
                                
                                for interface in net_stats.values():
                                    total_rx += interface["rx_bytes"]
                                    total_tx += interface["tx_bytes"]

                                # Calculate rates
                                if container_name in self._prev_stats:
                                    time_delta = (datetime.now(timezone.utc) - 
                                                self._prev_time[container_name]).total_seconds()
                                    prev_stats = self._prev_stats[container_name]
                                    
                                    if time_delta > 0:
                                        rx_delta = total_rx - prev_stats["rx_bytes"]
                                        tx_delta = total_tx - prev_stats["tx_bytes"]
                                        
                                        container_stats["network_speed_down"] = round((rx_delta / 1024) / time_delta, 2)  # KB/s
                                        container_stats["network_speed_up"] = round((tx_delta / 1024) / time_delta, 2)  # KB/s
                                
                                self._prev_stats[container_name] = {
                                    "rx_bytes": total_rx,
                                    "tx_bytes": total_tx
                                }
                                self._prev_time[container_name] = datetime.now(timezone.utc)
                                
                                container_stats["network_total_down"] = round(total_rx / (1024 * 1024), 2)  # MB
                                container_stats["network_total_up"] = round(total_tx / (1024 * 1024), 2)  # MB

                            # Update summary counters
                            if state["Status"] == "running":
                                summary["containers_running"] += 1
                                summary["total_cpu_percentage"] += container_stats.get("cpu_percentage", 0)
                                summary["total_memory_percentage"] += container_stats.get("memory_percentage", 0)
                            elif state["Status"] == "paused":
                                summary["containers_paused"] += 1
                            else:
                                summary["containers_stopped"] += 1

                            # Add the stats to main dictionary
                            containers_stats[container_name] = container_stats
                            
                    except Exception as err:
                        _LOGGER.error("Error processing container stats: %s", err)
                        continue

                # Update summary
                summary["total_containers"] = len(containers_stats)
                summary["total_cpu_percentage"] = round(summary["total_cpu_percentage"], 2)
                summary["total_memory_percentage"] = round(summary["total_memory_percentage"], 2)

                return {
                    "containers": containers_stats,
                    "summary": summary
                }

            except Exception as err:
                _LOGGER.error("Error getting container stats: %s", err)
                return {"containers": {}, "summary": {}}

        return await self._session_manager.execute_with_retry(_get_stats)

    def _get_status_string(self, state: dict) -> str:
        """Generate status string in Docker format."""
        status = state.get("Status", "unknown")
        
        if status == "running":
            if state.get("StartedAt"):
                started = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
                duration = datetime.now(timezone.utc) - started
                days = duration.days
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                
                if days > 0:
                    return f"Up {days} days"
                elif hours > 0:
                    return f"Up {hours} hours"
                else:
                    return f"Up {minutes} minutes"
            return "Up"
            
        elif status == "exited":
            exit_code = state.get("ExitCode", 0)
            finished = datetime.fromisoformat(state["FinishedAt"].replace("Z", "+00:00"))
            duration = datetime.now(timezone.utc) - finished
            
            days = duration.days
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            if days > 0:
                return f"Exited ({exit_code}) {days} days ago"
            elif hours > 0:
                return f"Exited ({exit_code}) {hours} hours ago"
            else:
                return f"Exited ({exit_code}) {minutes} minutes ago"
                
        return status.capitalize()
