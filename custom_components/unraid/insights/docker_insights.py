"""Docker insights module for monitoring Docker containers using API.

This module provides comprehensive container monitoring through a single sensor
per container, including state, resource usage, and network statistics.
"""
from __future__ import annotations

import logging
import aiodocker # type: ignore
import asyncio
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, TYPE_CHECKING

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
        self._session = None  # Track the aiohttp session

    async def get_client(self) -> aiodocker.Docker:
        """Get a Docker client with improved session management."""
        async with self._lock:
            if self._should_refresh():
                await self._refresh_client()
                
            if not self._client:
                raise RuntimeError("Failed to establish Docker connection")
                
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
        """Refresh the Docker client connection with better error handling."""
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
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                    
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
        async with self._lock:
            self._closed = True
            if self._client:
                try:
                    # Close Docker client first
                    await self._client.close()
                    
                    # Close underlying session if it exists
                    if hasattr(self._client, 'session') and self._client.session:
                        await self._client.session.close()
                        self._client.session = None
                except Exception as err:
                    _LOGGER.debug("Error closing Docker client: %s", err)
                finally:
                    self._client = None
                    self._session = None

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
        self._disabled = False
        self._busy = False
        self._proxy_url: Optional[str] = None
        self._monitor_ready = asyncio.Event()
        self._connection_lock = asyncio.Lock()
        self._last_connection_attempt = time.time()
        self._connection_retry_delay = 30  # seconds
        self._connection_errors = 0 # Track connection errors
        self._stats_retry_count = 0
        self._max_stats_retries = 5

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
            
            # Ensure any existing session is properly closed
            if self._session_manager:
                await self._session_manager.close()
                
            self._session_manager = DockerSessionManager(
                connection_factory=self._create_proxy_client,
                max_retries=3,
                retry_delay=1.0,
                session_timeout=3600
            )
            
            # Test connection
            client = await self._session_manager.get_client()
            await client.containers.list()
            _LOGGER.info("Successfully established Docker connection via proxy")

        except Exception as err:
            if self._session_manager:
                await self._session_manager.close()
            self._session_manager = None
            raise ConnectionError(
                "Could not establish Docker connection. Make sure Docker socket "
                "proxy container is running"
            ) from err

    async def connect(self) -> None:
        """Connect to Docker daemon with improved error handling."""
        if self._closed:
            raise RuntimeError("Cannot connect - instance is closed")
                
        if self.is_connected:
            return

        try:
            await self._detect_and_connect()
            self._monitor_ready.set()
            self._closed = False
            self._connection_errors = 0
        except Exception as err:
            self._connection_errors += 1
            self._monitor_ready.clear()
            await self.cleanup()
            
            delay = min(self._connection_retry_delay * (2 ** self._connection_errors), 300)
            _LOGGER.error(
                "Failed to connect to Docker (%s). Will retry in %d seconds",
                err,
                delay
            )
            
            raise ConnectionError(f"Failed to establish Docker connection: {err}") from err

    async def ensure_connected(self) -> bool:
        """Ensure we have a valid connection with proper error handling."""
        if self._disabled:
            return False

        async with self._connection_lock:
            try:
                if not self.is_connected:
                    current_time = time.time()
                    if current_time - self._last_connection_attempt > self._connection_retry_delay:
                        self._busy = True
                        try:
                            await self.connect()
                            self._last_connection_attempt = current_time
                            self._connection_errors = 0
                            return True
                        except Exception as err:
                            _LOGGER.error("Failed to reconnect to Docker: %s", err)
                            return False
                        finally:
                            self._busy = False
                return self.is_connected
            except Exception as err:
                _LOGGER.error("Error in ensure_connected: %s", err)
                return False

    async def close(self) -> None:
        """Close the Docker connection and cleanup resources."""
        self._closed = True
        await self.cleanup()

    async def disable(self) -> None:
        """Disable Docker insights and cleanup resources properly."""
        self._disabled = True
        self._busy = True
        try:
            # First close any open sessions
            if self._session_manager:
                try:
                    await self._session_manager.close()
                except Exception as err:
                    _LOGGER.debug("Error closing session manager: %s", err)
                finally:
                    self._session_manager = None

            # Clear stats
            self._prev_stats.clear()
            self._prev_time.clear()
            self._prev_network.clear()

            # Cancel any pending tasks
            tasks = [
                task for task in asyncio.all_tasks()
                if 'aiodocker' in str(task) and not task.done()
            ]
            for task in tasks:
                task.cancel()
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as err:
            _LOGGER.error("Error during Docker insights cleanup: %s", err)
        finally:
            self._session_manager = None
            self._monitor_ready.clear()
            self._closed = True
            self._busy = False

    async def cleanup(self) -> None:
        """Enhanced cleanup with session handling."""
        async with self._connection_lock:
            try:
                if self._session_manager:
                    try:
                        await self._session_manager.close()
                    except Exception as err:
                        _LOGGER.debug("Error closing session manager: %s", err)
                    finally:
                        self._session_manager = None

                # Clear stats
                self._prev_stats.clear()
                self._prev_time.clear()

                # Cancel any pending tasks
                tasks = [
                    task for task in asyncio.all_tasks()
                    if 'aiodocker' in str(task) and not task.done()
                ]
                if tasks:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
            except Exception as err:
                _LOGGER.error("Error during Docker insights cleanup: %s", err)
            finally:
                self._session_manager = None
                self._monitor_ready.clear()
                self._closed = True

    @property
    def is_connected(self) -> bool:
        """Check if Docker client is connected."""
        return bool(self._session_manager and self._session_manager.is_connected())

    async def ensure_valid_session(self) -> bool:
            """Ensure we have a valid Docker session."""
            if self._disabled:
                return False

            async with self._connection_lock:
                try:
                    if not self._session_manager or not self.is_connected:
                        if self._session_manager:
                            await self._session_manager.close()
                            self._session_manager = None
                        # Add delay between reconnection attempts    
                        if self._stats_retry_count > 0:
                            await asyncio.sleep(min(1.0 * (2 ** (self._stats_retry_count - 1)), 30))
                        return await self.connect()

                    return True

                except Exception as err:
                    _LOGGER.debug("Session validation failed: %s", err)
                    if self._session_manager:
                        await self._session_manager.close()
                        self._session_manager = None
                    return False

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
        """Get Docker container statistics with improved error handling."""
        if self._disabled or self._busy or self._closed:
            return {"containers": {}, "summary": {}}

        max_retries = 3
        current_retry = 0
        backoff_time = 1  # Start with 1 second delay

        while current_retry < max_retries:
            try:
                if not await self.ensure_valid_session():
                    # Add exponential backoff for reconnection attempts
                    await asyncio.sleep(min(backoff_time * (2 ** current_retry), 30))
                    return {"containers": {}, "summary": {}}

                stats = await self._session_manager.execute_with_retry(
                    lambda docker: self._get_stats(docker)
                )

                # Reset error counters on success
                if self._stats_retry_count > 0:
                    _LOGGER.debug(
                        "Successfully recovered Docker stats collection after %d retries",
                        self._stats_retry_count
                    )
                    self._stats_retry_count = 0

                return stats

            except Exception as err:
                current_retry += 1
                self._stats_retry_count += 1

                # Handle different error types
                if any(msg in str(err).lower() for msg in [
                    "session is closed", 
                    "nonetype", 
                    "not connected",
                    "connection reset",
                    "timeout"
                ]):
                    if current_retry < max_retries:
                        _LOGGER.debug(
                            "Docker session state changed (attempt %d/%d): %s",
                            current_retry,
                            max_retries,
                            err
                        )
                        
                        # Force session refresh with backoff
                        await self.cleanup()
                        await asyncio.sleep(min(backoff_time * (2 ** (current_retry - 1)), 30))
                        continue
                    else:
                        _LOGGER.debug(
                            "Docker session error after %d retries: %s",
                            max_retries,
                            err
                        )
                else:
                    _LOGGER.error("Error collecting Docker stats: %s", err)

                # Return empty stats on error
                return {"containers": {}, "summary": {}}

        _LOGGER.debug(
            "Failed to collect Docker stats after %d retries",
            max_retries
        )
        return {"containers": {}, "summary": {}}

    async def _get_stats(self, docker: aiodocker.Docker) -> Dict[str, Any]:
        """Get Docker container statistics with improved error handling."""
        if self._disabled or not docker:
            return {"containers": {}, "summary": {}}

        # Initialize empty stats structure
        containers_stats = {}
        summary = {
            "containers_running": 0,
            "containers_paused": 0,
            "containers_stopped": 0,
            "total_containers": 0,
            "total_cpu_percentage": 0.0,
            "total_memory_percentage": 0.0
        }

        try:
            if not hasattr(docker, 'containers'):
                _LOGGER.debug("Invalid Docker client state")
                return {"containers": {}, "summary": {}}

            try:
                containers = await docker.containers.list(all=True)
            except Exception as err:
                if any(msg in str(err).lower() for msg in [
                    "session is closed",
                    "not connected",
                    "connection reset",
                    "nonetype"
                ]):
                    _LOGGER.debug("Docker connection state changed during container list: %s", err)
                else:
                    _LOGGER.error("Failed to list containers: %s", err)
                return {"containers": {}, "summary": {}}

            # Process each container with improved error handling
            for container in containers:
                if self._disabled:
                    return {"containers": {}, "summary": {}}

                try:
                    # Get container details with timeout protection
                    async with asyncio.timeout(10):  # 10 second timeout per container
                        info = await container.show()
                        stats = await container.stats(stream=False)

                    if not info or not stats:
                        continue

                    state = info["State"]
                    config = info["Config"]
                    container_name = info["Name"].lstrip("/")

                    # Basic container stats
                    container_stats = {
                        "state": state["Status"],
                        "status": self._get_status_string(state),
                        "health": state.get("Health", {}).get("Status", "none"),
                        "image": config["Image"],
                        "version": config["Image"].split(":")[-1] if ":" in config["Image"] else "latest"
                    }

                    # Add runtime stats if container is running
                    if state["Status"] == "running" and stats:
                        try:
                            stats_obj = stats[0]
                            await self._process_container_runtime_stats(
                                container_stats, 
                                stats_obj, 
                                container_name, 
                                summary
                            )
                        except (IndexError, KeyError) as err:
                            _LOGGER.debug("Error processing runtime stats for %s: %s", container_name, err)
                            continue

                    # Update summary counters
                    if state["Status"] == "running":
                        summary["containers_running"] += 1
                        summary["total_cpu_percentage"] += container_stats.get("cpu_percentage", 0)
                        summary["total_memory_percentage"] += container_stats.get("memory_percentage", 0)
                    elif state["Status"] == "paused":
                        summary["containers_paused"] += 1
                    else:
                        summary["containers_stopped"] += 1

                    # Store container stats
                    containers_stats[container_name] = container_stats

                except asyncio.TimeoutError:
                    _LOGGER.debug("Timeout getting stats for container %s", container_name)
                    continue
                except Exception as err:
                    if any(msg in str(err).lower() for msg in [
                        "session is closed",
                        "not connected",
                        "connection reset",
                        "nonetype"
                    ]):
                        _LOGGER.debug("Connection state changed for container %s: %s", 
                                    container_name, err)
                    else:
                        _LOGGER.error("Error processing container %s: %s", 
                                    container_name, err)
                    continue

            # Update summary stats only if not disabled
            if not self._disabled:
                summary["total_containers"] = len(containers_stats)
                summary["total_cpu_percentage"] = round(summary["total_cpu_percentage"], 2)
                summary["total_memory_percentage"] = round(summary["total_memory_percentage"], 2)

            return {
                "containers": containers_stats,
                "summary": summary
            }

        except Exception as err:
            # Handle connection-related errors at debug level
            if any(msg in str(err).lower() for msg in [
                "session is closed",
                "not connected",
                "connection reset",
                "nonetype"
            ]):
                _LOGGER.debug("Docker connection state changed: %s", err)
            else:
                _LOGGER.error("Error getting container stats: %s", err)
            return {"containers": {}, "summary": {}}

    async def _process_container_runtime_stats(
        self,
        container_stats: Dict[str, Any],
        stats_obj: Dict[str, Any],
        container_name: str,
        summary: Dict[str, Any]
    ) -> None:
        """Process runtime statistics for a running container."""
        try:
            # CPU stats
            cpu_stats = stats_obj["cpu_stats"]
            precpu_stats = stats_obj["precpu_stats"]
            
            cpu_delta = float(cpu_stats["cpu_usage"]["total_usage"] - 
                        precpu_stats["cpu_usage"]["total_usage"])
            system_delta = float(cpu_stats["system_cpu_usage"] - 
                            precpu_stats["system_cpu_usage"])
            num_cpus = len(cpu_stats["cpu_usage"].get("percpu_usage", [])) or 1
            
            if system_delta > 0 and not self._disabled:
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
            
            if not self._disabled:
                memory_usage = used_memory / (1024 * 1024)  # Convert to MB
                container_stats["memory_usage"] = round(memory_usage, 2)
                container_stats["memory_limit"] = round(memory_limit, 2)
                container_stats["memory_percentage"] = round((memory_usage / memory_limit) * 100.0, 2)

            # Network stats if available
            if "networks" in stats_obj and not self._disabled:
                await self._process_network_stats(container_stats, stats_obj["networks"], container_name)

        except Exception as err:
            _LOGGER.error("Error processing container runtime stats: %s", err)

    async def _process_network_stats(
        self,
        container_stats: Dict[str, Any],
        networks: Dict[str, Any],
        container_name: str
    ) -> None:
        """Process network statistics for a container."""
        if self._disabled or not self._session_manager:
            return
        
        try:
            total_rx = 0
            total_tx = 0
            
            current_time = datetime.now(timezone.utc)

            for interface in networks.values():
                total_rx += interface["rx_bytes"]
                total_tx += interface["tx_bytes"]

            # Calculate rates if we have previous stats and not disabled
            if container_name in self._prev_stats and not self._disabled:
                try:
                    time_delta = (current_time - self._prev_time[container_name]).total_seconds()
                    prev_stats = self._prev_stats[container_name]
                    
                    if time_delta > 0:
                        rx_delta = max(0, total_rx - prev_stats["rx_bytes"])  # Prevent negative values
                        tx_delta = max(0, total_tx - prev_stats["tx_bytes"])
                        
                        container_stats["network_speed_down"] = round((rx_delta / 1024) / time_delta, 2)  # KB/s
                        container_stats["network_speed_up"] = round((tx_delta / 1024) / time_delta, 2)  # KB/s
                except Exception as err:
                    _LOGGER.debug("Error calculating network rates: %s", err)
                    # Continue to update totals even if rate calculation fails
            
            # Only update previous stats if not disabled
            if not self._disabled:
                self._prev_stats[container_name] = {
                    "rx_bytes": total_rx,
                    "tx_bytes": total_tx
                }
                self._prev_time[container_name] = current_time
            
            # Update totals
            container_stats["network_total_down"] = round(total_rx / (1024 * 1024), 2)  # MB
            container_stats["network_total_up"] = round(total_tx / (1024 * 1024), 2)  # MB

        except Exception as err:
            _LOGGER.error("Error processing network stats: %s", err)

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
