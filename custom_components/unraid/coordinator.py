"""DataUpdateCoordinator for Unraid."""
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from datetime import timedelta
import logging

from .unraid import UnraidAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data["check_interval"]),
        )
        self.api = api
        self.entry = entry

    async def _async_update_data(self):
        """Fetch data from Unraid."""
        try:
            if not await self.api.ping():
                raise UpdateFailed("Unraid server is unreachable")
            
            return {
                "system_stats": await self.api.get_system_stats(),
                "docker_containers": await self.api.get_docker_containers(),
                "vms": await self.api.get_vms(),
                "user_scripts": await self.api.get_user_scripts(),
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Perform initial ping to check if the server is online
            if not await self.api.ping():
                raise ConfigEntryNotReady("Failed to connect to Unraid server")
        except Exception as err:
            _LOGGER.error(f"Failed to connect to Unraid server: {err}")
            raise ConfigEntryNotReady from err

        return True