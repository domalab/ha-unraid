"""API client for Unraid."""
from __future__ import annotations

import logging
import asyncio
import os
import aiofiles # type: ignore
from typing import Optional

import asyncssh # type: ignore
from .const import AUTH_METHOD_PASSWORD # type: ignore

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

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        password: str | None = None,
        ssh_key_path: str | None = None,
        auth_method: str = AUTH_METHOD_PASSWORD
    ) -> None:
        
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
        self.ssh_key_path = ssh_key_path
        self.auth_method = auth_method
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.lock = asyncio.Lock()
        self.connect_timeout = 30
        self.command_timeout = 60

    async def ensure_connection(self) -> None:
        """Ensure that a connection to the Unraid server is established."""
        if self.conn is None:
            async with self.lock:
                if self.conn is None:
                    try:
                        # Prepare connection parameters
                        conn_params = {
                            "username": self.username,
                            "port": self.port,
                            "known_hosts": None,
                        }

                        if self.auth_method == AUTH_METHOD_PASSWORD:
                            if not self.password:
                                raise ValueError("Password required for password authentication")
                            conn_params["password"] = self.password
                        else:  # key authentication
                            if not self.ssh_key_path:
                                raise ValueError("SSH key path required for key authentication")
                            
                            # Verify the SSH key file exists and is readable
                            if not os.path.isfile(self.ssh_key_path):
                                raise FileNotFoundError(f"SSH key file not found: {self.ssh_key_path}")
                            
                            try:
                                # Check if file is readable using aiofiles
                                async with aiofiles.open(self.ssh_key_path, 'r', encoding='utf-8') as _:
                                    pass
                                conn_params["client_keys"] = [self.ssh_key_path]
                            except (IOError, PermissionError) as err:
                                raise ValueError(f"SSH key file not readable: {err}") from err

                        self.conn = await asyncssh.connect(
                            self.host,
                            **conn_params
                        )
                    except (asyncssh.Error, OSError) as err:
                        self.conn = None
                        _LOGGER.error("Connection failed: %s", err)
                        raise

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