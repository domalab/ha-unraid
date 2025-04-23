# Entity Development Guide

This guide explains how entities are implemented in the Unraid integration and provides guidance for developing new entities.

## Entity Architecture

The integration uses a factory pattern combined with base classes to create consistent entity implementations across different platforms (sensors, binary sensors, switches, buttons).

### Entity Base Classes

Each entity type has a base class that handles common functionality:

- `UnraidSensorBase`: Base class for sensors
- `UnraidBinarySensorBase`: Base class for binary sensors
- `UnraidSwitchBase`: Base class for switches
- `UnraidButtonBase`: Base class for buttons

These base classes handle:
- Entity registration 
- Default attributes
- Update coordination
- Availability tracking

### Entity Description Classes

Entity descriptions provide metadata for entities:

```python
@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""
    
    key: str = UNDEFINED
    name: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    native_unit_of_measurement: str | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None
    entity_registry_enabled_default: bool = True
    value_fn: Callable[[dict], Any] = lambda _: None
    available_fn: Callable[[dict], bool] | None = None
    # ... other attributes
```

The `value_fn` is particularly important as it's responsible for extracting the entity state from the coordinator data.

## Creating a New Entity

### Creating a New Sensor

1. Choose the appropriate directory (`sensors/`, `diagnostics/`) based on the entity's purpose.

2. Create a new class that inherits from the appropriate base class:

```python
class UnraidMyNewSensor(UnraidSensorBase):
    """My new sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="my_new_sensor",
            name="My New Sensor",
            native_unit_of_measurement="units",
            device_class=SensorDeviceClass.MEASUREMENT,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:my-icon",
            suggested_display_precision=2,
            value_fn=self._get_value,
            available_fn=lambda data: "required_key" in data,
        )
        super().__init__(coordinator, description)
        
    def _get_value(self, data: dict) -> Any:
        """Extract the sensor value from coordinator data."""
        # Complex extraction logic here
        return value
        
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "attribute_1": "value_1",
            "attribute_2": "value_2",
            # ...
        }
```

3. Register the sensor type in the appropriate registry:

```python
# In sensors/registry.py
SensorFactory.register_sensor_type("my_new_sensor", UnraidMyNewSensor)
```

4. Add the sensor creator to the appropriate creator function:

```python
def create_system_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create system sensors."""
    entities = [
        # ...existing entities
        UnraidMyNewSensor(coordinator),
    ]
    return entities
```

### Creating a Switch or Button

Switches and buttons follow a similar pattern but need to implement action methods:

```python
class UnraidMyActionSwitch(UnraidSwitchBase):
    """Switch to control something on Unraid."""

    def __init__(self, coordinator, container_id: str) -> None:
        """Initialize the switch."""
        self._container_id = container_id
        super().__init__(
            coordinator,
            SwitchDescription(
                key=f"container_{container_id}_switch",
                name=f"Container {container_id}",
                icon="mdi:docker",
                value_fn=self._get_state,
                available_fn=self._is_available,
            ),
        )
        
    def _get_state(self, data: dict) -> bool:
        """Get the current switch state."""
        # Logic to determine current state
        return state
        
    def _is_available(self, data: dict) -> bool:
        """Determine if the switch is available."""
        # Availability logic
        return True
        
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.api.some_action(self._container_id)
        await self.coordinator.async_request_refresh()
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.api.some_other_action(self._container_id)
        await self.coordinator.async_request_refresh()
```

## Entity Registration

The integration uses a factory pattern for entity registration:

1. Register entity types with the factory
2. Create factory creator functions that instantiate entities
3. Register the creator functions with the factory

This allows for flexible entity creation based on available data.

## Entity Optimizations

### Update Frequency Control

Entities can control how frequently they're updated by registering with the coordinator:

```python
# Register sensor with priority
coordinator.register_sensor(
    "my_sensor", 
    category=SensorCategory.SYSTEM,
    priority=SensorPriority.HIGH
)

# Request an update for a specific sensor
coordinator.request_sensor_update("my_sensor")
```

### Data Availability Checks

Always implement the `available_fn` to indicate when an entity should be considered available:

```python
available_fn=lambda data: (
    "required_key" in data 
    and data.get("required_key") is not None
)
```

### Value Transformation

Complex value transformations should be moved to separate methods rather than using lambda functions:

```python
# Instead of:
value_fn=lambda data: complex_transformation(data.get("some_value"))

# Use:
value_fn=self._get_value

def _get_value(self, data: dict) -> Any:
    """Get the value with complex transformation."""
    raw_value = data.get("some_value")
    # Complex transformation logic
    return transformed_value
```

## Testing Entities

### Manual Testing

1. Implement the entity
2. Restart Home Assistant
3. Check that the entity appears with the correct state and attributes
4. Test edge cases (e.g., missing data, connection issues)

### Automated Testing

While the integration currently lacks comprehensive automated tests, consider writing tests for:

1. Data extraction logic
2. Edge cases
3. State transitions
4. Action execution

## Common Patterns

### Conditional Entity Creation

Dynamically create entities based on available data:

```python
def create_special_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create sensors only when certain conditions are met."""
    entities = []
    
    # Only create if feature is available
    if coordinator.data.get("special_feature"):
        entities.append(UnraidSpecialSensor(coordinator))
        
    # Create entities for each item in a collection
    for item_id, item_data in coordinator.data.get("items", {}).items():
        entities.append(UnraidItemSensor(coordinator, item_id))
        
    return entities
```

### Entity Naming

Follow consistent naming patterns:

- Class names: `Unraid[Feature][EntityType]` (e.g., `UnraidCPUUsageSensor`)
- Entity IDs: `[domain].[unraid_hostname]_[feature]_[subfeature]` (e.g., `sensor.unraid_cpu_usage`)
- Friendly names: Clear, concise descriptions (e.g., "CPU Usage")

### Attribute Best Practices

- Include a `last_update` timestamp in attributes
- Use consistent units and formatting
- Only include relevant, non-empty attributes
- Consider adding diagnostic attributes where helpful 