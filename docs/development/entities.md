# Entity Development Guide

This guide explains how entities are implemented in the Unraid integration and provides guidance for developing new entities.

## Entity Architecture

The integration uses a factory pattern combined with base classes to create consistent entity implementations across different platforms (sensors, binary sensors, switches, buttons).

### Entity Base Classes

Each entity type has a base class that handles common functionality:

- `UnraidSensorBase`: Base class for sensors (in `sensors/base.py`)
- `UnraidBinarySensorBase`: Base class for binary sensors (in `diagnostics/base.py`)
- `UnraidSwitchBase`: Base class for switches (in `switch.py`)
- `UnraidButtonBase`: Base class for buttons (in `button.py`)

These base classes handle:

- Entity registration and unique ID generation
- Default attributes and properties
- Update coordination with the data coordinator
- Availability tracking and state management
- Device info and entity category assignment

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
    entity_category: EntityCategory | None = None
    has_entity_name: bool = True
    value_fn: Callable[[dict], Any] = lambda _: None
    available_fn: Callable[[dict], bool] | None = None
    translation_key: str | None = None
    translation_placeholders: dict[str, str] | None = None
```

The `value_fn` is particularly important as it's responsible for extracting the entity state from the coordinator data.

## Creating a New Entity

### Creating a New Sensor

1. Choose the appropriate directory (`sensors/`, `diagnostics/`) based on the entity's purpose.

2. Create a new class that inherits from the appropriate base class and any needed mixins:

```python
class UnraidMyNewSensor(UnraidSensorBase, ValueValidationMixin):
    """My new sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize any mixins first
        ValueValidationMixin.__init__(self)

        # Create entity description
        description = UnraidSensorEntityDescription(
            key="my_new_sensor",
            name="My New Sensor",
            native_unit_of_measurement="units",
            device_class=SensorDeviceClass.MEASUREMENT,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:my-icon",
            suggested_display_precision=2,
            entity_category=EntityCategory.DIAGNOSTIC,
            has_entity_name=True,
            value_fn=self._get_value,
            available_fn=lambda data: "required_key" in data.get("system_stats", {}),
        )

        # Initialize the base class
        super().__init__(coordinator, description)

        # Set up device info using the EntityNaming helper
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="system"
        )

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_system")},
            "name": f"Unraid System ({naming.clean_hostname()})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
            "sw_version": coordinator.data.get("system_stats", {}).get("version"),
            "via_device": (DOMAIN, coordinator.entry.entry_id),
        }

    def _get_value(self, data: dict) -> Any:
        """Extract the sensor value from coordinator data."""
        # Get data from the appropriate section
        system_data = data.get("system_stats", {})

        # Extract and validate the value
        raw_value = system_data.get("my_metric")
        return self.validate_value(raw_value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        system_data = self.coordinator.data.get("system_stats", {})

        return {
            "attribute_1": system_data.get("attribute_1"),
            "attribute_2": system_data.get("attribute_2"),
            "last_update": dt_util.now().isoformat(),
        }
```

3\. Register the sensor type in the appropriate registry:

```python
# In sensors/registry.py
def register_system_sensors() -> None:
    """Register system sensors with the factory."""
    from .system import (
        # ...existing imports
        UnraidMyNewSensor,
    )

    # Register sensor types
    SensorFactory.register_sensor_type("my_new_sensor", UnraidMyNewSensor)
```

4\. Add the sensor creator to the appropriate creator function:

```python
def create_system_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create system sensors."""
    from .system import (
        # ...existing imports
        UnraidMyNewSensor,
    )

    entities = [
        # ...existing entities
        UnraidMyNewSensor(coordinator),
    ]

    return entities
```

### Creating a Switch or Button

Switches and buttons follow a similar pattern but need to implement action methods:

```python
class UnraidContainerSwitch(UnraidSwitchBase):
    """Switch to control a Docker container on Unraid."""

    def __init__(self, coordinator, container_id: str, container_name: str) -> None:
        """Initialize the switch."""
        self._container_id = container_id
        self._container_name = container_name

        # Create entity description
        description = SwitchEntityDescription(
            key=f"container_{container_id}_switch",
            name=f"{container_name}",
            icon="mdi:docker",
            entity_category=EntityCategory.CONFIG,
        )

        # Initialize the base class
        super().__init__(coordinator, description)

        # Set up device info using the EntityNaming helper
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_docker")},
            "name": f"Unraid Docker ({naming.clean_hostname()})",
            "manufacturer": "Docker",
            "model": "Container Engine",
            "via_device": (DOMAIN, coordinator.entry.entry_id),
        }

        # Set unique ID
        self._attr_unique_id = f"{coordinator.entry.entry_id}_docker_{container_id}_switch"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        containers = self.coordinator.data.get("docker_containers", {})
        container = next((c for c in containers if c.get("id") == self._container_id), None)

        if not container:
            return False

        return container.get("state") == "running"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        containers = self.coordinator.data.get("docker_containers", {})
        return any(c.get("id") == self._container_id for c in containers)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (start the container)."""
        await self.coordinator.api.start_container(self._container_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (stop the container)."""
        await self.coordinator.api.stop_container(self._container_id)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        containers = self.coordinator.data.get("docker_containers", {})
        container = next((c for c in containers if c.get("id") == self._container_id), {})

        return {
            "container_id": self._container_id,
            "image": container.get("image"),
            "status": container.get("status"),
            "last_update": dt_util.now().isoformat(),
        }
```

## Entity Registration

The integration uses a factory pattern for entity registration:

1. Register entity types with the factory
2. Create factory creator functions that instantiate entities
3. Register the creator functions with the factory

This allows for flexible entity creation based on available data.

## Entity Optimizations

### Update Frequency Control

Entities can control how frequently they're updated by registering with the coordinator's `SensorPriorityManager`:

```python
# Register sensor with priority
coordinator.sensor_priority_manager.register_sensor(
    "my_sensor",
    category=SensorCategory.SYSTEM,
    priority=SensorPriority.HIGH
)

