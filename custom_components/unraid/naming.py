"""Naming utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Callable, Dict, Union
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

# Patterns for entity name formatting
ENTITY_NAME_PATTERNS: Dict[str, Union[str, Callable[[str], str]]] = {
    "disk": lambda num: f"Array {num}",
    "cache": lambda _: "Pool Cache",
    "parity": lambda _: "Parity",
    "pool": lambda name: f"Pool {name.title()}" if name != "cache" else "Pool Cache",
    "docker": lambda name: f"Docker {name}",
    "vm": lambda name: f"VM {name}",
}

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

@dataclass
class EntityNaming:
    """Entity naming configuration."""
    domain: str
    hostname: str
    component: str

    def get_entity_id(self, name: str) -> str:
        """Get normalized entity ID."""
        clean_name = normalize_name(name)
        entity_id = f"{self.domain}_server_{normalize_name(self.hostname)}_{self.component}_{clean_name}"
        _LOGGER.debug("Generated entity_id: %s | hostname: %s | component: %s | clean_name: %s",
                    entity_id, self.hostname, self.component, clean_name)
        return entity_id

    def get_entity_name(self, name: str, component_type: str = None) -> str:
        """Get formatted entity name."""
        if component_type and component_type in ENTITY_NAME_PATTERNS:
            pattern = ENTITY_NAME_PATTERNS[component_type]
            entity_name = pattern(name) if callable(pattern) else pattern
            _LOGGER.debug("Generated entity_name: %s | hostname: %s | name: %s | component_type: %s",
                        entity_name, self.hostname, name, component_type)
            return entity_name
        entity_name = name.title()
        _LOGGER.debug("Generated entity_name: %s | name: %s | component_type: %s",
                    entity_name, name, component_type)
        return entity_name

    def clean_hostname(self) -> str:
        """Get cleaned hostname."""
        return self.hostname.capitalize()