"""DataUpdateCoordinator for Unraid."""
import asyncio
from datetime import timedelta
import logging
import time
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, UPDATE_CHECK_INTERVAL
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.api = api
        self.entry = entry
        self.ping_interval = entry.data["ping_interval"]
        self._is_online = False
        self._ping_task = None
        self.update_check_interval = entry.data[UPDATE_CHECK_INTERVAL]
        self.last_update_check = 0
        self.container_updates = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data["check_interval"]),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Unraid."""
        if not self._is_online:
            raise UpdateFailed("Unraid server is offline")

        try:
            data = {
                "system_stats": await self.api.get_system_stats(),
                "docker_containers": await self.api.get_docker_containers(),
                "vms": await self.api.get_vms(),
                "user_scripts": await self.api.get_user_scripts(),
                "container_updates": self.container_updates,
            }

            # Check for updates if the interval has passed
            current_time = time.time()
            if current_time - self.last_update_check >= self.update_check_interval:
                self.hass.async_create_task(self.async_check_updates())

            return data
        except Exception as err:
            _LOGGER.error(f"Error communicating with Unraid: {err}")
            self._is_online = False
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def async_check_updates(self):
        """Check for container updates asynchronously."""
        try:
            self.container_updates = await self.api.check_container_updates()
            self.last_update_check = time.time()
            self.async_set_updated_data(self.data)
        except Exception as err:
            _LOGGER.error(f"Error checking for container updates: {err}")

    async def ping_unraid(self) -> None:
        """Ping the Unraid server to check if it's online."""
        while True:
            try:
                await asyncio.wait_for(self.api.ping(), timeout=10.0)
                if not self._is_online:
                    _LOGGER.info("Unraid server is back online")
                    self._is_online = True
                    await self.async_request_refresh()
            except asyncio.TimeoutError:
                _LOGGER.warning("Ping to Unraid server timed out")
                self._is_online = False
            except Exception as e:
                _LOGGER.error(f"Error pinging Unraid server: {e}")
                self._is_online = False

            await asyncio.sleep(self.ping_interval)

    async def start_ping_task(self) -> None:
        """Start the ping task."""
        if self._ping_task is None:
            self._ping_task = self.hass.async_create_task(self.ping_unraid())

    async def stop_ping_task(self) -> None:
        """Stop the ping task."""
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Perform initial ping to check if the server is online
            await asyncio.wait_for(self.api.ping(), timeout=10.0)
            self._is_online = True
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.error(f"Failed to connect to Unraid server: {err}")
            raise ConfigEntryNotReady from err

        await self.start_ping_task()
        
        # Schedule the first update check
        self.hass.async_create_task(self.async_check_updates())

        return True