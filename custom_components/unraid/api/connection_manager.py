"""Connection manager for Unraid integration."""
from __future__ import annotations

import logging
import asyncio
import time
from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import asyncssh  # type: ignore

_LOGGER = logging.getLogger(__name__)


class UnraidConnectionError(Exception):
    """Base class for Unraid connection errors."""
    pass


class CommandTimeoutError(UnraidConnectionError):
    """Raised when a command times out."""
    pass


class CommandError(UnraidConnectionError):
    """Raised when a command fails with an error."""
    def __init__(self, message: str, exit_code: Optional[int] = None):
        super().__init__(message)
        self.exit_code = exit_code

class ConnectionState(Enum):
    """Connection state enum."""
    IDLE = auto()
    CONNECTING = auto()
    ACTIVE = auto()
    ERROR = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()


@dataclass
class ConnectionMetrics:
    """Connection metrics data."""
    created_at: datetime
    last_used: datetime
    command_count: int = 0
    error_count: int = 0
    total_command_time: float = 0.0

    @property
    def age(self) -> float:
        """Get the age of the connection in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_time(self) -> float:
        """Get the idle time of the connection in seconds."""
        return (datetime.now() - self.last_used).total_seconds()

    @property
    def avg_command_time(self) -> float:
        """Get the average command execution time."""
        if self.command_count == 0:
            return 0.0
        return self.total_command_time / self.command_count


class SSHConnection:
    """A managed SSH connection."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22
    ) -> None:
        """Initialize the connection."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port

        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.state = ConnectionState.DISCONNECTED
        self.metrics = ConnectionMetrics(
            created_at=datetime.now(),
            last_used=datetime.now()
        )
        self.lock = asyncio.Lock()
        self._command_timeout = 60

    async def connect(self) -> None:
        """Establish the SSH connection with improved error handling."""
        if self.state == ConnectionState.ACTIVE:
            return

        async with self.lock:
            if self.state == ConnectionState.ACTIVE:
                return

            try:
                self.state = ConnectionState.CONNECTING

                # Specific error handling for different SSH connection issues
                try:
                    self.conn = await asyncssh.connect(
                        self.host,
                        username=self.username,
                        password=self.password,
                        port=self.port,
                        known_hosts=None,
                        keepalive_interval=30,  # Send keepalive every 30 seconds
                        keepalive_count_max=3,  # Disconnect after 3 failed keepalives
                        login_timeout=10         # 10 second login timeout
                    )
                    self.state = ConnectionState.ACTIVE
                    self.metrics.last_used = datetime.now()
                    _LOGGER.debug(
                        "Connected to %s (conn_id=%s)",
                        self.host,
                        id(self)
                    )
                    # Reset error count on successful connection
                    if self.metrics.error_count > 0:
                        _LOGGER.info(
                            "Connection to %s recovered after %d errors",
                            self.host,
                            self.metrics.error_count
                        )
                        self.metrics.error_count = 0

                except asyncssh.DisconnectError as err:
                    self.state = ConnectionState.ERROR
                    self.metrics.error_count += 1
                    _LOGGER.error(
                        "SSH disconnection error for %s: %s",
                        self.host,
                        err
                    )
                    raise ConnectionError(f"SSH disconnection: {err}") from err

                except asyncssh.ConnectionLost as err:
                    self.state = ConnectionState.ERROR
                    self.metrics.error_count += 1
                    _LOGGER.error(
                        "SSH connection lost to %s: %s",
                        self.host,
                        err
                    )
                    raise ConnectionError(f"SSH connection lost: {err}") from err

                except asyncssh.PermissionDenied as err:
                    self.state = ConnectionState.ERROR
                    self.metrics.error_count += 1
                    _LOGGER.error(
                        "SSH authentication failed for %s: %s",
                        self.host,
                        err
                    )
                    raise ConnectionError(f"SSH authentication failed: {err}") from err

                except asyncssh.HostKeyNotVerifiable as err:
                    self.state = ConnectionState.ERROR
                    self.metrics.error_count += 1
                    _LOGGER.error(
                        "SSH host key verification failed for %s: %s",
                        self.host,
                        err
                    )
                    raise ConnectionError(f"SSH host key verification failed: {err}") from err

                except asyncio.TimeoutError:
                    self.state = ConnectionState.ERROR
                    self.metrics.error_count += 1
                    _LOGGER.error(
                        "SSH connection timeout for %s",
                        self.host
                    )
                    raise ConnectionError("SSH connection timeout") from None

            except Exception as err:
                self.state = ConnectionState.ERROR
                self.metrics.error_count += 1
                _LOGGER.error(
                    "Connection failed to %s: %s",
                    self.host,
                    err
                )
                raise

    async def disconnect(self) -> None:
        """Disconnect the SSH connection."""
        if self.conn is None or self.state == ConnectionState.DISCONNECTED:
            self.state = ConnectionState.DISCONNECTED
            return

        async with self.lock:
            if self.conn is None:
                self.state = ConnectionState.DISCONNECTED
                return

            try:
                self.state = ConnectionState.DISCONNECTING
                self.conn.close()
                await self.conn.wait_closed()
                _LOGGER.debug(
                    "Disconnected from %s (conn_id=%s)",
                    self.host,
                    id(self)
                )
            except Exception as err:
                _LOGGER.debug(
                    "Error during disconnect from %s: %s",
                    self.host,
                    err
                )
            finally:
                self.conn = None
                self.state = ConnectionState.DISCONNECTED

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None
    ) -> asyncssh.SSHCompletedProcess:
        """Execute a command over the SSH connection with improved error handling."""
        if self.conn is None or self.state != ConnectionState.ACTIVE:
            await self.connect()

        if timeout is None:
            timeout = self._command_timeout

        start_time = time.time()
        try:
            self.metrics.last_used = datetime.now()
            self.metrics.command_count += 1

            try:
                async with asyncio.timeout(timeout):
                    result = await self.conn.run(command)

                exec_time = time.time() - start_time
                self.metrics.total_command_time += exec_time
                return result

            except asyncio.TimeoutError:
                exec_time = time.time() - start_time
                self.metrics.total_command_time += exec_time
                self.metrics.error_count += 1
                _LOGGER.error(
                    "Command timed out after %.1f seconds: %s",
                    exec_time,
                    command[:100] + ("..." if len(command) > 100 else "")
                )
                self.state = ConnectionState.ERROR
                self.conn = None
                raise CommandTimeoutError(
                    f"Command timed out after {exec_time:.1f} seconds"
                ) from None

            except asyncssh.ProcessError as err:
                exec_time = time.time() - start_time
                self.metrics.total_command_time += exec_time
                self.metrics.error_count += 1
                _LOGGER.error(
                    "Command process error: %s (exit_code=%s, command=%s)",
                    err,
                    getattr(err, 'exit_status', 'unknown'),
                    command[:100] + ("..." if len(command) > 100 else "")
                )
                # Don't mark connection as bad for process errors
                raise CommandError(
                    f"Process error: {err}",
                    exit_code=getattr(err, 'exit_status', None)
                ) from err

            except (asyncssh.ConnectionLost, asyncssh.DisconnectError) as err:
                exec_time = time.time() - start_time
                self.metrics.total_command_time += exec_time
                self.metrics.error_count += 1
                _LOGGER.error(
                    "SSH connection lost during command: %s",
                    err
                )
                self.state = ConnectionState.ERROR
                self.conn = None
                raise ConnectionError(f"SSH connection lost: {err}") from err

        except Exception as err:
            # Catch any other exceptions not handled above
            exec_time = time.time() - start_time
            self.metrics.total_command_time += exec_time
            self.metrics.error_count += 1
            self.state = ConnectionState.ERROR
            self.conn = None
            _LOGGER.error(
                "Unhandled error during command execution: %s (command=%s)",
                err,
                command[:100] + ("..." if len(command) > 100 else "")
            )
            raise

    @property
    def is_healthy(self) -> bool:
        """Check if the connection is healthy."""
        return (
            self.state == ConnectionState.ACTIVE and
            self.conn is not None and
            self.metrics.error_count < 5
        )

    @property
    def is_reusable(self) -> bool:
        """Check if the connection can be reused."""
        return (
            self.is_healthy and
            self.metrics.age < 300 and  # Max lifetime 5 minutes
            self.metrics.error_count < 3
        )


class ConnectionManager:
    """Manages a pool of SSH connections to Unraid servers."""

    def __init__(self) -> None:
        """Initialize the connection manager."""
        self._pool: List[SSHConnection] = []
        self._pool_size = 3  # Maximum number of concurrent connections
        self._min_idle = 1  # Minimum number of idle connections
        self._max_lifetime = 600  # Maximum connection lifetime in seconds (increased to 10 minutes)
        self._retry_interval = 10  # Retry interval in seconds
        self._lock = asyncio.Lock()
        self._health_check_interval = 60  # Health check interval in seconds
        self._last_health_check = datetime.now()
        self._connection_stats = {
            "reused": 0,
            "created": 0,
            "errors": 0,
            "health_checks": 0,
            "health_check_failures": 0,
            "commands_executed": 0,
            "command_errors": 0,
            "total_command_time": 0.0,
        }

        # Exponential backoff settings
        self._initial_backoff = 1.0
        self._max_backoff = 300.0
        self._backoff_factor = 2.0

        # Last errors for circuit breaker
        self._recent_errors: List[datetime] = []
        self._circuit_breaker_threshold = 5
        self._circuit_breaker_window = 60  # seconds
        self._circuit_open = False
        self._circuit_reset_time: Optional[datetime] = None

        # Command batching settings
        self._command_batch_size = 5  # Maximum number of commands to batch
        self._command_batch_timeout = 0.1  # Maximum time to wait for batching in seconds

    async def initialize(self, host: str, username: str, password: str, port: int = 22) -> None:
        """Initialize the connection pool."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port

        # Seed the pool with one connection
        await self._add_connection()

    async def _add_connection(self) -> SSHConnection:
        """Add a new connection to the pool."""
        connection = SSHConnection(
            host=self.host,
            username=self.username,
            password=self.password,
            port=self.port
        )

        await connection.connect()
        self._pool.append(connection)
        return connection

    async def _clean_pool(self) -> None:
        """Clean up expired or unhealthy connections."""
        async with self._lock:
            to_remove = []

            for conn in self._pool:
                # Check if connection is too old
                if conn.metrics.age > self._max_lifetime:
                    _LOGGER.debug(
                        "Removing connection due to age: %.1f seconds (conn_id=%s)",
                        conn.metrics.age,
                        id(conn)
                    )
                    to_remove.append(conn)
                # Check if connection has too many errors
                elif conn.metrics.error_count >= 5:
                    _LOGGER.debug(
                        "Removing connection due to too many errors: %d (conn_id=%s)",
                        conn.metrics.error_count,
                        id(conn)
                    )
                    to_remove.append(conn)
                # Check if connection is in error state
                elif conn.state == ConnectionState.ERROR:
                    _LOGGER.debug(
                        "Removing connection due to error state (conn_id=%s)",
                        id(conn)
                    )
                    to_remove.append(conn)

            # Remove expired connections
            for conn in to_remove:
                await conn.disconnect()
                self._pool.remove(conn)

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff time."""
        backoff = self._initial_backoff * (self._backoff_factor ** attempt)
        return min(backoff, self._max_backoff)

    def _check_circuit_breaker(self) -> bool:
        """Check if the circuit breaker is open."""
        if not self._circuit_open:
            # Clean up old errors
            now = datetime.now()
            self._recent_errors = [
                t for t in self._recent_errors
                if (now - t).total_seconds() < self._circuit_breaker_window
            ]

            # Check if we've exceeded the threshold
            if len(self._recent_errors) >= self._circuit_breaker_threshold:
                self._circuit_open = True
                self._circuit_reset_time = now + timedelta(seconds=self._max_backoff)
                _LOGGER.warning(
                    "Circuit breaker tripped for %s - too many errors (%d)",
                    self.host,
                    len(self._recent_errors)
                )
                return True

            return False

        # Check if it's time to reset the circuit breaker
        if self._circuit_reset_time and datetime.now() > self._circuit_reset_time:
            self._circuit_open = False
            self._recent_errors = []
            self._circuit_reset_time = None
            _LOGGER.info("Circuit breaker reset for %s", self.host)
            return False

        return True

    async def get_connection(self) -> SSHConnection:
        """Get a connection from the pool or create a new one."""
        if self._check_circuit_breaker():
            raise ConnectionError(f"Circuit breaker open for {self.host}")

        # First clean the pool
        await self._clean_pool()

        # Log pool health metrics periodically (every 100 calls)
        metrics = self.get_metrics()
        if metrics["total_commands"] % 100 == 0:
            _LOGGER.debug(
                "Connection pool health: %s active, %s total, %s errors, circuit: %s",
                metrics["active_connections"],
                metrics["pool_size"],
                metrics["total_errors"],
                metrics["circuit_breaker_status"]
            )

        async with self._lock:
            # Look for a reusable connection
            for conn in self._pool:
                if conn.is_reusable:
                    _LOGGER.debug(
                        "Reusing existing connection (conn_id=%s, age=%.1fs, cmds=%d)",
                        id(conn),
                        conn.metrics.age,
                        conn.metrics.command_count
                    )
                    return conn

            # If we have capacity, create a new connection
            if len(self._pool) < self._pool_size:
                try:
                    conn = await self._add_connection()
                    _LOGGER.debug("Created new connection (conn_id=%s)", id(conn))
                    return conn
                except Exception:
                    self._recent_errors.append(datetime.now())
                    raise

            # Otherwise, find the least used connection
            least_used = min(
                self._pool,
                key=lambda c: c.metrics.command_count
            )
            _LOGGER.debug(
                "Pool full, reusing least used connection (conn_id=%s, cmds=%d)",
                id(least_used),
                least_used.metrics.command_count
            )
            return least_used

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        max_retries: int = 2
    ) -> asyncssh.SSHCompletedProcess:
        """Execute a command using a connection from the pool with improved retry logic."""
        attempt = 0
        last_error = None
        command_preview = command[:100] + ("..." if len(command) > 100 else "")

        while attempt <= max_retries:
            try:
                if attempt > 0:
                    backoff_time = self._calculate_backoff(attempt)
                    _LOGGER.debug(
                        "Retrying command (attempt %d/%d) after %.1f seconds: %s",
                        attempt,
                        max_retries + 1,
                        backoff_time,
                        command_preview
                    )
                    await asyncio.sleep(backoff_time)

                conn = await self.get_connection()
                return await conn.execute_command(command, timeout)

            except CommandTimeoutError as err:
                self._recent_errors.append(datetime.now())
                last_error = err
                attempt += 1
                _LOGGER.warning(
                    "Command timed out (attempt %d/%d): %s",
                    attempt,
                    max_retries + 1,
                    command_preview
                )
                # Continue with retry for timeouts

            except CommandError as err:
                self._recent_errors.append(datetime.now())
                last_error = err

                # Don't retry if the command itself failed with a non-zero exit code
                # as it's likely to fail again
                if err.exit_code is not None and err.exit_code != 0:
                    _LOGGER.warning(
                        "Command failed with exit code %d, not retrying: %s",
                        err.exit_code,
                        command_preview
                    )
                    raise

                # For other command errors, retry
                attempt += 1
                _LOGGER.warning(
                    "Command error (attempt %d/%d): %s - %s",
                    attempt,
                    max_retries + 1,
                    command_preview,
                    err
                )

            except ConnectionError as err:
                self._recent_errors.append(datetime.now())
                last_error = err
                attempt += 1
                _LOGGER.warning(
                    "Connection error (attempt %d/%d): %s - %s",
                    attempt,
                    max_retries + 1,
                    command_preview,
                    err
                )
                # Continue with retry for connection errors

            except Exception as err:
                self._recent_errors.append(datetime.now())
                last_error = err
                attempt += 1
                _LOGGER.warning(
                    "Unexpected error (attempt %d/%d): %s - %s",
                    attempt,
                    max_retries + 1,
                    command_preview,
                    err
                )
                # Continue with retry for unexpected errors

        # If we get here, all retries failed
        _LOGGER.error(
            "Command failed after %d attempts: %s",
            max_retries + 1,
            command_preview
        )

        # Provide more context in the error message
        if isinstance(last_error, CommandTimeoutError):
            raise CommandTimeoutError(
                f"Command timed out after {max_retries + 1} attempts: {command_preview}"
            ) from last_error
        elif isinstance(last_error, CommandError):
            raise CommandError(
                f"Command failed after {max_retries + 1} attempts: {command_preview}",
                exit_code=last_error.exit_code
            ) from last_error
        elif isinstance(last_error, ConnectionError):
            raise ConnectionError(
                f"Connection error after {max_retries + 1} attempts: {command_preview}"
            ) from last_error
        elif last_error:
            raise last_error
        else:
            raise ConnectionError(f"Command failed after {max_retries + 1} attempts: {command_preview}")

    async def shutdown(self) -> None:
        """Shutdown the connection manager."""
        async with self._lock:
            for conn in self._pool:
                await conn.disconnect()
            self._pool = []

    async def health_check(self) -> bool:
        """Perform a health check on a connection."""
        try:
            conn = await self.get_connection()
            result = await conn.execute_command("echo")
            return result.exit_status == 0
        except Exception as err:
            _LOGGER.error("Health check failed: %s", err)
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Get connection pool metrics."""
        active_count = len([c for c in self._pool if c.state == ConnectionState.ACTIVE])
        error_count = len([c for c in self._pool if c.state == ConnectionState.ERROR])

        total_commands = sum(c.metrics.command_count for c in self._pool)
        total_errors = sum(c.metrics.error_count for c in self._pool)
        error_rate = total_errors / max(total_commands, 1)

        return {
            "pool_size": len(self._pool),
            "active_connections": active_count,
            "error_connections": error_count,
            "total_commands": total_commands,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "circuit_breaker_status": "open" if self._circuit_open else "closed",
            "recent_errors": len(self._recent_errors)
        }