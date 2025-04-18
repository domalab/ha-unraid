"""API client for Unraid."""
from __future__ import annotations

import logging
from typing import Optional

import asyncssh # type: ignore

from .api.connection_manager import ConnectionManager
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

        # Use ConnectionManager instead of direct connection
        self.connection_manager = ConnectionManager()
        self.connect_timeout = 30
        self.command_timeout = 60
        self._in_context = False
        self._setup_done = False

    async def ensure_connection(self) -> None:
        """Ensure that the connection manager is initialized."""
        if not self._setup_done:
            await self.connection_manager.initialize(
                self.host,
                self.username,
                self.password,
                self.port
            )
            self._setup_done = True

    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None
    ) -> asyncssh.SSHCompletedProcess:
        """Execute a command on the Unraid server using the connection pool."""
        await self.ensure_connection()

        if timeout is None:
            timeout = self.command_timeout

        try:
            result = await self.connection_manager.execute_command(
                command,
                timeout=timeout
            )
            return result

        except Exception as err:
            _LOGGER.error("Command failed: %s", err)
            raise

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        if self._setup_done:
            await self.connection_manager.shutdown()
            self._setup_done = False

    async def ping(self) -> bool:
        """Check if the Unraid server is accessible via SSH."""
        try:
            await self.ensure_connection()
            return await self.connection_manager.health_check()
        except Exception as err:
            _LOGGER.error("Failed to ping Unraid server at %s: %s", self.host, err)
            return False

    async def __aenter__(self) -> 'UnraidAPI':
        """Enter async context."""
        self._in_context = True
        await self.ensure_connection()
        return self

    async def __aexit__(self, *_) -> None:
        """Exit async context."""
        self._in_context = False
        # We don't disconnect here to maintain the connection pool
