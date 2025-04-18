"""Exceptions for the Unraid integration."""


class UnraidError(Exception):
    """Base exception for Unraid integration."""


class UnraidConnectionError(UnraidError):
    """Exception raised when connection to Unraid server fails."""


class UnraidAuthError(UnraidError):
    """Exception raised when authentication to Unraid server fails."""


class UnraidDataError(UnraidError):
    """Exception raised when data from Unraid server is invalid."""


class UnraidCommandError(UnraidError):
    """Exception raised when a command on Unraid server fails."""
