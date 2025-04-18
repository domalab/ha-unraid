"""Compatibility layer for the old UnraidClient class."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from .unraid import UnraidAPI
from .data_handler import UnraidDataHandler
from .exceptions import UnraidConnectionError

_LOGGER = logging.getLogger(__name__)

class UnraidClient:
    """Legacy client for Unraid servers - compatibility layer."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        data_path: str = None,
        use_ssh: bool = True
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.data_path = data_path
        self.use_ssh = use_ssh
        self._data_handler = None

        # Create an UnraidAPI instance for actual operations
        self.api = UnraidAPI(host, username, password, port)

    def _init_data_handler(self) -> None:
        """Initialize the data handler."""
        if self._data_handler is None:
            self._data_handler = UnraidDataHandler(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                data_path=self.data_path,
                use_ssh=self.use_ssh
            )

    async def connect(self) -> bool:
        """Connect to the Unraid server."""
        try:
            await self.api.ensure_connection()
            return True
        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        await self.api.disconnect()

    async def execute_command(self, command: str, timeout: Optional[int] = None) -> Any:
        """Execute a command on the Unraid server."""
        return await self.api.execute_command(command, timeout)

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics from the Unraid server."""
        return await self.api.get_system_stats()

    async def get_disk_info(self) -> Dict[str, Any]:
        """Get disk information from the Unraid server."""
        # Combine disk usage and array usage
        disk_data, extra_stats = await self.api.get_individual_disk_usage()
        array_data = await self.api.get_array_usage()

        return {
            "disk_list": disk_data,
            "array_usage": array_data,
            **extra_stats
        }

    async def get_docker_containers(self) -> List[Dict[str, Any]]:
        """Get Docker container information from the Unraid server."""
        docker_info = await self.api.get_docker_info()
        return docker_info.get("containers", [])

    async def get_vms(self) -> List[Dict[str, Any]]:
        """Get VM information from the Unraid server."""
        vm_info = await self.api.get_vm_info()
        return vm_info.get("vms", [])

    async def get_network_interfaces(self) -> List[Dict[str, Any]]:
        """Get network interface information from the Unraid server."""
        network_info = await self.api.get_network_info()
        return network_info.get("interfaces", [])

    async def get_ups_info(self) -> Dict[str, Any]:
        """Get UPS information from the Unraid server."""
        return await self.api.get_ups_info()

    async def ping(self) -> bool:
        """Check if the Unraid server is accessible."""
        return await self.api.ping()

    # Methods for test_client.py compatibility
    async def async_get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("system_stats", {})
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get system stats: {err}") from err

    async def async_get_disk_info(self) -> List[Dict[str, Any]]:
        """Get disk information from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("disks", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get disk info: {err}") from err

    async def async_get_docker_containers(self) -> List[Dict[str, Any]]:
        """Get Docker container information from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("docker_containers", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get docker containers: {err}") from err

    async def async_get_vms(self) -> List[Dict[str, Any]]:
        """Get VM information from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("vms", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get VMs: {err}") from err

    async def async_get_ups_info(self) -> Dict[str, Any]:
        """Get UPS information from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("ups_info", {})
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get UPS info: {err}") from err

    async def async_get_parity_status(self) -> Dict[str, Any]:
        """Get parity status from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("parity_status", {})
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get parity status: {err}") from err

    async def async_get_plugins(self) -> List[Dict[str, Any]]:
        """Get plugins from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("plugins", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get plugins: {err}") from err

    async def async_get_shares(self) -> List[Dict[str, Any]]:
        """Get shares from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("shares", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get shares: {err}") from err

    async def async_get_users(self) -> List[Dict[str, Any]]:
        """Get users from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("users", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get users: {err}") from err

    async def async_get_alerts(self) -> List[Dict[str, Any]]:
        """Get alerts from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("alerts", [])
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get alerts: {err}") from err

    async def async_get_array_status(self) -> Dict[str, Any]:
        """Get array status from the Unraid server."""
        try:
            self._init_data_handler()
            data = await self._data_handler.async_load_data()
            return data.get("array_status", {})
        except Exception as err:
            raise UnraidConnectionError(f"Failed to get array status: {err}") from err
