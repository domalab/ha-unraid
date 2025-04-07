"""Migration utilities for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Set, List

from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers import entity_registry as er # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore

from .const import DOMAIN, CONF_HOSTNAME, DEFAULT_NAME, ENTITY_NAMING_VERSION
from .utils import normalize_name

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
    """Remove orphaned entities from previous installation.

    Returns the count of removed entities.
    """
    ent_reg = er.async_get(hass)
    hostname = entry.data.get(CONF_HOSTNAME, DEFAULT_NAME)
    hostname_clean = normalize_name(hostname).lower()
    removed_count = 0

    # First, get ALL registered entities (not just for this config entry)
    all_entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)

    # Create a list to track unique_ids we've seen to avoid duplication
    processed_unique_ids = set()

    # Stage 1: Remove all entities for THIS config entry
    for entity_entry in all_entities:
        try:
            _LOGGER.info("Removing entity for current config entry: %s", entity_entry.entity_id)
            ent_reg.async_remove(entity_entry.entity_id)
            removed_count += 1
        except Exception as err:
            _LOGGER.error("Failed to remove entity %s: %s", entity_entry.entity_id, err)

    # Stage 2: Find ALL entities across ALL config entries with this hostname
    # This will catch orphaned entities from previous installations
    all_entities = ent_reg.entities.values()
    for entity_entry in all_entities:
        try:
            unique_id = entity_entry.unique_id

            # Skip if we've already processed this unique_id
            if unique_id in processed_unique_ids:
                continue

            # Check if this is an Unraid entity with our hostname
            if (DOMAIN in unique_id.lower() and
                hostname_clean in unique_id.lower() and
                "server" in unique_id.lower()):

                _LOGGER.info("Removing orphaned entity: %s, unique_id: %s",
                            entity_entry.entity_id, unique_id)
                ent_reg.async_remove(entity_entry.entity_id)
                removed_count += 1
                processed_unique_ids.add(unique_id)

        except Exception as entity_err:
            _LOGGER.error(
                "Failed to clean up entity %s: %s",
                entity_entry.entity_id,
                entity_err
            )

    if removed_count > 0:
        _LOGGER.info("Removed %s orphaned entities during cleanup", removed_count)

    return removed_count


async def async_migrate_with_rollback(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entities with rollback support."""
    ent_reg = er.async_get(hass)

    # Perform cleanup of orphaned entities first
    # This helps prevent duplicate entities when reinstalling
    await async_cleanup_orphaned_entities(hass, entry)

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

async def migrate_entity_id_format(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entity_format: int = ENTITY_NAMING_VERSION
) -> bool:
    """Migrate entity IDs from old format to new format.

    Old format: unraid_server_hostname_component_name
    New format: unraid_hostname_component_name

    This creates aliases for existing entities to maintain compatibility.
    Only applies to existing installations - new installations will use the new format directly.

    Args:
        hass: HomeAssistant instance
        entry: ConfigEntry instance

    Returns:
        True if migration was successful, False otherwise
    """
    # Always use the new naming format
    _LOGGER.warning("Using entity format version 2")
    _LOGGER.warning("Using new entity naming format, forcing migration")

    # For version 2, we need to remove all old entities to allow new ones to be created
    # This is necessary because the entity_id format has changed

    try:
        ent_reg = er.async_get(hass)
        hostname = entry.data.get(CONF_HOSTNAME, DEFAULT_NAME)
        hostname_clean = normalize_name(hostname).lower()
        migrated_count = 0
        failed_count = 0
        original_states: Dict[str, Dict[str, Any]] = {}
        processed_entities: Set[str] = set()

        # Get all entities for this config entry
        entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        _LOGGER.warning("Found %s entities for config entry %s", len(entities), entry.entry_id)

        # Remove all existing entities for this config entry to allow new ones to be created
        # with the new naming format
        removed_count = 0
        for entity in entities:
            if entity.entity_id.startswith(f"unraid_"):
                _LOGGER.info("Removing entity for current config entry: %s", entity.entity_id)
                ent_reg.async_remove(entity.entity_id)
                removed_count += 1

        if removed_count > 0:
            _LOGGER.info("Removed %s orphaned entities during cleanup", removed_count)

        # First pass: collect all entities that need migration
        entities_to_migrate: List[er.RegistryEntry] = []
        for entity in entities:
            # Check if entity ID matches old format
            if entity.entity_id.startswith(f"unraid_server_{hostname_clean}_"):
                entities_to_migrate.append(entity)

        # If no entities need migration, we're done
        if not entities_to_migrate:
            _LOGGER.info("No entities need migration to new naming format")
            return True

        # Second pass: perform the migration
        for entity in entities_to_migrate:
            # Skip if we've already processed this entity
            if entity.entity_id in processed_entities:
                continue

            # Store original state for rollback if needed
            original_states[entity.entity_id] = {
                "unique_id": entity.unique_id,
                "aliases": entity.aliases,
                "entity_id": entity.entity_id
            }

            # Create new entity ID
            new_entity_id = entity.entity_id.replace(f"unraid_server_{hostname_clean}_", f"unraid_{hostname_clean}_")

            # Add alias for backward compatibility
            aliases = set(entity.aliases) if entity.aliases else set()
            aliases.add(entity.entity_id)

            # Update entity with new entity ID and alias
            try:
                ent_reg.async_update_entity(
                    entity_id=entity.entity_id,
                    new_entity_id=new_entity_id,
                    aliases=aliases
                )
                migrated_count += 1
                processed_entities.add(entity.entity_id)
                _LOGGER.debug(
                    "Migrated entity %s to %s with alias",
                    entity.entity_id,
                    new_entity_id
                )
            except Exception as update_err:
                _LOGGER.warning(
                    "Failed to migrate entity %s: %s",
                    entity.entity_id,
                    update_err
                )
                failed_count += 1

        # Log migration results
        if migrated_count > 0:
            _LOGGER.info(
                "Successfully migrated %s entities to new naming format for %s (failed: %s)",
                migrated_count,
                hostname,
                failed_count
            )

        return True

    except Exception as err:
        _LOGGER.error("Entity ID format migration failed: %s", err)
        return False
