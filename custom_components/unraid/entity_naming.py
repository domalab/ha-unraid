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
        hostname = self.hostname.lower()
        entity_id_lower = clean_entity_id.lower()

        # Check if entity_id starts with hostname (case insensitive)
        if entity_id_lower.startswith(f"{hostname}_"):
            # Get the part after the hostname_
            clean_entity_id = clean_entity_id[len(hostname) + 1:]

        # Remove 'unraid_' prefix if it exists
        if clean_entity_id.lower().startswith("unraid_"):
            clean_entity_id = clean_entity_id[7:]

        # Format the entity ID - include hostname to avoid conflicts with multiple servers
        return f"{self.domain}_{hostname}_{clean_entity_id}"

    def clean_hostname(self) -> str:
        """Get a clean version of the hostname for display purposes."""
        return self.hostname.replace('_', ' ').title()
