"""Connection manager for Unraid integration."""
from __future__ import annotations

import logging
import asyncio
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

import asyncssh  # type: ignore

_LOGGER = logging.getLogger(__name__)

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
        """Establish the SSH connection."""
        if self.state == ConnectionState.ACTIVE:
            return
            
        async with self.lock:
            if self.state == ConnectionState.ACTIVE:
                return
                
            try:
                self.state = ConnectionState.CONNECTING
                self.conn = await asyncssh.connect(
                    self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    known_hosts=None
                )
                self.state = ConnectionState.ACTIVE
                self.metrics.last_used = datetime.now()
                _LOGGER.debug(
                    "Connected to %s (conn_id=%s)", 
                    self.host,
                    id(self)
                )
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
        """Execute a command over the SSH connection."""
        if self.conn is None or self.state != ConnectionState.ACTIVE:
            await self.connect()
            
        if timeout is None:
            timeout = self._command_timeout
            
        start_time = time.time()
        try:
            self.metrics.last_used = datetime.now()
            self.metrics.command_count += 1
            
            async with asyncio.timeout(timeout):
                result = await self.conn.run(command)
                
            exec_time = time.time() - start_time
            self.metrics.total_command_time += exec_time
            return result
            
        except Exception as err:
            exec_time = time.time() - start_time
            self.metrics.total_command_time += exec_time
            self.metrics.error_count += 1
            self.state = ConnectionState.ERROR
            self.conn = None
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
        self._max_lifetime = 300  # Maximum connection lifetime in seconds
        self._retry_interval = 10  # Retry interval in seconds
        self._lock = asyncio.Lock()
        
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
            now = datetime.now()
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
                except Exception as err:
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
        """Execute a command using a connection from the pool."""
        attempt = 0
        last_error = None
        
        while attempt <= max_retries:
            try:
                if attempt > 0:
                    backoff_time = self._calculate_backoff(attempt)
                    _LOGGER.debug(
                        "Retrying command (attempt %d/%d) after %.1f seconds: %s",
                        attempt,
                        max_retries + 1,
                        backoff_time,
                        command
                    )
                    await asyncio.sleep(backoff_time)
                
                conn = await self.get_connection()
                return await conn.execute_command(command, timeout)
                
            except Exception as err:
                self._recent_errors.append(datetime.now())
                last_error = err
                attempt += 1
                _LOGGER.debug(
                    "Command failed (attempt %d/%d): %s - %s",
                    attempt,
                    max_retries + 1,
                    command,
                    err
                )
        
        # If we get here, all retries have failed
        _LOGGER.error(
            "Command failed after %d retries: %s", 
            max_retries, 
            command
        )
        raise last_error
    
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