# Developer Guide

This guide is intended for developers who want to contribute to the Unraid Integration for Home Assistant. It provides an overview of the architecture, key components, and development patterns used in the codebase.

## Architecture Overview

The Unraid integration follows the Home Assistant integration architecture with a focus on modularity and performance. It's structured around a central update coordinator that efficiently fetches and manages data from an Unraid server via SSH.

![Architecture Diagram](../assets/images/architecture.png)

### Key Components

1. **Data Update Coordinator**: Central component managing state, data fetching, and updates
2. **API Client**: Modular API implementation using mixins for different functionality areas
3. **Connection Manager**: Manages SSH connections with features like connection pooling and circuit breaking
4. **Entity Framework**: Base classes and factories for creating different entity types
5. **Caching System**: Optimizes performance by caching data based on update frequency needs

## Code Structure

```
custom_components/unraid/
├── api/                    # API implementation modules
│   ├── connection_manager.py  # SSH connection management and pooling
│   ├── cache_manager.py    # Data caching functionality
│   ├── system_operations.py   # System-related API operations
│   ├── disk_operations.py  # Disk-related API operations  
│   ├── docker_operations.py   # Docker container operations
│   ├── vm_operations.py    # Virtual machine operations
│   └── ...                 # Other API modules
├── sensors/                # Sensor implementations
│   ├── system.py           # System-related sensors
│   ├── storage.py          # Storage-related sensors
│   └── ...                 # Other sensor modules
├── diagnostics/            # Diagnostic capabilities
├── coordinator.py          # Main data update coordinator
├── __init__.py             # Integration setup
├── config_flow.py          # Configuration flow
├── sensor.py               # Sensor platform registration
├── binary_sensor.py        # Binary sensor platform
├── switch.py               # Switch platform
├── button.py               # Button platform
├── services.py             # Service definitions
└── ...                     # Other components
```

## Core Concepts

### Data Coordinator

The `UnraidDataUpdateCoordinator` (in `coordinator.py`) is the core of the integration:

- Manages the data refresh cycle for all entities
- Implements smart update scheduling based on data type
- Handles caching and optimizes SSH commands
- Processes and normalizes data for entity consumption
- Contains recovery mechanisms for connection issues

```python
class UnraidDataUpdateCoordinator(DataUpdateCoordinator[UnraidDataDict]):
    """Class to manage fetching Unraid data."""
    
    # Initialization with different update intervals
    def __init__(self, hass: HomeAssistant, api: UnraidAPI, entry: ConfigEntry) -> None:
        # ...
        
    # Main data update method
    async def _async_update_data(self) -> Dict[str, Any]:
        # ...
```

### API Client Architecture

The API client uses a modular approach with mixins for different functionality areas:

```python
class UnraidAPI(
    NetworkOperationsMixin,
    DiskOperationsMixin,
    DockerOperationsMixin,
    VMOperationsMixin,
    SystemOperationsMixin,
    UPSOperationsMixin,
    UserScriptOperationsMixin
):
    """API client for interacting with Unraid servers."""
    # ...
```

Each mixin provides specialized functionality for a particular domain (e.g., Docker containers, virtual machines). This modular approach:

- Makes the codebase easier to maintain and extend
- Allows focused testing of individual components
- Creates clear separation of concerns

### Connection Management

The integration employs a sophisticated connection management system (`connection_manager.py`) that:

- Maintains a pool of SSH connections for performance
- Implements circuit breaking to prevent cascading failures
- Handles retry logic and exponential backoff
- Provides health monitoring for connections

### Entity Implementation

Entities are implemented using a factory pattern with base classes for each entity type:

1. Create entity base classes (e.g., `UnraidSensorBase`)
2. Implement specific entities (e.g., `UnraidCPUUsageSensor`)
3. Register entities with the factory
4. Factory creates all entities during platform setup

This pattern allows for:
- Consistent entity behavior and attributes
- Easy addition of new entity types
- Centralized entity creation and registration

Example sensor implementation:

