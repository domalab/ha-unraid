# Changelog

## 2025-04-05: Epic 3 - Performance Optimization

### Features
- Implemented selective data caching with `CacheManager` to reduce API calls
- Added sensor prioritization to optimize update frequency based on importance
- Implemented memory monitoring and automatic cleanup to prevent leaks
- Added intelligent logging with filters and rate limiting
- Created new optimization services for runtime tuning:
  - `force_update`: Force an immediate refresh of data
  - `get_optimization_stats`: Get detailed performance metrics
  - `clear_cache`: Manually clear cached data
  - `force_sensor_update`: Trigger update for specific sensors

### Bug Fixes
- Fixed critical issue with method object `len()` operations
- Improved type checking and defensive programming throughout the codebase
- Added proper error handling for network interfaces and UPS data
- Fixed API method access by using proper public interfaces

### Technical Details
- Added `cache_manager.py` with prioritized caching system
- Implemented `sensor_priority.py` for sensor update scheduling
- Added memory usage monitoring in coordinator
- Created `log_filter.py` for intelligent log management
- Updated coordinator to implement cache and priority-based updates
- Added optimization services in `services.py` and `services.yaml`

### Success Criteria Met
- ✅ Reduced API calls through intelligent caching
- ✅ Implemented priority-based updates for efficiency
- ✅ Added memory monitoring and cleanup
- ✅ Provided services for runtime optimization
- ✅ Maintained all functionality while reducing resource usage

## 2025-04-05: Epic 1 - Connection Management Optimization

### Features
- Implemented connection pooling with a maximum of 3 concurrent connections
- Added connection lifecycle management with state machine
- Implemented connection health metrics collection
- Added exponential backoff for connection retries (initial: 1s, max: 300s)
- Implemented circuit breaker pattern to prevent cascading failures
- Added SSH logging suppression to reduce log spam

### Bug Fixes
- Fixed excessive log messages from asyncssh module
- Fixed connection handling to properly reuse connections
- Improved error handling and connection recovery

### Technical Details
- Added `connection_manager.py` with `ConnectionManager` class
- Implemented `SSHConnection` class for connection management
- Added connection state tracking using `ConnectionState` enum
- Implemented connection metrics tracking with `ConnectionMetrics` class
- Modified UnraidAPI to use the ConnectionManager
- Added logging filters to suppress verbose SSH logs
- Updated API module initialization to expose connection management classes

### Success Criteria Met
- ✅ Maximum 3 concurrent connections (configurable via pool_size)
- ✅ Connection reuse enabled
- ✅ Connection establishment handled with proper timeouts
- ✅ Log spam reduced by suppressing verbose SSH logs
- ✅ Error handling with exponential backoff and circuit breaker 

## 2025-04-05: Bug Fixes

### Fixed Thermal Zone Parser
- Fixed `_parse_thermal_zones` method to handle malformed thermal zone data
- Added error handling to prevent "not enough values to unpack" errors
- Added debug logging for skipped thermal zone lines

### Module Initialization Improvements
- Refactored module imports to avoid blocking calls in the event loop
- Pre-import platform modules at load time to avoid dynamic imports
- Added ImportWarningFilter to suppress Home Assistant import_module warnings
- Updated logging filter system to handle more warning types 