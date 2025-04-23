# API Documentation

This document describes the key API components of the Unraid integration for Home Assistant.

## API Client Structure

The Unraid API client is designed using a mixin-based architecture, which allows for modular organization of functionality. Each mixin handles a specific domain of operations, such as disk operations, Docker containers, or virtual machines.

### Base API Client

The main `UnraidAPI` class combines all the specialized mixins:

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

### Connection Management

All SSH connections are managed through the `ConnectionManager` class, which handles:

- Creating and pooling SSH connections
- Executing commands with timeouts
- Graceful error handling and recovery
- Connection health monitoring

```python
# Usage example:
result = await api.execute_command("ls -la /mnt/user/")
```

## API Modules

### System Operations

The `SystemOperationsMixin` handles retrieving system information:

- CPU usage and temperature
- Memory usage
- System temperatures
- Fan speeds
- Uptime and version information

Key methods:
- `get_system_stats()`: Retrieves comprehensive system statistics
- `get_cpu_info()`: Gets CPU-specific information
- `get_memory_info()`: Gets memory usage details

### Disk Operations

The `DiskOperationsMixin` provides functionality for interacting with Unraid's storage system:

- Array status and information
- Individual disk data
- Cache pool information
- SMART data retrieval

Key methods:
- `get_array_status()`: Gets current array status
- `get_disk_info()`: Retrieves information about individual disks
- `get_smart_data()`: Gets SMART details for health monitoring

### Docker Operations

The `DockerOperationsMixin` handles Docker container management:

- Container listing and status
- Start/stop/pause operations
- Container details and statistics

Key methods:
- `get_docker_containers()`: Lists all Docker containers
- `start_container()`: Starts a specific container
- `stop_container()`: Stops a specific container

### VM Operations

The `VMOperationsMixin` provides virtual machine management capabilities:

- VM listing and status
- Start/stop/pause operations
- VM configuration details

Key methods:
- `get_vms()`: Lists all virtual machines
- `start_vm()`: Starts a specific VM
- `stop_vm()`: Stops a specific VM

### UPS Operations

The `UPSOperationsMixin` handles UPS (Uninterruptible Power Supply) monitoring:

- UPS status and battery levels
- Power monitoring
- Runtime estimates

Key methods:
- `get_ups_info()`: Retrieves UPS status information

### User Script Operations

The `UserScriptOperationsMixin` provides functionality for managing user scripts:

- Listing available scripts
- Executing scripts
- Script status monitoring

Key methods:
- `get_user_scripts()`: Lists all available user scripts
- `execute_user_script()`: Runs a specific user script

## Error Handling

The API includes robust error handling mechanisms:

- Specific exception types for different error scenarios
- Automatic retries with exponential backoff
- Circuit breaking to prevent cascading failures
- Detailed logging for troubleshooting

Example error handling:

```python
try:
    result = await api.execute_command("some_command")
except CommandTimeoutError:
    # Handle timeout
except CommandError as err:
    # Handle command failure with err.exit_code
except UnraidConnectionError:
    # Handle general connection issues
```

## Caching System

The integration implements a sophisticated caching system to minimize SSH connections and improve performance:

- Memory-based caching with configurable TTL
- Prioritized cache management
- Automatic cache invalidation

Example cache configuration:

```python
self._cache_ttls = {
    # Static or rarely changing data
    "disk_mapping": 3600,  # 1 hour
    "disk_info": 1800,     # 30 minutes
    
    # Semi-dynamic data
    "system_stats": 120,   # 2 minutes
    
    # Highly dynamic data
    "cpu_info": 30,        # 30 seconds
}
```

## API Extension

When extending the API with new functionality:

1. Determine if the feature fits in an existing mixin or requires a new one
2. Implement command execution and parsing
3. Add appropriate error handling
4. Implement caching where appropriate
5. Update the coordinator to use the new API functionality

Example of adding a new API method:

```python
class MyNewOperationsMixin:
    """Mixin for new feature operations."""
    
    def __init__(self):
        """Initialize the mixin."""
        self._some_state = {}
    
    async def get_new_feature_data(self):
        """Get data for the new feature."""
        try:
            result = await self.execute_command("my_command")
            # Parse result
            data = self._parse_command_output(result.stdout)
            return data
        except Exception as err:
            _LOGGER.error("Failed to get new feature data: %s", err)
            raise
            
    def _parse_command_output(self, output):
        """Parse command output."""
        # Parsing logic
        return parsed_data
``` 