```python
class UnraidCPUUsageSensor(UnraidSensorBase):
    """CPU usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="cpu_usage",
            name="CPU Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:cpu-64-bit",
            suggested_display_precision=1,
            value_fn=lambda data: data.get("system_stats", {}).get("cpu_usage"),
            # ...
        )
        super().__init__(coordinator, description)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        # ...
```

## Development Workflow

### Setting Up Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/domalab/ha-unraid.git
   cd ha-unraid
   ```

2. Create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements_dev.txt
   ```

4. Set up a development instance of Home Assistant or use the provided development container configuration.

### Development Best Practices

#### Code Style and Standards

The project follows Home Assistant's coding standards:

- Type hints for all functions and methods
- Comprehensive docstrings
- Follow PEP 8 for code style
- Use meaningful variable and function names

#### Testing New Features

1. **Unit Testing**: Create or update unit tests for your changes
2. **Integration Testing**: Test your changes with a real Unraid server
3. **Documentation**: Update documentation to reflect your changes

#### Performance Considerations

The integration is designed with performance in mind:

- Use the caching system appropriately:
  ```python
  # Register sensor with the appropriate priority
  coordinator.register_sensor(
      "my_sensor", 
      category=SensorCategory.SYSTEM,
      priority=SensorPriority.HIGH
  )
  ```

- Minimize SSH commands by batching where possible
- Be mindful of update frequencies for different data types

### Adding New Features

#### Adding a New Sensor

1. Create a new sensor class in the appropriate sensors module:
   ```python
   class MyNewSensor(UnraidSensorBase):
       """My new sensor for Unraid."""

       def __init__(self, coordinator) -> None:
           """Initialize the sensor."""
           description = UnraidSensorEntityDescription(
               key="my_sensor",
               name="My Sensor",
               # ... other attributes
               value_fn=lambda data: data.get("path", {}).get("to", {}).get("value")
           )
           super().__init__(coordinator, description)
   ```

2. Register the sensor in the appropriate registry:
   ```python
   # In sensors/registry.py
   SensorFactory.register_sensor_type("my_sensor", MyNewSensor)
   ```

3. Ensure the data needed for the sensor is fetched in the coordinator

#### Adding a New API Feature

1. Identify which mixin should contain the functionality (or create a new one)
2. Implement the feature in the appropriate mixin
3. Add tests for the new functionality
4. Update the coordinator to fetch and process the new data if needed

## Common Challenges and Solutions

### SSH Connection Issues

The integration includes robust connection handling via the `ConnectionManager`, but SSH connections can still be challenging. Common issues include:

- Authentication failures
- Network timeouts
- Command execution timeouts

Solution approaches:
- Check connection settings (host, username, password, port)
- Ensure the Unraid server allows SSH connections
- Review logs for specific error messages
- Consider increasing timeout values for slower connections

### Data Parsing

The integration parses command output from the Unraid server, which can vary between Unraid versions. When adding or modifying parsing logic:

- Make parsing robust to different output formats
- Include version checks where needed
- Add logging for parse failures
- Create tests with sample outputs

### Memory Management

The integration implements caching to improve performance. To prevent memory issues:

- Use the CacheManager with appropriate cache invalidation
- Monitor memory usage during development
- Be careful with large data structures
- Consider paginating large data sets

## Contributing Guidelines

When contributing to the Unraid integration:

1. Fork the repository and create a feature branch
2. Make your changes following the coding standards
3. Add or update tests for your changes
4. Update documentation as needed
5. Create a pull request with a clear description of your changes

### Pull Request Checklist

- [ ] Code follows style guidelines
- [ ] Tests cover new/changed functionality
- [ ] Documentation updated
- [ ] Changelog entry added for significant changes

## Getting Help

If you need assistance with development:

- Open an issue on GitHub with the "question" label
- Review existing issues and discussions
- Check the Home Assistant developer documentation

By following this guide, you should be able to understand and contribute to the Unraid integration effectively. Happy coding! 