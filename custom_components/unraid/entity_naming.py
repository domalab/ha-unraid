"""Entity naming utilities for Unraid integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

@dataclass
class EntityNaming:
    """Helper class for entity naming."""
    domain: str
    hostname: str
    component: str
    entity_format: int = 2  # Default to new format (version 2)

    def __init__(self, domain: str, hostname: str, component: str, entity_format: int = 2) -> None:
        """Initialize the entity naming helper."""
        self.domain = domain
        self.hostname = hostname.lower()  # Ensure hostname is lowercase for entity IDs
        self.component = component
        self.entity_format = entity_format

    def get_entity_name(self, entity_id: str, component_type: str = None) -> str:
        """Get the entity name based on the configured format.

        Always uses the format: component_entity_id (without domain or hostname)
        This is used for display names within entities, not for entity IDs.
        """
        component = component_type or self.component
        return f"{component}_{entity_id}"

    def get_entity_id(self, entity_id: str, component_type: str = None) -> str:
        """Get the entity ID based on the configured format.

        Uses format: unraid_hostname_component_name
        Ensures no duplication of hostname or component in the entity_id
        """
        # Clean the entity_id to avoid duplication
        clean_entity_id = entity_id

        # Remove hostname from entity_id if it exists
        hostname_variations = [self.hostname, self.hostname.capitalize(), self.hostname.upper()]
        for variation in hostname_variations:
            if clean_entity_id.startswith(f"{variation}_"):
                clean_entity_id = clean_entity_id[len(variation) + 1:]

        # Format the entity ID
        return f"{self.domain}_{self.hostname}_{clean_entity_id}"

    def clean_hostname(self) -> str:
        """Get a clean version of the hostname for display purposes."""
        return self.hostname.replace('_', ' ').title()
