"""Migration utilities for Unraid integration."""
from __future__ import annotations

import logging
import re

from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers import entity_registry as er # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore

from .const import DOMAIN, CONF_HOSTNAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

def clean_entity_id(entity_id: str, hostname: str) -> str:
    """Clean entity ID by removing duplicate hostname occurrences.
    
    Args:
        entity_id: Original entity ID
        hostname: Current hostname
        
    Returns:
        Cleaned entity ID without hostname duplicates
    """
    # Convert everything to lowercase for comparison
    hostname_lower = hostname.lower()
    
    # Split into parts
    parts = entity_id.split('_')
    
    # Remove any parts that are exactly the hostname
    cleaned_parts = [part for part in parts if part != hostname_lower]
    
    # Reconstruct the ID
    return '_'.join(cleaned_parts)

async def async_migrate_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate entities to use hostname-based naming."""
    ent_reg = er.async_get(hass)
    hostname = entry.data.get(CONF_HOSTNAME, DEFAULT_NAME).capitalize()

    # Find all entities for this config entry
    entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    
    migrated_count = 0
    
    for entity_entry in entity_entries:
        try:
            # Check if entity needs migration (has IP-based naming or duplicate hostname)
            ip_pattern = r'unraid_server_\d+_\d+_\d+_\d+_'
            needs_migration = bool(re.search(ip_pattern, entity_entry.unique_id))
            
            # Also check for duplicate hostname
            hostname_count = entity_entry.unique_id.lower().count(hostname.lower())
            needs_migration = needs_migration or hostname_count > 1
            
            if needs_migration:
                # Clean the entity type by removing any hostname duplicates
                cleaned_id = clean_entity_id(entity_entry.unique_id, hostname)
                # Ensure we have the correct prefix
                if not cleaned_id.startswith("unraid_server_"):
                    cleaned_id = f"unraid_server_{cleaned_id}"
                # Create new unique_id with single hostname instance
                new_unique_id = f"unraid_server_{hostname}_{cleaned_id.split('_')[-1]}"
                
                if new_unique_id != entity_entry.unique_id:
                    _LOGGER.debug(
                        "Migrating entity %s to new unique_id %s",
                        entity_entry.entity_id,
                        new_unique_id
                    )
                    
                    # Check if target ID already exists
                    existing = ent_reg.async_get_entity_id(
                        entity_entry.domain,
                        DOMAIN,
                        new_unique_id
                    )
                    
                    if existing and existing != entity_entry.entity_id:
                        _LOGGER.debug(
                            "Removing existing entity %s before migration",
                            existing
                        )
                        ent_reg.async_remove(existing)

                    # Update entity with new unique_id
                    ent_reg.async_update_entity(
                        entity_entry.entity_id,
                        new_unique_id=new_unique_id
                    )
                    migrated_count += 1
                    
        except Exception as err:
            _LOGGER.error(
                "Error migrating entity %s: %s",
                entity_entry.entity_id,
                err
            )
            continue

    if migrated_count > 0:
        _LOGGER.info(
            "Successfully migrated %s entities to use hostname %s",
            migrated_count,
            hostname
        )