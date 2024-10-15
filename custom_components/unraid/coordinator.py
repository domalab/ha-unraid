"""DataUpdateCoordinator for Unraid."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.api = api
        self.entry = entry
        self.ping_interval = entry.data["ping_interval"]
        self._is_online = True
        self._ping_task = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data["check_interval"]),
        )

    async def _async_update_data(self):
        """Fetch data from Unraid."""
        if not self._is_online:
            raise UpdateFailed("Unraid server is offline")

        try:
            system_stats = await self.api.get_system_stats()
            docker_containers = await self.api.get_docker_containers()
            vms = await self.api.get_vms()
            user_scripts = await self.api.get_user_scripts()

            return {
                "system_stats": system_stats,
                "docker_containers": docker_containers,
                "vms": vms,
                "user_scripts": user_scripts,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def ping_unraid(self):
        """Ping the Unraid server to check if it's online."""
        while True:
            try:
                await self.api.ping()
                if not self._is_online:
                    _LOGGER.info("Unraid server is back online")
                    self._is_online = True
                    await self.async_request_refresh()
            except Exception:
                if self._is_online:
                    _LOGGER.warning("Unraid server is offline")
                    self._is_online = False
            
            await asyncio.sleep(self.ping_interval)

    async def start_ping_task(self):
        """Start the ping task."""
        if self._ping_task is None:
            self._ping_task = self.hass.async_create_task(self.ping_unraid())

    async def stop_ping_task(self):
        """Stop the ping task."""
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None