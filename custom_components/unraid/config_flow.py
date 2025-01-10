"""Config flow for Unraid integration."""
from __future__ import annotations

import logging
import os
import aiofiles # type: ignore
from typing import Any
from dataclasses import dataclass


import voluptuous as vol # type: ignore
from homeassistant import config_entries # type: ignore
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore
from homeassistant.exceptions import HomeAssistantError # type: ignore
from homeassistant.helpers import selector # type: ignore

from .const import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    CONF_AUTH_METHOD,
    CONF_SSH_KEY_PATH,
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

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidConfigFlowData:
    """Unraid Config Flow Data class."""

    host: str
    username: str
    port: int = DEFAULT_PORT
    password: str | None = None
    ssh_key_path: str | None = None
    auth_method: str = AUTH_METHOD_PASSWORD
    general_interval: int = DEFAULT_GENERAL_INTERVAL
    disk_interval: int = DEFAULT_DISK_INTERVAL
    has_ups: bool = False

async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    
    Args:
        data: Dictionary containing user input from config flow.
            Must contain: host, username, auth_method
            If auth_method is password: must contain password
            If auth_method is ssh_key: must contain ssh_key_path
            Optional: port, general_interval, disk_interval, has_ups
            
    Returns:
        Dictionary containing title for the config entry
        
    Raises:
        CannotConnect: Error connecting to the Unraid server
        ValueError: Required fields are missing or invalid
        Exception: Other errors during validation
    """
    # Validate required base fields
    if not data.get(CONF_HOST):
        raise ValueError("Host is required")
    if not data.get(CONF_USERNAME):
        raise ValueError("Username is required")
    if not data.get(CONF_AUTH_METHOD):
        raise ValueError("Authentication method is required")

    # Validate port range if provided
    port = data.get(CONF_PORT, DEFAULT_PORT)
    if not 1 <= port <= 65535:
        raise ValueError(f"Port {port} is invalid. Must be between 1 and 65535")
        
    # Validate auth method specific requirements
    auth_method = data[CONF_AUTH_METHOD]
    if auth_method == AUTH_METHOD_PASSWORD:
        if not data.get(CONF_PASSWORD):
            raise ValueError("Password is required for password authentication")
    elif auth_method == AUTH_METHOD_KEY:
        ssh_key_path = data.get(CONF_SSH_KEY_PATH)
        if not ssh_key_path:
            raise ValueError("SSH key path is required for key authentication")
        
        # Validate SSH key file
        try:
            if not os.path.exists(ssh_key_path):
                raise ValueError(f"SSH key file not found: {ssh_key_path}")
            if not os.path.isfile(ssh_key_path):
                raise ValueError(f"SSH key path is not a file: {ssh_key_path}")
            
            # Check if file is readable
            try:
                async with aiofiles.open(ssh_key_path, 'r', encoding='utf-8') as _:
                    pass
            except (IOError, PermissionError) as err:
                raise ValueError(f"SSH key file not readable: {err}") from err
                
        except Exception as err:
            raise ValueError(f"Invalid SSH key: {err}") from err
    else:
        raise ValueError(f"Invalid authentication method: {auth_method}")

    # Create API instance for connection test
    api = UnraidAPI(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        port=port,
        password=data.get(CONF_PASSWORD),
        ssh_key_path=data.get(CONF_SSH_KEY_PATH),
        auth_method=auth_method
    )

    try:
        async with api:
            # Test connection by attempting to ping the server
            if not await api.ping():
                raise CannotConnect("Failed to connect to Unraid server")
            
            # If successful, try to get hostname for a better title
            try:
                hostname = await api.get_hostname()
                if hostname:
                    return {"title": f"Unraid Server ({hostname})"}
            except Exception as err:
                _LOGGER.warning("Could not get hostname: %s", err)
                
            # Fallback to using IP/host if hostname not available
            return {"title": f"Unraid Server ({data[CONF_HOST]})"}
            
    except Exception as err:
        _LOGGER.error("Connection test failed: %s", err)
        raise CannotConnect("Failed to connect to Unraid server") from err

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unraid."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        # Store user input across steps
        self.host: str | None = None
        self.username: str | None = None
        self.auth_method: str | None = None
        self.password: str | None = None
        self.ssh_key_path: str | None = None
        self.port: int = DEFAULT_PORT
        self.general_interval: int = DEFAULT_GENERAL_INTERVAL
        self.disk_interval: int = DEFAULT_DISK_INTERVAL
        self.has_ups: bool = False
        self.reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Start the auth method step
        return await self.async_step_auth_method()

    async def async_step_auth_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle authentication method step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Save the user input
                self.host = user_input[CONF_HOST]
                self.username = user_input[CONF_USERNAME]
                self.auth_method = user_input[CONF_AUTH_METHOD]
                
                # Check for duplicate entry
                await self.async_set_unique_id(
                    self.host.lower(),
                    raise_on_progress=True
                )
                self._abort_if_unique_id_configured()
                
                # Proceed to auth details
                return await self.async_step_auth_details()
                
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Build the schema for auth method step
        schema_fields = {
            vol.Required(
                CONF_HOST,
                default=self.host or ""
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_USERNAME,
                default=self.username or ""
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_AUTH_METHOD,
                default=self.auth_method or AUTH_METHOD_PASSWORD
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"label": "Password", "value": AUTH_METHOD_PASSWORD},
                        {"label": "SSH Key", "value": AUTH_METHOD_KEY},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        }

        return self.async_show_form(
            step_id="auth_method",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "host_description": "IP address or hostname of your Unraid server",
                "username_description": "Username for SSH access",
                "auth_method_description": "Choose authentication method",
            },
        )

    async def async_step_auth_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle authentication details step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Save the authentication details
                if self.auth_method == AUTH_METHOD_PASSWORD:
                    self.password = user_input[CONF_PASSWORD]
                else:
                    self.ssh_key_path = user_input[CONF_SSH_KEY_PATH]
                    # Validate SSH key path
                    if not os.path.isfile(self.ssh_key_path):
                        raise ValueError(f"SSH key file not found: {self.ssh_key_path}")
                    try:
                        async with aiofiles.open(self.ssh_key_path, 'r', encoding='utf-8') as _:
                            pass
                    except (IOError, PermissionError) as err:
                        raise ValueError(f"SSH key file not readable: {err}") from err

                # Proceed to other settings
                return await self.async_step_other_settings()

            except ValueError as err:
                errors["base"] = str(err)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Build schema based on auth method
        schema_fields = {}
        if self.auth_method == AUTH_METHOD_PASSWORD:
            schema_fields[vol.Required(CONF_PASSWORD)] = selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            )
        else:
            schema_fields[vol.Required(CONF_SSH_KEY_PATH)] = selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                )
            )

        return self.async_show_form(
            step_id="auth_details",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "password_description": "Password for SSH access",
                "ssh_key_description": "Path to SSH private key file",
            },
        )

    async def async_step_other_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle other settings step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Save the settings
                self.port = user_input.get(CONF_PORT, DEFAULT_PORT)
                self.general_interval = user_input[CONF_GENERAL_INTERVAL]
                self.disk_interval = user_input[CONF_DISK_INTERVAL]
                self.has_ups = user_input[CONF_HAS_UPS]

                # Combine all data
                data = {
                    CONF_HOST: self.host,
                    CONF_USERNAME: self.username,
                    CONF_AUTH_METHOD: self.auth_method,
                    CONF_PORT: self.port,
                    CONF_GENERAL_INTERVAL: self.general_interval,
                    CONF_DISK_INTERVAL: self.disk_interval,
                    CONF_HAS_UPS: self.has_ups,
                }

                # Add auth credentials based on method
                if self.auth_method == AUTH_METHOD_PASSWORD:
                    data[CONF_PASSWORD] = self.password
                else:
                    data[CONF_SSH_KEY_PATH] = self.ssh_key_path

                # Final validation and connection test
                try:
                    info = await validate_input(data)
                    return self.async_create_entry(title=info["title"], data=data)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except ValueError as err:
                    errors["base"] = str(err)
                except Exception:  # pylint: disable=broad-except
                    errors["base"] = "unknown"

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Build schema for other settings
        schema_fields = {
            vol.Optional(
                CONF_PORT,
                default=self.port
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=65535,
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_GENERAL_INTERVAL,
                default=self.general_interval
            ): vol.All(
                vol.Coerce(int),
                vol.Range(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_GENERAL_INTERVAL
                )
            ),
            vol.Required(
                CONF_DISK_INTERVAL,
                default=self.disk_interval
            ): vol.All(
                vol.Coerce(int),
                vol.Range(
                    min=MIN_DISK_INTERVAL,
                    max=MAX_DISK_INTERVAL
                )
            ),
            vol.Required(
                CONF_HAS_UPS,
                default=self.has_ups
            ): selector.BooleanSelector(),
        }

        return self.async_show_form(
            step_id="other_settings",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "port_description": f"SSH port (default: {DEFAULT_PORT})",
                "general_interval_description": (
                    "How often to update non-disk sensors (1-60 minutes)"
                ),
                "disk_interval_description": (
                    "How often to update disk information (1-24 hours)"
                ),
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthorization request."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._host = entry_data[CONF_HOST]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthorization confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None and self.reauth_entry:
            try:
                # Get original auth method
                auth_method = self.reauth_entry.data.get(CONF_AUTH_METHOD, AUTH_METHOD_PASSWORD)
                data = {**self.reauth_entry.data, **user_input}
                data[CONF_AUTH_METHOD] = auth_method
                
                await validate_input(data)

                self.hass.config_entries.async_update_entry(
                    self.reauth_entry, data=data
                )
                await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        # Show appropriate reauth form based on auth method
        auth_method = self.reauth_entry.data.get(CONF_AUTH_METHOD, AUTH_METHOD_PASSWORD)
        schema = {vol.Required(CONF_USERNAME): str}
        
        if auth_method == AUTH_METHOD_PASSWORD:
            schema[vol.Required(CONF_PASSWORD)] = str
        else:
            schema[vol.Required(CONF_SSH_KEY_PATH)] = str

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(import_data)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> UnraidOptionsFlowHandler:
        """Get the options flow for this handler."""
        return UnraidOptionsFlowHandler(config_entry)

class UnraidOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Unraid."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
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
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_GENERAL_INTERVAL: user_input[CONF_GENERAL_INTERVAL],
                    CONF_DISK_INTERVAL: user_input[CONF_DISK_INTERVAL],
                    CONF_HAS_UPS: user_input[CONF_HAS_UPS],
                },
            )

        schema = vol.Schema({
            vol.Optional(CONF_PORT, default=self._port): vol.Coerce(int),
            vol.Required(
                CONF_GENERAL_INTERVAL,
                default=self._general_interval
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_GENERAL_INTERVAL)
            ),
            vol.Required(
                CONF_DISK_INTERVAL,
                default=self._disk_interval
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_DISK_INTERVAL, max=MAX_DISK_INTERVAL)
            ),
            vol.Required(CONF_HAS_UPS, default=self._has_ups): bool,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "general_interval_description": (
                    "How often to update non-disk sensors (1-60 minutes)"
                ),
                "disk_interval_description": (
                    "How often to update disk information (1-24 hours)"
                ),
            },
        )

class CannotConnect(HomeAssistantError):
    """Error raised when we cannot connect to the Unraid server."""