"""Config flow for Unraid integration."""
from __future__ import annotations

from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_CHECK_INTERVAL, CONF_CHECK_INTERVAL, CONF_HAS_UPS
from .unraid import UnraidAPI

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL): vol.All(
            int, vol.Range(min=60, max=3600)
        ),
        vol.Required(CONF_HAS_UPS, default=False): bool,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = UnraidAPI(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT])

    try:
        await api.connect()
        has_ups = await api.detect_ups()
        await api.disconnect()
    except Exception as err:
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {"title": f"Unraid Server ({data[CONF_HOST]})", "has_ups": has_ups}

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
                user_input[CONF_HAS_UPS] = info["has_ups"]
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
                "check_interval_description": "How often to update sensor data (in seconds)",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHECK_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_CHECK_INTERVAL,
                            DEFAULT_CHECK_INTERVAL
                        )
                    ): vol.All(int, vol.Range(min=60, max=3600)),
                    vol.Optional(
                        CONF_PORT,
                        default=self.config_entry.options.get(
                            CONF_PORT,
                            DEFAULT_PORT
                        )
                    ): int,
                    vol.Required(
                        CONF_HAS_UPS,
                        default=self.config_entry.options.get(
                            CONF_HAS_UPS,
                            False
                        )
                    ): bool,
                }
            )
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""