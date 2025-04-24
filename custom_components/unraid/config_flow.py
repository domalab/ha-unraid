"""Config flow for Unraid integration.

This module provides the configuration flow for the Unraid integration.
It includes:
- Initial setup flow with validation
- Options flow for updating settings
- Reauthorization flow for updating credentials
- Validation functions for hostname, port, and credentials

The config flow includes advanced validation to ensure that the user provides
valid information before attempting to connect to the Unraid server, improving
the overall user experience and reducing connection failures.
"""
from __future__ import annotations

import logging
import re
import socket
from typing import Any, Dict
from dataclasses import dataclass

import voluptuous as vol # type: ignore
from homeassistant import config_entries # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore
from homeassistant.exceptions import HomeAssistantError # type: ignore
from homeassistant.core import HomeAssistant, callback # type: ignore
# from homeassistant.helpers import importlib as ha_importlib # type: ignore

from .migrations import async_migrate_with_rollback

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_GENERAL_INTERVAL,
    CONF_DISK_INTERVAL,
    DEFAULT_GENERAL_INTERVAL,
    DEFAULT_DISK_INTERVAL,
    DISK_INTERVAL_OPTIONS,
    GENERAL_INTERVAL_OPTIONS,
    CONF_HAS_UPS,
    MIGRATION_VERSION,
)
from .unraid import UnraidAPI

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidConfigFlowData:
    """Unraid Config Flow Data class."""

    host: str
    username: str
    password: str
    port: int = DEFAULT_PORT
    general_interval: int = DEFAULT_GENERAL_INTERVAL
    disk_interval: int = DEFAULT_DISK_INTERVAL
    has_ups: bool = False

@callback
def get_schema_base(
    general_interval: int,
    disk_interval: int,
    include_auth: bool = False,
    has_ups: bool = False,
) -> vol.Schema:
    """Get base schema with dropdowns for both intervals."""
    # Create a list of options for the disk interval selector
    disk_interval_options = {
        option: f"{option // 60} hours" if option >= 60 else f"{option} minutes"
        for option in DISK_INTERVAL_OPTIONS
    }

    # Create a list of options for the general interval selector
    general_interval_options = {
        option: f"{option} minutes" for option in GENERAL_INTERVAL_OPTIONS
    }

    if include_auth:
        # Initial setup schema with correct field order
        schema = {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(
            CONF_GENERAL_INTERVAL,
            default=general_interval
            ): vol.In(general_interval_options),
            vol.Required(
            CONF_DISK_INTERVAL,
            default=disk_interval
            ): vol.In(disk_interval_options),
            vol.Required(CONF_HAS_UPS, default=has_ups): bool,
        }
    else:
        # Options schema remains unchanged
        schema = {
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
            vol.Required(
                CONF_GENERAL_INTERVAL,
                default=general_interval
            ): vol.In(general_interval_options),
            vol.Required(
                CONF_DISK_INTERVAL,
                default=disk_interval
            ): vol.In(disk_interval_options),
            vol.Required(CONF_HAS_UPS, default=has_ups): bool,
        }

    return vol.Schema(schema)

@callback
def get_init_schema(general_interval: int, disk_interval: int) -> vol.Schema:
    """Get schema for initial setup."""
    return get_schema_base(general_interval, disk_interval, include_auth=True)

@callback
def get_options_schema(
    general_interval: int,
    disk_interval: int,
    has_ups: bool,
) -> vol.Schema:
    """Get schema for options flow."""
    return get_schema_base(
        general_interval,
        disk_interval,
        has_ups=has_ups
    )

