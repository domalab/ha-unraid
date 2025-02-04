"""Migration utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any

from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers import entity_registry as er # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore

from .const import DOMAIN, CONF_HOSTNAME, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

def clean_and_validate_unique_id(unique_id: str, hostname: str) -> str:
    """Clean and validate unique ID format.
    
    Args:
        unique_id: Original unique ID
        hostname: Server hostname
        
    Returns:
        Cleaned and validated unique ID
    """
    hostname_lower = hostname.lower()
    parts = unique_id.split('_')
    
    # Remove hostname duplicates while preserving structure
    cleaned_parts = [part for part in parts if part.lower() != hostname_lower]
    
    # Ensure proper structure
    if not cleaned_parts[0:2] == ['unraid', 'server']:
        cleaned_parts = ['unraid', 'server'] + cleaned_parts
    
    # Insert hostname after unraid_server prefix
    if len(cleaned_parts) >= 2:
        cleaned_parts.insert(2, hostname_lower)
    
    return '_'.join(cleaned_parts)

async def perform_rollback(
    hass: HomeAssistant,
    ent_reg: er.EntityRegistry,
    original_states: Dict[str, Any]
) -> None:
    """Rollback entities to original state."""
    for entity_id, original in original_states.items():
        try:
            ent_reg.async_update_entity(
                entity_id,
                new_unique_id=original["unique_id"],
                new_name=original["name"]
            )
        except Exception as err:
            _LOGGER.error("Rollback failed for %s: %s", entity_id, err)

async def update_entity_safely(
    ent_reg: er.EntityRegistry,
    entity_entry: er.RegistryEntry,
    new_unique_id: str
) -> None:
    """Safely update entity with new unique ID."""
    # Check for existing entity with new ID
    existing = ent_reg.async_get_entity_id(
        entity_entry.domain,
        DOMAIN,
        new_unique_id
    )
    
    if existing and existing != entity_entry.entity_id:
        _LOGGER.debug("Removing duplicate entity %s", existing)
        ent_reg.async_remove(existing)
    
    ent_reg.async_update_entity(
        entity_entry.entity_id,
        new_unique_id=new_unique_id
    )

async def async_migrate_with_rollback(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entities with rollback support."""
    ent_reg = er.async_get(hass)
    
    # Store original states for rollback
    original_states = {
        entity.entity_id: {
            "unique_id": entity.unique_id,
            "name": entity.name
        }
        for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    }
    
    try:
        hostname = entry.data.get(CONF_HOSTNAME, DEFAULT_NAME)
        migrated_count = 0
        
        for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            try:
                # Check if migration is needed (has IP-based naming or duplicate hostname)
                ip_pattern = r'unraid_server_\d+_\d+_\d+_\d+_'
                needs_migration = bool(re.search(ip_pattern, entity_entry.unique_id))
                
                hostname_count = entity_entry.unique_id.lower().count(hostname.lower())
                needs_migration = needs_migration or hostname_count > 1
                
                if needs_migration:
                    new_unique_id = clean_and_validate_unique_id(
                        entity_entry.unique_id,
                        hostname
                    )
                    
                    if new_unique_id != entity_entry.unique_id:
                        await update_entity_safely(ent_reg, entity_entry, new_unique_id)
                        migrated_count += 1
                    
            except Exception as entity_err:
                _LOGGER.error(
                    "Failed to migrate entity %s: %s",
                    entity_entry.entity_id,
                    entity_err
                )
                continue
                
        if migrated_count:
            _LOGGER.info(
                "Successfully migrated %s entities for %s",
                migrated_count,
                hostname
            )
        
        return True
        
    except Exception as err:
        _LOGGER.error("Migration failed, rolling back: %s", err)
        await perform_rollback(hass, ent_reg, original_states)
        return False
