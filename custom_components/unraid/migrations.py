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
    ent_reg: er.EntityRegistry,
    original_states: Dict[str, Any]
) -> None:
    """Rollback entities to original state.

    Args:
        ent_reg: Entity registry
        original_states: Dictionary of original entity states
    """
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
    # First remove any existing entities with the new ID
    # to prevent duplicates - this is important during reinstallation
    existing_id = ent_reg.async_get_entity_id(
        entity_entry.domain,
        DOMAIN,
        new_unique_id
    )

    if existing_id and existing_id != entity_entry.entity_id:
        _LOGGER.info("Removing duplicate entity %s with unique_id: %s", existing_id, new_unique_id)
        ent_reg.async_remove(existing_id)

    # Now update the entity with the new unique_id
    _LOGGER.debug("Updating entity %s with new unique_id: %s", entity_entry.entity_id, new_unique_id)
    ent_reg.async_update_entity(
        entity_entry.entity_id,
        new_unique_id=new_unique_id
    )

async def async_cleanup_orphaned_entities(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Clean up orphaned entities from previous installations.

    This function removes all entities for the current config entry to ensure
    a clean slate for entity creation.

    Args:
        hass: HomeAssistant instance
        entry: ConfigEntry instance

    Returns:
        Number of entities removed
    """
    ent_reg = er.async_get(hass)
    removed_count = 0

    # Get all entities for this config entry
    all_entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    entity_count = len(all_entities)

    if entity_count > 0:
        _LOGGER.info("Found %s entities for config entry %s", entity_count, entry.entry_id)

        # Remove all entities for THIS config entry
        for entity_entry in all_entities:
            try:
                _LOGGER.debug("Removing entity: %s", entity_entry.entity_id)
                ent_reg.async_remove(entity_entry.entity_id)
                removed_count += 1
            except Exception as err:
                _LOGGER.error("Failed to remove entity %s: %s", entity_entry.entity_id, err)
    else:
        _LOGGER.debug("No entities found for config entry %s - may be a new installation", entry.entry_id)

    if removed_count > 0:
        _LOGGER.info("Removed %s entities during cleanup", removed_count)

    return removed_count


async def async_cleanup_duplicate_entities(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Clean up duplicate entities that may have been created during restarts.

    This addresses GitHub issue #81 where entities are duplicated with _2 suffix.

    Args:
        hass: HomeAssistant instance
        entry: ConfigEntry instance

    Returns:
        Number of duplicate entities removed
    """
    ent_reg = er.async_get(hass)
    removed_count = 0
    hostname = entry.data.get(CONF_HOSTNAME, DEFAULT_NAME).lower()

    # Get all Unraid entities (not just for this config entry)
    all_unraid_entities = [
        entity for entity in ent_reg.entities.values()
        if entity.platform == DOMAIN
    ]

    # Group entities by their base unique_id (without _2, _3, etc. suffixes)
    entity_groups = {}
    for entity in all_unraid_entities:
        # Extract base unique_id by removing numeric suffixes
        base_unique_id = re.sub(r'_\d+$', '', entity.unique_id)
        if base_unique_id not in entity_groups:
            entity_groups[base_unique_id] = []
        entity_groups[base_unique_id].append(entity)

    # Find and remove duplicates
    for base_unique_id, entities in entity_groups.items():
        if len(entities) > 1:
            # Sort by creation time or entity_id to keep the original
            entities.sort(key=lambda e: e.entity_id)
            original = entities[0]
            duplicates = entities[1:]

            _LOGGER.info(
                "Found %d duplicate entities for base unique_id %s, keeping %s",
                len(duplicates),
                base_unique_id,
                original.entity_id
            )

            for duplicate in duplicates:
                try:
                    _LOGGER.info("Removing duplicate entity: %s", duplicate.entity_id)
                    ent_reg.async_remove(duplicate.entity_id)
                    removed_count += 1
                except Exception as err:
                    _LOGGER.error("Failed to remove duplicate entity %s: %s", duplicate.entity_id, err)

    if removed_count > 0:
        _LOGGER.info("Removed %d duplicate entities", removed_count)

    return removed_count


async def async_migrate_with_rollback(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entities with rollback support.

    This function handles migration of entity unique IDs to the new format.
    It includes rollback support in case of failures.

    Args:
        hass: HomeAssistant instance
        entry: ConfigEntry instance

    Returns:
        True if migration was successful, False otherwise
    """
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
        await perform_rollback(ent_reg, original_states)
        return False

# Legacy function migrate_entity_id_format has been removed as it's no longer needed
# All entities now use the new format (unraid_hostname_component_name) by default
