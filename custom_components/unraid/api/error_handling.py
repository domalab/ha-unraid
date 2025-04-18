"""Error handling utilities for Unraid integration."""
from __future__ import annotations

import logging
import functools
import asyncio
from typing import Any, Callable, TypeVar, cast, Optional

from .connection_manager import CommandTimeoutError, CommandError, UnraidConnectionError

_LOGGER = logging.getLogger(__name__)

# Type variables for function signatures
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


class UnraidAPIError(Exception):
    """Base class for Unraid API errors."""
    pass


class UnraidDataError(UnraidAPIError):
    """Raised when there's an error parsing or processing data."""
    pass


class UnraidTimeoutError(UnraidAPIError):
    """Raised when an operation times out."""
    pass


class UnraidOperationError(UnraidAPIError):
    """Raised when an operation fails."""
    def __init__(self, message: str, exit_code: Optional[int] = None):
        super().__init__(message)
        self.exit_code = exit_code


def with_error_handling(
    fallback_return: Optional[Any] = None,
    max_retries: int = 2,
    retry_delay: float = 1.0
) -> Callable[[F], F]:
    """Decorator to add error handling to API operations.

    Args:
        fallback_return: Value to return if the operation fails
        max_retries: Maximum number of retries for the operation
        retry_delay: Delay between retries in seconds

    Returns:
        Decorated function with error handling
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0

            while retries <= max_retries:
                try:
                    return await func(*args, **kwargs)

                except CommandTimeoutError as err:
                    # Error handling
                    retries += 1
                    if retries > max_retries:
                        _LOGGER.error(
                            "Operation timed out after %d retries: %s",
                            max_retries,
                            func.__name__
                        )
                        if fallback_return is not None:
                            return fallback_return
                        raise UnraidTimeoutError(f"Operation timed out: {err}") from err

                    _LOGGER.warning(
                        "Operation timed out, retrying (%d/%d): %s",
                        retries,
                        max_retries + 1,
                        func.__name__
                    )
                    await asyncio.sleep(retry_delay * retries)

                except CommandError as err:
                    # Error handling
                    # Don't retry if the command itself failed with a non-zero exit code
                    if err.exit_code is not None and err.exit_code != 0:
                        _LOGGER.error(
                            "Command failed with exit code %d: %s",
                            err.exit_code,
                            func.__name__
                        )
                        if fallback_return is not None:
                            return fallback_return
                        raise UnraidOperationError(
                            f"Command failed: {err}",
                            exit_code=err.exit_code
                        ) from err

                    # For other command errors, retry
                    retries += 1
                    if retries > max_retries:
                        _LOGGER.error(
                            "Operation failed after %d retries: %s",
                            max_retries,
                            func.__name__
                        )
                        if fallback_return is not None:
                            return fallback_return
                        raise UnraidOperationError(f"Operation failed: {err}") from err

                    _LOGGER.warning(
                        "Operation failed, retrying (%d/%d): %s",
                        retries,
                        max_retries + 1,
                        func.__name__
                    )
                    await asyncio.sleep(retry_delay * retries)

                except (ConnectionError, UnraidConnectionError) as err:
                    # Error handling
                    retries += 1
                    if retries > max_retries:
                        _LOGGER.error(
                            "Connection error after %d retries: %s",
                            max_retries,
                            func.__name__
                        )
                        if fallback_return is not None:
                            return fallback_return
                        raise UnraidConnectionError(f"Connection error: {err}") from err

                    _LOGGER.warning(
                        "Connection error, retrying (%d/%d): %s",
                        retries,
                        max_retries + 1,
                        func.__name__
                    )
                    await asyncio.sleep(retry_delay * retries)

                except Exception as err:
                    # last_error = err
                    _LOGGER.error(
                        "Unexpected error in %s: %s",
                        func.__name__,
                        err,
                        exc_info=True
                    )
                    if fallback_return is not None:
                        return fallback_return
                    raise UnraidAPIError(f"Unexpected error: {err}") from err

            # This should never happen, but just in case
            if fallback_return is not None:
                return fallback_return
            raise UnraidAPIError(f"Operation failed after {max_retries} retries")

        return cast(F, wrapper)
    return decorator


def safe_parse(
    parser_func: Callable[[Any], T],
    data: Any,
    default: Optional[T] = None,
    error_msg: str = "Error parsing data"
) -> T:
    """Safely parse data with error handling.

    Args:
        parser_func: Function to parse the data
        data: Data to parse
        default: Default value to return if parsing fails
        error_msg: Error message to log if parsing fails

    Returns:
        Parsed data or default value if parsing fails
    """
    try:
        return parser_func(data)
    except Exception as err:
        _LOGGER.error("%s: %s", error_msg, err)
        if default is not None:
            return default
        raise UnraidDataError(f"{error_msg}: {err}") from err
