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

    def __init__(self, host: str, username: str, password: str, port: int = 22) -> None:
        """Initialize the API client."""
        self._connection_manager = ConnectionManager(host, username, password, port)
        self._cache_manager = CacheManager()
        self._log_manager = LogManager()
        self._disk_mapper = DiskMapper()
        self._smart_data_manager = SmartDataManager()
        self._disk_state_manager = DiskStateManager()
```

### Connection Management

All SSH connections are managed through the `ConnectionManager` class, which handles:

- Creating and pooling SSH connections
- Executing commands with timeouts
- Graceful error handling and recovery
- Connection health monitoring
- Circuit breaking for fault tolerance

```python
# Usage example:
result = await api.execute_command("ls -la /mnt/user/")

# With error handling decorator
@with_error_handling(fallback_return=None, max_retries=2)
async def get_some_data(self):
    result = await self.execute_command("some_command")
    return self._parse_result(result)
```

## Core Components

### Cache Manager

The `CacheManager` class provides a centralized caching system:

- Memory-based caching with configurable TTL
- Priority-based cache invalidation
- Size-limited cache to prevent memory issues
- Performance metrics tracking

```python
# Usage example:
value = self._cache_manager.get("system_stats")
if value is None:
    value = await self._fetch_system_stats()
    self._cache_manager.set("system_stats", value, ttl=120, priority=CacheItemPriority.HIGH)
```

### Log Manager

The `LogManager` class provides centralized logging with features:

- Configurable log levels
- Rate limiting to prevent log spam
- Context-aware logging
- Performance impact tracking

### Disk Mapper

The `DiskMapper` class handles the complex task of mapping Unraid disk identifiers:

- Maps between device paths, serial numbers, and Unraid identifiers
- Handles special cases like NVMe drives and USB devices
- Provides consistent disk identification across the integration

## API Modules

### System Operations

The `SystemOperationsMixin` handles retrieving system information:

- CPU usage and temperature
- Memory usage
- System temperatures
- Fan speeds
- Uptime and version information
- Boot drive information

Key methods:

- `get_system_stats()`: Retrieves comprehensive system statistics
- `get_cpu_info()`: Gets CPU-specific information
- `get_memory_info()`: Gets memory usage details
- `get_temperature_data()`: Gets temperature sensor readings
- `get_fan_data()`: Gets fan speed readings
- `get_unraid_version()`: Gets Unraid OS version information

### Disk Operations

The `DiskOperationsMixin` provides functionality for interacting with Unraid's storage system:

- Array status and information
- Individual disk data
- Cache pool information
- SMART data retrieval
- Disk state monitoring

Key methods:

- `get_array_status()`: Gets current array status
- `get_disk_info()`: Retrieves information about individual disks
- `get_smart_data()`: Gets SMART details for health monitoring
- `get_disk_temperatures()`: Gets disk temperature readings
- `get_disk_usage()`: Gets disk usage statistics
- `get_pool_info()`: Gets cache pool information

### Docker Operations

The `DockerOperationsMixin` handles Docker container management:

- Container listing and status
- Start/stop/pause operations
- Container details and statistics
- Container resource usage

Key methods:

- `get_docker_containers()`: Lists all Docker containers
- `start_container()`: Starts a specific container
- `stop_container()`: Stops a specific container
- `restart_container()`: Restarts a specific container
- `pause_container()`: Pauses a specific container
- `unpause_container()`: Unpauses a specific container
- `get_container_logs()`: Gets logs for a specific container

### VM Operations

The `VMOperationsMixin` provides virtual machine management capabilities:

- VM listing and status
- Start/stop/pause operations
- VM configuration details
- VM resource usage

Key methods:

- `get_vms()`: Lists all virtual machines
- `start_vm()`: Starts a specific VM
- `stop_vm()`: Stops a specific VM
- `restart_vm()`: Restarts a specific VM
- `pause_vm()`: Pauses a specific VM
- `resume_vm()`: Resumes a specific VM
- `get_vm_details()`: Gets detailed information for a specific VM

### UPS Operations

The `UPSOperationsMixin` handles UPS (Uninterruptible Power Supply) monitoring:

- UPS status and battery levels
- Power monitoring and consumption
- Runtime estimates
- UPS events and alerts

Key methods:

- `get_ups_info()`: Retrieves UPS status information
- `get_ups_metrics()`: Gets power consumption metrics
- `get_ups_status()`: Gets current UPS status
- `has_ups()`: Checks if a UPS is configured
- `get_ups_power_consumption()`: Gets current power consumption

### User Script Operations

The `UserScriptOperationsMixin` provides functionality for managing user scripts:

- Listing available scripts
- Executing scripts
- Script status monitoring
- Script output retrieval

Key methods:

- `get_user_scripts()`: Lists all available user scripts
- `execute_user_script()`: Runs a specific user script
- `get_script_status()`: Gets the status of a script
- `get_script_output()`: Gets the output of a script execution

### Network Operations

The `NetworkOperationsMixin` provides network interface monitoring:

- Network interface listing
- Bandwidth usage statistics
- Interface status monitoring
- Rate smoothing for bandwidth graphs

Key methods:

- `get_network_interfaces()`: Lists all network interfaces
- `get_network_stats()`: Gets bandwidth statistics
- `get_interface_details()`: Gets detailed information for a specific interface

## Error Handling

The API includes robust error handling mechanisms:

- Specific exception types for different error scenarios
- Automatic retries with exponential backoff
- Circuit breaking to prevent cascading failures
- Detailed logging for troubleshooting
- Fallback values for graceful degradation

The error handling system is implemented through a decorator pattern:

```python
@with_error_handling(fallback_return=None, max_retries=2, retry_delay=1.0)
async def get_some_data(self):
    """Get some data with automatic error handling."""
    result = await self.execute_command("some_command")
    return self._parse_result(result)
