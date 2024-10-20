"""DataUpdateCoordinator for Unraid."""
from datetime import timedelta
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_CHECK_INTERVAL
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.api = api
        self.entry = entry

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data[CONF_CHECK_INTERVAL]),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Unraid."""
        try:
            await self.api.connect()
            data = {
                "system_stats": await self.api.get_system_stats(),
                "docker_containers": await self.api.get_docker_containers(),
                "vms": await self.api.get_vms(),
                "user_scripts": await self.api.get_user_scripts(),
            }
            await self.api.disconnect()
            return data
        except Exception as err:
            _LOGGER.error("Error communicating with Unraid: %s", err)
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Perform initial connection to check if the server is reachable
            await self.api.connect()
            await self.api.disconnect()
            return True
        except Exception as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err