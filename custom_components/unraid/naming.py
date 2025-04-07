"""Naming utilities for Unraid integration."""
from __future__ import annotations

import logging
from typing import Callable, Dict, Union, Optional
from dataclasses import dataclass

from .utils import normalize_name
from .const import ENTITY_NAMING_VERSION

_LOGGER = logging.getLogger(__name__)

# Patterns for entity name formatting - keep unchanged
ENTITY_NAME_PATTERNS: Dict[str, Union[str, Callable[[str], str]]] = {
    "disk": lambda num: f"Array {num}",
    "cache": lambda _: "Pool Cache",
    "parity": lambda _: "Parity",
    "pool": lambda name: f"Pool {name.title()}" if name != "cache" else "Pool Cache",
    "docker": lambda name: f"Docker {name}",
    "vm": lambda name: f"VM {name}",
}

@dataclass
class EntityNaming:
    """Entity naming configuration."""
    domain: str
    hostname: str
    component: str
    naming_version: Optional[int] = None

    def get_entity_id(self, name: str) -> str:
        """Get normalized entity ID."""
        # Cleanup the hostname and normalize the name
        hostname_clean = normalize_name(self.hostname)
        clean_name = normalize_name(name)

        # Always use the new format
        # New format: unraid_hostname_component_name
        unique_id = f"unraid_{hostname_clean}_{self.component}_{clean_name}"

        # Log the generated unique_id for debugging
        _LOGGER.debug(
            "Generated unique_id: %s | hostname: %s | component: %s | clean_name: %s",
            unique_id, hostname_clean, self.component, clean_name
        )
        return unique_id

    def get_entity_name(self, name: str, component_type: str = None) -> str:
        """Get formatted entity name without hostname."""
        if component_type and component_type in ENTITY_NAME_PATTERNS:
            pattern = ENTITY_NAME_PATTERNS[component_type]
            entity_name = pattern(name) if callable(pattern) else pattern
            _LOGGER.debug(
                "Generated entity_name: %s | name: %s | component_type: %s",
                entity_name, name, component_type
            )
            return entity_name

        entity_name = name.title()
        _LOGGER.debug(
            "Generated entity_name: %s | name: %s | component_type: %s",
            entity_name, name, component_type
        )
        return entity_name

    def clean_hostname(self) -> str:
        """Get cleaned hostname."""
        return normalize_name(self.hostname).capitalize()