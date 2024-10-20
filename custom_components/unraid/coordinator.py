"""DataUpdateCoordinator for Unraid."""
import asyncio
from datetime import timedelta
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_CHECK_INTERVAL,
    CONF_PING_INTERVAL,
)
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.api = api
        self.entry = entry
        self.ping_interval = entry.data[CONF_PING_INTERVAL]
        self._is_online = False
        self._ping_task: asyncio.Task | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.data[CONF_CHECK_INTERVAL]),
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
            }

            return data
        except Exception as err:
            _LOGGER.error("Error communicating with Unraid: %s", err)
            self._is_online = False
            raise UpdateFailed(f"Error communicating with Unraid: {err}") from err

    async def ping_unraid(self) -> None:
        """Ping the Unraid server to check if it's online."""
        while True:
            try:
                is_online = await asyncio.wait_for(self.api.ping(), timeout=10.0)
                if is_online and not self._is_online:
                    _LOGGER.info("Unraid server is back online")
                    self._is_online = True
                    await self.async_request_refresh()
                elif not is_online and self._is_online:
                    _LOGGER.warning("Unraid server is offline")
                    self._is_online = False
            except asyncio.TimeoutError:
                _LOGGER.warning("Ping to Unraid server timed out")
                self._is_online = False
            except Exception as e:
                _LOGGER.error("Error pinging Unraid server: %s", e)
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
            self._is_online = await asyncio.wait_for(self.api.ping(), timeout=10.0)
            if not self._is_online:
                raise ConfigEntryNotReady("Unraid server is not reachable")
        except (asyncio.TimeoutError, Exception) as err:
            _LOGGER.error("Failed to connect to Unraid server: %s", err)
            raise ConfigEntryNotReady from err

        await self.start_ping_task()

        return True