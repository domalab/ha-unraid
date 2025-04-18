"""Data handler for Unraid integration - compatibility layer."""
from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

from .exceptions import UnraidConnectionError
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)


class UnraidDataHandler:
    """Data handler for Unraid integration - compatibility layer for tests."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        data_path: str = None,
        use_ssh: bool = True,
    ) -> None:
        """Initialize the data handler."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.data_path = data_path
        self.use_ssh = use_ssh
        
        # Create an UnraidAPI instance for actual operations
        self.api = UnraidAPI(host, username, password, port)
        
        # Cache for data
        self._data: Dict[str, Any] = {}
        self._last_update: Optional[datetime] = None

    async def async_load_data(self) -> Dict[str, Any]:
        """Load data from Unraid server or cache."""
        try:
            # If we have a data path, try to load from file first
            if self.data_path:
                # Generate filename based on host
                filename = f"unraid_data_{self.host.replace('.', '_')}.json"
                filepath = os.path.join(self.data_path, filename)
                
                # Check if file exists and is recent
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "r") as f:
                            data = json.load(f)
                            self._data = data
                            return data
                    except (json.JSONDecodeError, IOError) as err:
                        _LOGGER.warning("Error loading data from file: %s", err)
            
            # If no file or error, fetch from API
            system_stats = await self.api.get_system_stats()
            disk_info = await self.api.get_disk_info()
            docker_info = await self.api.get_docker_info()
            vm_info = await self.api.get_vm_info()
            ups_info = await self.api.get_ups_info()
            network_info = await self.api.get_network_info()
            
            # Combine all data
            self._data = {
                "system_stats": system_stats,
                "disks": disk_info.get("disk_list", []),
                "docker_containers": docker_info.get("containers", []),
                "vms": vm_info.get("vms", []),
                "ups_info": ups_info,
                "network_info": network_info,
                "parity_status": {"status": "idle", "progress": 0},
                "plugins": [],
                "shares": [],
                "users": [],
                "alerts": [],
                "array_status": {"status": "Started", "protection_status": "Normal"},
            }
            
            # Save to file if data_path is set
            if self.data_path:
                try:
                    filename = f"unraid_data_{self.host.replace('.', '_')}.json"
                    filepath = os.path.join(self.data_path, filename)
                    with open(filepath, "w") as f:
                        json.dump(self._data, f)
                except IOError as err:
                    _LOGGER.warning("Error saving data to file: %s", err)
            
            self._last_update = datetime.now()
            return self._data
            
        except Exception as err:
            _LOGGER.error("Error loading data from Unraid server: %s", err)
            raise UnraidConnectionError(f"Failed to connect to Unraid server: {err}") from err