```

For manual error handling:

```python
try:
    result = await api.execute_command("some_command")
except CommandTimeoutError:
    # Handle timeout
except CommandError as err:
    # Handle command failure with err.exit_code
except UnraidConnectionError:
    # Handle general connection issues
except UnraidDataError:
    # Handle data parsing issues
```

## Caching System

The integration implements a sophisticated caching system to minimize SSH connections and improve performance:

- Memory-based caching with configurable TTL
- Prioritized cache management
- Automatic cache invalidation
- Size-limited cache to prevent memory issues
- Performance metrics tracking

The `CacheManager` class provides a centralized interface for all caching operations:

```python
# Cache configuration
self._cache_ttls = {
    # Static or rarely changing data
    "disk_mapping": 3600,  # 1 hour
    "disk_info": 1800,     # 30 minutes

    # Semi-dynamic data
    "system_stats": 120,   # 2 minutes

    # Highly dynamic data
    "cpu_info": 30,        # 30 seconds
}

# Cache usage
value = self._cache_manager.get("system_stats")
if value is None:
    value = await self._fetch_system_stats()
    self._cache_manager.set(
        "system_stats",
        value,
        ttl=120,
        priority=CacheItemPriority.HIGH
    )
```

## API Extension

When extending the API with new functionality:

1. Determine if the feature fits in an existing mixin or requires a new one
2. Implement command execution and parsing
3. Add appropriate error handling using the `with_error_handling` decorator
4. Implement caching where appropriate
5. Add logging with appropriate levels
6. Update the coordinator to use the new API functionality
7. Register any new sensors with the `SensorPriorityManager`

Example of adding a new API method:

```python
class MyNewOperationsMixin:
    """Mixin for new feature operations."""

    def __init__(self):
        """Initialize the mixin."""
        self._some_state = {}

    @with_error_handling(fallback_return=None, max_retries=2)
    async def get_new_feature_data(self):
        """Get data for the new feature."""
        # Check cache first
        cache_key = "new_feature_data"
        cached_data = self._cache_manager.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Log the API request
        self._log_manager.log_api_request("get_new_feature_data")

        # Execute command
        result = await self.execute_command("my_command")

        # Parse result
        data = self._parse_command_output(result.stdout)

        # Cache the result
        self._cache_manager.set(
            cache_key,
            data,
            ttl=300,  # 5 minutes
            priority=CacheItemPriority.MEDIUM
        )

        return data

    def _parse_command_output(self, output):
        """Parse command output."""
        try:
            # Parsing logic
            return parsed_data
        except Exception as err:
            raise UnraidDataError(f"Failed to parse output: {err}") from err
```
