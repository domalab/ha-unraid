"""Sensor factory for Unraid integration."""
from __future__ import annotations

import logging
from typing import Dict, List, Type, Any, Callable, Optional, Set

from homeassistant.helpers.entity import Entity

from ..coordinator import UnraidDataUpdateCoordinator
from .base import UnraidSensorBase
from .const import UnraidSensorEntityDescription

_LOGGER = logging.getLogger(__name__)


class SensorFactory:
    """Factory class for creating Unraid sensors."""

    _sensor_types: Dict[str, Type[UnraidSensorBase]] = {}
    _sensor_creators: Dict[str, Callable[[UnraidDataUpdateCoordinator, Any], List[Entity]]] = {}
    _sensor_groups: Dict[str, Set[str]] = {}

    @classmethod
    def register_sensor_type(cls, sensor_type: str, sensor_class: Type[UnraidSensorBase]) -> None:
        """Register a sensor type with the factory."""
        cls._sensor_types[sensor_type] = sensor_class
        _LOGGER.debug("Registered sensor type: %s", sensor_type)

    @classmethod
    def register_sensor_creator(
        cls, 
        creator_id: str, 
        creator_fn: Callable[[UnraidDataUpdateCoordinator, Any], List[Entity]],
        group: str = "default"
    ) -> None:
        """Register a sensor creator function with the factory."""
        cls._sensor_creators[creator_id] = creator_fn
        
        # Add to group
        if group not in cls._sensor_groups:
            cls._sensor_groups[group] = set()
        cls._sensor_groups[group].add(creator_id)
        
        _LOGGER.debug("Registered sensor creator: %s in group: %s", creator_id, group)

    @classmethod
    def create_sensor(
        cls, 
        sensor_type: str, 
        coordinator: UnraidDataUpdateCoordinator, 
        description: UnraidSensorEntityDescription,
        **kwargs: Any
    ) -> Optional[UnraidSensorBase]:
        """Create a sensor of the specified type."""
        if sensor_type not in cls._sensor_types:
            _LOGGER.error("Unknown sensor type: %s", sensor_type)
            return None

        try:
            sensor_class = cls._sensor_types[sensor_type]
            return sensor_class(coordinator, description, **kwargs)
        except Exception as err:
            _LOGGER.error("Error creating sensor of type %s: %s", sensor_type, err)
            return None

    @classmethod
    def create_sensors_by_group(
        cls, 
        coordinator: UnraidDataUpdateCoordinator,
        group: str = "default"
    ) -> List[Entity]:
        """Create all sensors in a specific group."""
        entities = []
        
        if group not in cls._sensor_groups:
            _LOGGER.warning("Unknown sensor group: %s", group)
            return entities
            
        for creator_id in cls._sensor_groups[group]:
            if creator_id not in cls._sensor_creators:
                _LOGGER.warning("Missing creator function for: %s", creator_id)
                continue
                
            try:
                creator_fn = cls._sensor_creators[creator_id]
                new_entities = creator_fn(coordinator, None)
                if new_entities:
                    entities.extend(new_entities)
                    _LOGGER.debug(
                        "Created %d sensors with creator: %s", 
                        len(new_entities), 
                        creator_id
                    )
            except Exception as err:
                _LOGGER.error("Error creating sensors with creator %s: %s", creator_id, err)
                
        return entities

    @classmethod
    def create_all_sensors(cls, coordinator: UnraidDataUpdateCoordinator) -> List[Entity]:
        """Create all registered sensors."""
        entities = []
        
        for creator_id, creator_fn in cls._sensor_creators.items():
            try:
                new_entities = creator_fn(coordinator, None)
                if new_entities:
                    entities.extend(new_entities)
                    _LOGGER.debug(
                        "Created %d sensors with creator: %s", 
                        len(new_entities), 
                        creator_id
                    )
            except Exception as err:
                _LOGGER.error("Error creating sensors with creator %s: %s", creator_id, err)
                
        return entities
