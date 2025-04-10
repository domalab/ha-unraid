# System Patterns: Unraid Integration for Home Assistant

## Architecture Overview
The Unraid Integration follows the standard Home Assistant integration architecture, with clear separation of concerns:

```
unraid/
├── api/                  # API client for communicating with Unraid
├── sensors/              # Sensor entities implementation
├── diagnostics/          # Diagnostic tools
├── translations/         # Internationalization files
├── __init__.py           # Integration setup
├── config_flow.py        # Configuration UI flow
├── coordinator.py        # Data coordinator for efficient updates
├── sensor.py             # Sensor platform registration
├── binary_sensor.py      # Binary sensor registration
├── switch.py             # Switch entity implementation
├── button.py             # Button entity implementation
├── services.py           # Custom service implementations
├── repairs.py            # Automatic repair workflows
├── const.py              # Constants and shared values
└── helpers.py            # Shared utility functions
```

## Key Design Patterns

### 1. Data Coordinator Pattern
- Uses `DataUpdateCoordinator` to efficiently fetch and distribute data
- Optimizes API calls through configurable update intervals
- Prevents redundant calls and respects server resources
- Separates data fetching logic from entity representation

### 2. Integration Setup Pattern
- Follows Home Assistant's `async_setup_entry` paradigm
- Proper cleanup on unload via `async_unload_entry`
- Forward-compatible config migration system

### 3. Configuration Flow Pattern
- Step-based configuration with validation
- Connection testing before completing setup
- Clear error handling and user feedback

### 4. Service Registration Pattern
- Well-defined service schemas in YAML
- Async service implementation
- Proper error handling and reporting

### 5. Entity Implementation Pattern
- Clear inheritance hierarchy from HA base classes
- Consistent naming and attribute handling
- Proper state reporting and error management

## Key Technical Decisions

### 1. SSH as Communication Protocol
- Decision: Use SSH rather than a REST API
- Rationale: Unraid doesn't expose a consistent API, SSH provides reliable access to all needed functionality
- Trade-offs: Requires SSH credentials, slightly higher overhead than a direct API

### 2. Separate Update Intervals
- Decision: Different update frequencies for different entity types
- Rationale: Disk information changes infrequently and is expensive to query
- Implementation: General update interval for most sensors, longer interval for disk information

### 3. Coordinator-based Data Model
- Decision: Centralized data fetching with entity subscribers
- Rationale: Minimize SSH connections and prevent overwhelming the Unraid server
- Implementation: Single coordinator with segmented data update methods

### 4. Automatic Repair Capabilities
- Decision: Implement automatic repair flows
- Rationale: Proactively help users resolve common issues
- Implementation: Integration with HA's repairs framework

### 5. Comprehensive State Validation
- Decision: Thorough validation of all state data
- Rationale: Handle unreliable or missing data gracefully
- Implementation: Defensive coding with clear fallbacks

## Component Relationships

### Data Flow
1. `coordinator.py` fetches data from Unraid via SSH
2. Data is cached and distributed to entities
3. Entities (sensors, switches, etc.) represent this data to Home Assistant
4. User actions via services or entity interaction trigger SSH commands
5. Results flow back through the coordinator to update entity states

### Key Dependencies
- `asyncssh` for asynchronous SSH connections
- Home Assistant core libraries
- No external APIs or third-party services

## Error Handling Strategy
- Connection failures trigger specific error paths
- Data validation prevents crashes on unexpected responses
- Clear error messages exposed to users through the UI
- Automatic repair flows for recoverable issues
- Graceful degradation when partial functionality is available 