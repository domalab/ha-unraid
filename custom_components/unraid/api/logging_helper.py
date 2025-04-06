"""Logging helper functions for Unraid integration."""
from __future__ import annotations

import logging
from typing import Dict, Any

# Store original logging levels to restore later
_ORIGINAL_LEVELS: Dict[str, int] = {}

def setup_logging_filters() -> None:
    """Set up logging filters to reduce verbosity of common loggers."""
    # Store and adjust logging levels for noisy libraries
    noisy_loggers = [
        "asyncssh",
        "asyncio",
        "custom_components.unraid.api.connection_manager",
    ]
    
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        if logger_name not in _ORIGINAL_LEVELS:
            _ORIGINAL_LEVELS[logger_name] = logger.level
        
        # Set asyncssh to WARNING level by default (too verbose at INFO)
        if logger_name == "asyncssh":
            logger.setLevel(logging.WARNING)
        # Set asyncio to WARNING (reduces event loop noise)
        elif logger_name == "asyncio":
            logger.setLevel(logging.WARNING)
        # Set connection manager to INFO (reduces debug connection spam)
        elif logger_name == "custom_components.unraid.api.connection_manager":
            logger.setLevel(logging.INFO)

def restore_logging_levels() -> None:
    """Restore original logging levels."""
    for logger_name, level in _ORIGINAL_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level) 