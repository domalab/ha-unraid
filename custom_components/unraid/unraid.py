"""API client for Unraid."""
from __future__ import annotations

import logging
import asyncio
from typing import Optional

import asyncssh # type: ignore

from .api.network_operations import NetworkOperationsMixin
from .api.disk_operations import DiskOperationsMixin
from .api.docker_operations import DockerOperationsMixin
from .api.vm_operations import VMOperationsMixin
from .api.system_operations import SystemOperationsMixin
from .api.ups_operations import UPSOperationsMixin
from .api.userscript_operations import UserScriptOperationsMixin

_LOGGER = logging.getLogger(__name__)

class UnraidAPI(
    NetworkOperationsMixin,
    DiskOperationsMixin,
    DockerOperationsMixin,
    VMOperationsMixin,
    SystemOperationsMixin,
    UPSOperationsMixin,
    UserScriptOperationsMixin
):
    """API client for interacting with Unraid servers."""

    def __init__(self, host: str, username: str, password: str, port: int = 22) -> None:
        """Initialize the Unraid API client."""
        
        # Initialize Network Operations
        NetworkOperationsMixin.__init__(self)

        # Initialize other mixins
        DiskOperationsMixin.__init__(self)
        DockerOperationsMixin.__init__(self)
        VMOperationsMixin.__init__(self)
        SystemOperationsMixin.__init__(self)
        UPSOperationsMixin.__init__(self)
        UserScriptOperationsMixin.__init__(self)

        # Set up network ops reference
        if isinstance(self, SystemOperationsMixin):
            self.set_network_ops(self)

        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.lock = asyncio.Lock()
        self.connect_timeout = 30
        self.command_timeout = 60

    async def ensure_connection(self) -> None:
        """Ensure that a connection to the Unraid server is established."""
        if self.conn is None:
            async with self.lock:
                if self.conn is None:
                    self.conn = await asyncssh.connect(
                        self.host,
                        username=self.username,
                        password=self.password,
                        port=self.port,
                        known_hosts=None
                    )

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None
    ) -> asyncssh.SSHCompletedProcess:
        """Execute a command on the Unraid server."""
        await self.ensure_connection()
        try:
            if timeout is None:
                timeout = self.command_timeout

            async with asyncio.timeout(timeout):
                result = await self.conn.run(command)
                return result

        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.error("Command failed: %s", err)
            self.conn = None  # Reset connection on error
            raise

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        if self.conn:
            try:
                self.conn.close()
                await self.conn.wait_closed()
            except Exception as err:
                _LOGGER.error("Error disconnecting from Unraid server: %s", err)
            finally:
                self.conn = None

    async def ping(self) -> bool:
        """Check if the Unraid server is accessible via SSH."""
        try:
            async with asyncio.timeout(self.connect_timeout):
                await self.ensure_connection()
                await self.conn.run("echo")

            _LOGGER.debug("Successfully pinged Unraid server at %s", self.host)
            return True

        except (asyncssh.Error, asyncio.TimeoutError, OSError) as err:
            _LOGGER.error("Failed to ping Unraid server at %s: %s", self.host, err)
            return False

    async def __aenter__(self) -> 'UnraidAPI':
        """Enter async context."""
        await self.ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        await self.disconnect()