async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    This function performs comprehensive validation of the user input:
    1. Validates the hostname/IP address format
    2. Validates the port number is within range
    3. Validates the credentials are not empty
    4. Attempts to connect to the Unraid server

    The function raises specific exceptions for different types of validation failures,
    which allows the config flow to provide specific error messages to the user.

    Args:
        data: A dictionary containing the user input (host, username, password, port)

    Returns:
        A dictionary containing the title for the config entry

    Raises:
        InvalidHost: If the hostname is empty or invalid
        InvalidPort: If the port is not within the valid range
        InvalidCredentials: If the username or password is empty
        CannotConnect: If the connection to the Unraid server fails
    """
    # Validate hostname/IP
    host_errors = validate_hostname(data[CONF_HOST])
    if host_errors:
        if "host" in host_errors and host_errors["host"] == "empty_host":
            raise InvalidHost("Host cannot be empty")
        elif "host" in host_errors and host_errors["host"] == "invalid_host":
            raise InvalidHost("Invalid hostname or IP address")

    # Validate port
    port_errors = validate_port(data[CONF_PORT])
    if port_errors:
        if "port" in port_errors and port_errors["port"] == "invalid_port":
            raise InvalidPort("Invalid port number")

    # Validate credentials
    cred_errors = validate_credentials(data[CONF_USERNAME], data[CONF_PASSWORD])
    if cred_errors:
        if "username" in cred_errors and cred_errors["username"] == "empty_username":
            raise InvalidCredentials("Username cannot be empty")
        elif "password" in cred_errors and cred_errors["password"] == "empty_password":
            raise InvalidCredentials("Password cannot be empty")

    # If all validation passes, try to connect
    api = UnraidAPI(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT])

    try:
        async with api:
            if not await api.ping():
                raise CannotConnect("Failed to connect to Unraid server")
    except Exception as err:
        raise CannotConnect from err

    return {"title": f"Unraid Server ({data[CONF_HOST]})"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unraid."""

    VERSION = MIGRATION_VERSION

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._general_interval = DEFAULT_GENERAL_INTERVAL
        self._disk_interval = DEFAULT_DISK_INTERVAL
        self._host: str | None = None
        self.reauth_entry: config_entries.ConfigEntry | None = None

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
                data = {**self.reauth_entry.data, **user_input}
                await validate_input(data)

                self.hass.config_entries.async_update_entry(
                    self.reauth_entry, data=data
                )
                await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except InvalidCredentials as err:
                _LOGGER.error("Invalid credentials: %s", err)
                if "username" in str(err).lower():
                    errors["username"] = "empty_username"
                else:
                    errors["password"] = "empty_password"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    @callback
    def _async_get_schema(self) -> vol.Schema:
        """Get a schema using the default or already configured options."""
        return get_init_schema(self._general_interval, self._disk_interval)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._host = user_input[CONF_HOST]
                info = await validate_input(user_input)

                await self.async_set_unique_id(
                    self._host.lower(),
                    raise_on_progress=True
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)
            except InvalidHost as err:
                _LOGGER.error("Invalid host: %s", err)
                if "empty" in str(err).lower():
                    errors["host"] = "empty_host"
                else:
                    errors["host"] = "invalid_host"
            except InvalidPort:
                _LOGGER.error("Invalid port")
                errors["port"] = "invalid_port"
            except InvalidCredentials as err:
                _LOGGER.error("Invalid credentials: %s", err)
                if "username" in str(err).lower():
                    errors["username"] = "empty_username"
                else:
                    errors["password"] = "empty_password"
            except CannotConnect:
                _LOGGER.error("Cannot connect to Unraid server")
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        schema = self._async_get_schema()

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host_description": "IP address or hostname of your Unraid server",
                "username_description": "Username for SSH access",
                "password_description": "Password for SSH access",
                "port_description": f"SSH port (default: {DEFAULT_PORT})",
                "general_interval_description": (
                    "How often to update non-disk sensors (1-60 minutes)"
                ),
                "disk_interval_description": (
                    "How often to update disk information (5 minutes to 24 hours)"
                ),
            },
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(import_data)

    # Migration is now handled in __init__.py to follow best practices
    # This method is kept for backward compatibility but delegates to the handler in __init__.py
    async def async_migrate_entry(self, hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Handle migration of config entries."""
        _LOGGER.debug("Delegating migration to handler in __init__.py")
        # Import the migration handler from __init__.py
        from . import async_migrate_entry as init_migrate_entry
        return await init_migrate_entry(hass, entry)

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

        # Create a list of options for the disk interval selector
        disk_interval_options = {
            option: f"{option // 60} hours" if option >= 60 else f"{option} minutes"
            for option in DISK_INTERVAL_OPTIONS
        }

        # Create a list of options for the general interval selector
        general_interval_options = {
            option: f"{option} minutes" for option in GENERAL_INTERVAL_OPTIONS
        }

        schema = vol.Schema({
            vol.Optional(CONF_PORT, default=self._port): vol.Coerce(int),
            vol.Required(
                CONF_GENERAL_INTERVAL,
                default=self._general_interval
            ): vol.In(general_interval_options),
            vol.Required(
                CONF_DISK_INTERVAL,
                default=self._disk_interval
            ): vol.In(disk_interval_options),
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
                    "How often to update disk information (5 minutes to 24 hours)"
                ),
            },
        )

def validate_hostname(hostname: str) -> Dict[str, str]:
    """Validate hostname or IP address.

    This function performs several checks on the provided hostname:
    1. Checks if the hostname is empty
    2. Checks if the hostname is a valid IP address
    3. If not an IP address, checks if it's a valid hostname format
    4. Attempts to resolve the hostname (but doesn't fail if resolution fails)

    Args:
        hostname: The hostname or IP address to validate

    Returns:
        A dictionary of errors, where the key is the field name and the value is the error code.
        An empty dictionary means no errors were found.
    """
    errors: Dict[str, str] = {}

    # Check if hostname is empty
    if not hostname:
        errors["host"] = "empty_host"
        return errors

    # Check if hostname is a valid IP address
    try:
        socket.inet_aton(hostname)
        # It's a valid IP address
        return errors
    except socket.error:
        # Not an IP address, check if it's a valid hostname
        # Using a more efficient regex that avoids potential exponential backtracking
        if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$", hostname):
            errors["host"] = "invalid_host"
            return errors

        # Try to resolve the hostname
        try:
            socket.gethostbyname(hostname)
        except socket.gaierror:
            # Hostname doesn't resolve, but we'll still allow it
            # as it might be resolvable in the user's network
            _LOGGER.warning("Hostname %s doesn't resolve, but allowing it", hostname)

    return errors

def validate_port(port: int) -> Dict[str, str]:
    """Validate port number.

    This function checks if the provided port number is within the valid range (1-65535).

    Args:
        port: The port number to validate

    Returns:
        A dictionary of errors, where the key is the field name and the value is the error code.
        An empty dictionary means no errors were found.
    """
    errors: Dict[str, str] = {}

    if port < 1 or port > 65535:
        errors["port"] = "invalid_port"

    return errors

def validate_credentials(username: str, password: str) -> Dict[str, str]:
    """Validate username and password.

    This function checks if the provided username and password are not empty.

    Args:
        username: The username to validate
        password: The password to validate

    Returns:
        A dictionary of errors, where the key is the field name and the value is the error code.
        An empty dictionary means no errors were found.
    """
    errors: Dict[str, str] = {}

    if not username:
        errors["username"] = "empty_username"

    if not password:
        errors["password"] = "empty_password"

    return errors

class InvalidHost(HomeAssistantError):
    """Error raised when the host is invalid."""

class InvalidPort(HomeAssistantError):
    """Error raised when the port is invalid."""

class InvalidCredentials(HomeAssistantError):
    """Error raised when the credentials are invalid."""

class CannotConnect(HomeAssistantError):
    """Error raised when we cannot connect to the Unraid server."""