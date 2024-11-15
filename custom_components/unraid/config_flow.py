"""Config flow for Unraid integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_GENERAL_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MAX_GENERAL_INTERVAL,
    MIN_DISK_INTERVAL,
    MAX_DISK_INTERVAL,
    CONF_HAS_UPS,
)
from .unraid import UnraidAPI

def get_schema_base(
    general_interval: int,
    disk_interval: int,
    include_auth: bool = False,
    has_ups: bool = False,
) -> vol.Schema:
    """Get base schema with sliders for both intervals."""
    schema = {
        vol.Required(
            CONF_GENERAL_INTERVAL,
            default=general_interval
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_UPDATE_INTERVAL,
                max=MAX_GENERAL_INTERVAL,
                msg=f"General interval must be between {MIN_UPDATE_INTERVAL} and {MAX_GENERAL_INTERVAL} minutes"
            )
        ),
        vol.Required(
            CONF_DISK_INTERVAL,
            default=disk_interval
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_DISK_INTERVAL,
                max=MAX_DISK_INTERVAL,
                msg=f"Disk interval must be between {MIN_DISK_INTERVAL} and {MAX_DISK_INTERVAL} hours"
            )
        ),
    }

    if include_auth:
        auth_schema = {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        }
        schema = {**auth_schema, **schema}
    else:
        schema[vol.Optional(CONF_PORT, default=DEFAULT_PORT)] = vol.Coerce(int)

    schema[vol.Required(CONF_HAS_UPS, default=has_ups)] = bool
    
    return vol.Schema(schema)

def get_init_schema(general_interval: int, disk_interval: int) -> vol.Schema:
    """Get schema for initial setup."""
    return get_schema_base(general_interval, disk_interval, include_auth=True)

def get_options_schema(
    general_interval: int,
    disk_interval: int,
    port: int,
    has_ups: bool
) -> vol.Schema:
    """Get schema for options flow."""
    return get_schema_base(general_interval, disk_interval, has_ups=has_ups)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = UnraidAPI(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT])

    try:
        async with api:
            if not await api.ping():
                raise CannotConnect
    except Exception as err:
        raise CannotConnect from err

    return {"title": f"Unraid Server ({data[CONF_HOST]})"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unraid."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._general_interval = DEFAULT_GENERAL_INTERVAL
        self._disk_interval = DEFAULT_DISK_INTERVAL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        schema = get_init_schema(
            self._general_interval,
            self._disk_interval
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host_description": "IP address or hostname of your Unraid server",
                "username_description": "Username for SSH access",
                "password_description": "Password for SSH access",
                "port_description": f"SSH port (default: {DEFAULT_PORT})",
                "general_interval_description": "How often to update non-disk sensors (1-60 minutes)",
                "disk_interval_description": "How often to update disk information (1-24 hours)",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Unraid."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._general_interval = config_entry.options.get(
            CONF_GENERAL_INTERVAL, DEFAULT_GENERAL_INTERVAL
        )
        self._disk_interval = config_entry.options.get(
            CONF_DISK_INTERVAL, DEFAULT_DISK_INTERVAL
        )
        self._port = config_entry.options.get(CONF_PORT, DEFAULT_PORT)
        self._has_ups = config_entry.options.get(
            CONF_HAS_UPS, 
            config_entry.data.get(CONF_HAS_UPS, False)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    **user_input,
                    CONF_HAS_UPS: user_input.get(CONF_HAS_UPS, self._has_ups)
                }
            )

        schema = get_options_schema(
            self._general_interval,
            self._disk_interval,
            self._port,
            self._has_ups
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""