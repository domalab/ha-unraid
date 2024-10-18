"""Config flow for Unraid integration."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from .unraid import UnraidAPI
from .const import DOMAIN, DEFAULT_PORT, DEFAULT_PING_INTERVAL, DEFAULT_CHECK_INTERVAL, UPDATE_CHECK_INTERVAL

UPDATE_INTERVALS = {
    "Every 6 hours": 21600,
    "Every 12 hours": 43200,
    "Daily": 86400,
    "Every 2 days": 172800,
    "Weekly": 604800,
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional("ping_interval", default=DEFAULT_PING_INTERVAL): vol.All(
            int, vol.Range(min=10, max=3600)
        ),
        vol.Optional("check_interval", default=DEFAULT_CHECK_INTERVAL): vol.All(
            int, vol.Range(min=60, max=3600)
        ),
        vol.Optional(UPDATE_CHECK_INTERVAL, default="Daily"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(UPDATE_INTERVALS.keys()),
                mode=selector.SelectSelectorMode.DROPDOWN
            )
        ),
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = UnraidAPI(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT])

    try:
        await api.connect()
        await api.disconnect()
    except Exception as err:
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {"title": f"Unraid Server ({data[CONF_HOST]})"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unraid."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                # Convert the friendly interval name to seconds
                user_input[UPDATE_CHECK_INTERVAL] = UPDATE_INTERVALS[user_input[UPDATE_CHECK_INTERVAL]]
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "host_description": "IP address or hostname of your Unraid server",
                "username_description": "Username for SSH access to your Unraid server",
                "password_description": "Password for SSH access to your Unraid server",
                "port_description": "SSH port (default is 22)",
                "ping_interval_description": "How often to check if the server is online (in seconds)",
                "check_interval_description": "How often to update sensor data (in seconds)",
                "update_check_interval_description": "How often to check for container updates",
            },
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""