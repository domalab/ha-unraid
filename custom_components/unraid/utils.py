"""Utility functions for Unraid integration."""
from __future__ import annotations

import logging
import re

_LOGGER = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    """Normalize a name for use in entity IDs."""
    # Convert to lowercase and replace invalid characters with underscores
    normalized = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    # Remove consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    return normalized.strip('_')

def validate_entity_name(name: str) -> bool:
    """Validate entity name follows conventions."""
    return bool(re.match(r'^[a-z0-9_]+$', name))