# Request an update for a specific sensor
coordinator.sensor_priority_manager.request_sensor_update("my_sensor")

# Check if a sensor should be updated based on its priority
should_update = coordinator.sensor_priority_manager.should_update_sensor(
    "my_sensor",
    current_time=dt_util.now()
)
```

The `SensorPriorityManager` tracks update frequencies based on priority levels:

```python
class SensorPriority(Enum):
    """Priority levels for sensors."""

    CRITICAL = 1  # Update every cycle
    HIGH = 2      # Update frequently
    MEDIUM = 3    # Update at medium frequency
    LOW = 4       # Update infrequently
    BACKGROUND = 5  # Update only when system is idle
```

### Data Availability Checks

Always implement the `available_fn` in the entity description or override the `available` property to indicate when an entity should be considered available:

```python
# In entity description
available_fn=lambda data: (
    "system_stats" in data
    and data.get("system_stats", {}).get("required_key") is not None
)

# Or as a property
@property
def available(self) -> bool:
    """Return True if entity is available."""
    system_data = self.coordinator.data.get("system_stats", {})
    return (
        system_data.get("required_key") is not None
        and self.coordinator.last_update_success
    )
```

### Value Transformation

Complex value transformations should be moved to separate methods rather than using lambda functions, and consider using mixins for common transformations:

```python
# Instead of:
value_fn=lambda data: complex_transformation(data.get("system_stats", {}).get("some_value"))

# Use a method:
value_fn=self._get_value

def _get_value(self, data: dict) -> Any:
    """Get the value with complex transformation."""
    system_data = data.get("system_stats", {})
    raw_value = system_data.get("some_value")
    # Complex transformation logic
    return transformed_value

# Or use a mixin:
class ValueValidationMixin:
    """Mixin for value validation and formatting."""

    def validate_value(self, value: Any) -> Any:
        """Validate and format a value."""
        if value is None:
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def format_bytes(self, bytes_value: Any) -> float:
        """Format bytes to GB."""
        if bytes_value is None:
            return None

        try:
            return round(float(bytes_value) / (1024 ** 3), 2)
        except (ValueError, TypeError):
            return None
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
def create_storage_sensors(coordinator: UnraidDataUpdateCoordinator, _: Any) -> List[Entity]:
    """Create storage sensors based on available disks."""
    from .storage import (
        UnraidArraySensor,
        UnraidDiskSensor,
        UnraidPoolSensor,
    )
    from ..helpers import is_solid_state_drive

    entities = []

    # Add array sensor
    entities.append(UnraidArraySensor(coordinator))

    # Get disk data
    disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])

    # Define ignored mounts and filesystem types
    ignored_mounts = {"disks", "remotes", "addons", "rootshare", "user/0", "dev/shm"}
    ignored_fs_types = {"autofs", "overlay", "tmpfs"}

    # Add disk sensors for each disk
    for disk in disk_data:
        # Skip disks with ignored mounts or filesystem types
        mount = disk.get("mount", "")
        fs_type = disk.get("fstype")

        if (
            any(ignored in mount for ignored in ignored_mounts)
            or fs_type in ignored_fs_types
        ):
            continue

        # Create appropriate sensor based on disk type
        if is_solid_state_drive(disk):
            entities.append(UnraidPoolSensor(coordinator, disk.get("name")))
        else:
            entities.append(UnraidDiskSensor(coordinator, disk.get("name")))

    return entities
```

### Entity Naming

Follow consistent naming patterns using the `EntityNaming` helper class:

```python
from ..entity_naming import EntityNaming

# Create naming helper
naming = EntityNaming(
    domain=DOMAIN,
    hostname=coordinator.hostname,
    component="system"
)

# Use for device info
self._attr_device_info = {
    "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_system")},
    "name": f"Unraid System ({naming.clean_hostname()})",
    # ...
}

# Use for unique IDs
self._attr_unique_id = f"{coordinator.entry.entry_id}_system_cpu_usage"
```

Follow these conventions:

- Class names: `Unraid[Feature][EntityType]` (e.g., `UnraidCPUUsageSensor`)
- Entity IDs: `[domain].[unraid_hostname]_[feature]_[subfeature]` (e.g., `sensor.unraid_cpu_usage`)
- Friendly names: Clear, concise descriptions (e.g., "CPU Usage")
- Device names: `Unraid [Component] ([hostname])` (e.g., "Unraid System (tower)")

### Attribute Best Practices

- Include a `last_update` timestamp in attributes using `dt_util.now().isoformat()`
- Use consistent units and formatting (e.g., always use GB instead of mixing GB and MB)
- Only include relevant, non-empty attributes (filter out None values)
- Consider adding diagnostic attributes where helpful
- Group related attributes in a logical order
- Use the `UnraidDiagnosticMixin` for entities that should provide diagnostic data

```python
from ..helpers import UnraidDiagnosticMixin

class UnraidSystemSensor(UnraidSensorBase, UnraidDiagnosticMixin):
    """System sensor with diagnostic capabilities."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)
        UnraidDiagnosticMixin.__init__(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self.coordinator.data.get("system_stats", {})

        # Filter out None values
        attributes = {}
        for key, value in data.items():
            if value is not None:
                attributes[key] = value

        # Add timestamp
        attributes["last_update"] = dt_util.now().isoformat()

        return attributes

    async def async_get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostics for this entity."""
        return {
            "state": self.state,
            "attributes": self.extra_state_attributes,
            "raw_data": self.coordinator.data.get("system_stats"),
        }
```
