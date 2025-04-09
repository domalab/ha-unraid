---
layout: default
title: Features
---

The Home Assistant Unraid Integration provides a comprehensive set of features for monitoring and controlling your Unraid server. This page details all the available features and how they can be used to enhance your home automation setup.

## System Monitoring

The integration provides comprehensive system monitoring capabilities, giving you real-time insights into your Unraid server's performance.

### CPU Metrics

- **CPU Usage**: Real-time CPU utilization percentage
  - Entity ID: `sensor.unraid_[hostname]_cpu_usage`
  - Unit: Percentage (%)
  - Updates: Every update cycle (default: 5 minutes)
- **CPU Temperature**: Current CPU temperature
  - Entity ID: `sensor.unraid_[hostname]_cpu_temperature`
  - Unit: Celsius (°C)
  - Updates: Every update cycle

### Memory Metrics

- **Memory Usage**: Current RAM usage
  - Entity ID: `sensor.unraid_[hostname]_memory_usage`
  - Unit: Percentage (%)
  - Updates: Every update cycle
- **Memory Available**: Available memory
  - Entity ID: `sensor.unraid_[hostname]_memory_available`
  - Unit: Gigabytes (GB)
  - Updates: Every update cycle

### System Status

- **Uptime**: Server uptime tracking
  - Entity ID: `sensor.unraid_[hostname]_uptime`
  - Unit: Time (days, hours, minutes)
  - Updates: Every update cycle
- **System Load**: System load averages for 1, 5, and 15 minutes
  - Entity IDs:
    - `sensor.unraid_[hostname]_load_1m`
    - `sensor.unraid_[hostname]_load_5m`
    - `sensor.unraid_[hostname]_load_15m`
  - Updates: Every update cycle

### Temperature Monitoring

- **Motherboard Temperature**: Current motherboard temperature
  - Entity ID: `sensor.unraid_[hostname]_motherboard_temperature`
  - Unit: Celsius (°C)
  - Updates: Every update cycle
- **System Fans**: Fan speeds in RPM
  - Entity ID: `sensor.unraid_[hostname]_fan_[number]_speed`
  - Unit: Revolutions Per Minute (RPM)
  - Updates: Every update cycle

### Example Use Cases

- **High Temperature Alerts**: Create automations to notify you when temperatures exceed safe thresholds
- **Performance Monitoring**: Track CPU and memory usage over time to identify performance issues
- **Fan Failure Detection**: Set up alerts for when fan speeds drop below expected values

## Storage Monitoring

The integration provides detailed monitoring of your Unraid storage system, including array status, individual disks, and health metrics.

### Array Status

- **Array Usage**: Overall array usage percentage
  - Entity ID: `sensor.unraid_[hostname]_array_usage`
  - Unit: Percentage (%)
  - Updates: Every disk update cycle (default: 1 hour)
- **Array Status**: Current status of the array (Started, Stopped, etc.)
  - Entity ID: `binary_sensor.unraid_[hostname]_array_status`
  - States: `on` (Started), `off` (Stopped)
  - Updates: Every update cycle
- **Array Protection**: Current protection mode (Normal, Parity, etc.)
  - Entity ID: `sensor.unraid_[hostname]_array_protection`
  - Updates: Every disk update cycle

### Individual Disks

- **Disk Usage**: Usage information for each disk in the array
  - Entity ID: `sensor.unraid_[hostname]_disk_[name]_usage`
  - Unit: Percentage (%)
  - Updates: Every disk update cycle
- **Disk Space**: Available and total space for each disk
  - Entity IDs:
    - `sensor.unraid_[hostname]_disk_[name]_free`
    - `sensor.unraid_[hostname]_disk_[name]_size`
  - Unit: Terabytes (TB) or Gigabytes (GB)
  - Updates: Every disk update cycle

### Disk Health

- **SMART Status**: SMART health status for each disk
  - Entity ID: `binary_sensor.unraid_[hostname]_disk_[name]_smart_status`
  - States: `on` (Healthy), `off` (Issues detected)
  - Updates: Every disk update cycle
- **Disk Temperature**: Temperature for each disk
  - Entity ID: `sensor.unraid_[hostname]_disk_[name]_temperature`
  - Unit: Celsius (°C)
  - Updates: Every disk update cycle
- **SMART Attributes**: Critical SMART attributes for each disk
  - Entity IDs: Various, depending on the disk and available attributes
  - Updates: Every disk update cycle

### Parity Information

- **Parity Status**: Current parity check status
  - Entity ID: `sensor.unraid_[hostname]_parity_status`
  - Updates: Every update cycle
- **Parity Schedule**: Next scheduled parity check
  - Entity ID: `sensor.unraid_[hostname]_next_parity_check`
  - Updates: Every update cycle

### Cache Pool

- **Cache Usage**: Cache pool usage percentage
  - Entity ID: `sensor.unraid_[hostname]_cache_usage`
  - Unit: Percentage (%)
  - Updates: Every disk update cycle
- **Cache Status**: Status of the cache pool
  - Entity ID: `binary_sensor.unraid_[hostname]_cache_status`
  - States: `on` (Healthy), `off` (Issues detected)
  - Updates: Every disk update cycle

### Storage Use Cases

- **Disk Space Alerts**: Get notified when disks are nearing capacity
- **Disk Health Monitoring**: Track disk health and temperature over time
- **Parity Check Tracking**: Monitor parity check progress and schedule
- **Automated Backups**: Trigger backups based on array status

## Docker Container Management

The integration provides comprehensive management of Docker containers running on your Unraid server.

### Container Status Monitoring

- **Container Status**: Monitor the status of Docker containers
  - Entity ID: `binary_sensor.unraid_[hostname]_docker_[container_name]`
  - States: `on` (Running), `off` (Stopped)
  - Updates: Every update cycle
- **Container Health**: Monitor the health status of Docker containers (if supported)
  - Entity ID: `sensor.unraid_[hostname]_docker_[container_name]_health`
  - States: `healthy`, `unhealthy`, `starting`, `unknown`
  - Updates: Every update cycle

### Container Control

- **Container Control**: Start, stop, and restart containers
  - Entity ID: `switch.unraid_[hostname]_docker_[container_name]`
  - Actions: Turn on (start), Turn off (stop)
  - Service calls:
    - `unraid.start_container`
    - `unraid.stop_container`
    - `unraid.restart_container`

### Container Resource Monitoring

- **CPU Usage**: Monitor container CPU usage
  - Entity ID: `sensor.unraid_[hostname]_docker_[container_name]_cpu`
  - Unit: Percentage (%)
  - Updates: Every update cycle
- **Memory Usage**: Monitor container memory usage
  - Entity ID: `sensor.unraid_[hostname]_docker_[container_name]_memory`
  - Unit: Megabytes (MB)
  - Updates: Every update cycle

### Container Management Use Cases

- **Automated Container Restarts**: Schedule container restarts during low-usage periods
- **Resource Monitoring**: Track container resource usage and get alerts for high usage
- **Dependency Management**: Start containers in a specific order based on dependencies
- **Power Management**: Automatically stop resource-intensive containers when not needed

## Virtual Machine Management

The integration provides monitoring and control of virtual machines running on your Unraid server.

### VM Status Monitoring

- **VM Status**: Monitor the status of virtual machines
  - Entity ID: `binary_sensor.unraid_[hostname]_vm_[vm_name]`
  - States: `on` (Running), `off` (Stopped)
  - Updates: Every update cycle
- **VM Details**: Additional information about each VM
  - Entity ID: `sensor.unraid_[hostname]_vm_[vm_name]_info`
  - Attributes: CPU cores, memory allocation, etc.
  - Updates: Every update cycle

### VM Control

- **VM Control**: Start, stop, and restart VMs
  - Entity ID: `switch.unraid_[hostname]_vm_[vm_name]`
  - Actions: Turn on (start), Turn off (stop)
  - Service calls:
    - `unraid.start_vm`
    - `unraid.stop_vm`
    - `unraid.restart_vm`

### VM Management Use Cases

- **Scheduled VM Operations**: Automatically start or stop VMs on a schedule
- **Conditional VM Control**: Start VMs based on presence detection or other triggers
- **Energy Saving**: Automatically shut down VMs during periods of inactivity
- **Sequential Operations**: Coordinate VM operations with Docker container management

## Command Execution

The integration allows you to execute commands and scripts on your Unraid server directly from Home Assistant.

### Service Commands

- **Execute Command**: Run shell commands on your Unraid server
  - Service call: `unraid.execute_command`
  - Parameters:
    - `command`: The shell command to execute
  - Returns: Command output and exit code

### User Scripts

- **User Script Execution**: Run user scripts from Home Assistant
  - Entity ID: `button.unraid_[hostname]_script_[script_name]`
  - Service call: `unraid.run_script`
  - Parameters:
    - `script_name`: The name of the script to run
  - Returns: Script output and exit code

- **User Script Status**: Monitor the status of user scripts
  - Entity ID: `sensor.unraid_[hostname]_script_[script_name]_status`
  - States: `idle`, `running`, `completed`, `failed`
  - Updates: When script status changes

### Command Execution Use Cases

- **System Maintenance**: Run maintenance commands on a schedule
- **Custom Automations**: Execute custom scripts based on triggers
- **Integration with Other Systems**: Use Unraid as a central automation hub
- **Diagnostic Commands**: Run diagnostic commands when issues are detected

## UPS Monitoring

The integration provides monitoring of UPS (Uninterruptible Power Supply) devices connected to your Unraid server.

### UPS Status

- **UPS Status**: Monitor UPS status when available
  - Entity ID: `binary_sensor.unraid_[hostname]_ups_status`
  - States: `on` (Online), `off` (Offline)
  - Updates: Every update cycle
- **UPS Model**: Information about the UPS model
  - Entity ID: `sensor.unraid_[hostname]_ups_model`
  - Updates: Every update cycle

### Power Monitoring

- **Input Voltage**: Monitor input voltage to the UPS
  - Entity ID: `sensor.unraid_[hostname]_ups_input_voltage`
  - Unit: Volts (V)
  - Updates: Every update cycle
- **Output Voltage**: Monitor output voltage from the UPS
  - Entity ID: `sensor.unraid_[hostname]_ups_output_voltage`
  - Unit: Volts (V)
  - Updates: Every update cycle
- **Load Percentage**: Monitor the load on the UPS
  - Entity ID: `sensor.unraid_[hostname]_ups_load`
  - Unit: Percentage (%)
  - Updates: Every update cycle

### Battery Information

- **Battery Level**: Track UPS battery level
  - Entity ID: `sensor.unraid_[hostname]_ups_battery`
  - Unit: Percentage (%)
  - Updates: Every update cycle
- **Runtime Remaining**: Estimate remaining runtime during power outages
  - Entity ID: `sensor.unraid_[hostname]_ups_runtime`
  - Unit: Minutes
  - Updates: Every update cycle

### UPS Monitoring Use Cases

- **Power Outage Alerts**: Get notified when power outages occur
- **Automated Shutdown**: Trigger safe shutdown procedures during extended outages
- **Battery Health Monitoring**: Track battery health over time
- **Power Quality Monitoring**: Monitor input voltage for power quality issues

## Advanced Features

The integration includes several advanced features designed to optimize performance and reliability.

### Performance Optimization

- **Intelligent Caching**: Optimized data collection with smart caching
  - Caches data based on update frequency and importance
  - Reduces unnecessary SSH connections
  - Improves response time for entity state updates
  - Automatically invalidates cache when data is likely to have changed

- **Priority-Based Updates**: Focus on updating the most critical data first
  - Updates high-priority entities more frequently
  - Ensures critical information is always current
  - Adapts update frequency based on system load

- **Resource-Efficient**: Designed to minimize impact on both Home Assistant and Unraid
  - Batches commands to reduce SSH connections
  - Optimizes data parsing to reduce CPU usage
  - Implements efficient error handling and recovery

### Reliability Features

- **Connection Management**: Robust SSH connection handling
  - Automatic reconnection on connection loss
  - Connection pooling to reduce overhead
  - Timeout handling to prevent hanging connections

- **Error Recovery**: Graceful handling of errors
  - Automatic retry for transient errors
  - Fallback mechanisms for critical data
  - Detailed logging for troubleshooting

### Advanced Configuration

- **Update Intervals**: Customizable update intervals for different data types
  - General system information
  - Disk information
  - Docker and VM information

- **Feature Selection**: Enable or disable specific features
  - UPS monitoring
  - Docker container monitoring
  - VM monitoring

## Entity Types

The integration provides various entity types to represent different aspects of your Unraid server.

### Sensors

- **Purpose**: For monitoring numeric values and states
- **Examples**:
  - CPU usage percentage
  - Memory usage
  - Disk temperatures
  - UPS battery level
- **Attributes**: Most sensors include additional attributes with related information
- **Units**: Where applicable, sensors include appropriate units (%, °C, GB, etc.)

### Binary Sensors

- **Purpose**: For status indicators with on/off states
- **Examples**:
  - Server online status
  - Array status (started/stopped)
  - Docker container status (running/stopped)
  - VM status (running/stopped)
- **Attributes**: May include additional status information
- **Device Class**: Uses appropriate device classes for correct icon display

### Switches

- **Purpose**: For toggling states
- **Examples**:
  - Docker container control (start/stop)
  - VM control (start/stop)
  - Service control (enable/disable)
- **Actions**: Turn on (start/enable), Turn off (stop/disable)
- **Feedback**: State reflects the actual status of the controlled entity

### Buttons

- **Purpose**: For triggering one-time actions
- **Examples**:
  - Run user scripts
  - Reboot server
  - Execute commands
- **Feedback**: May update related sensors with action results

## Service Calls

The integration exposes several services that can be used in automations and scripts.

### Command Service

- **`unraid.execute_command`**: Run a shell command on the Unraid server
  - **Parameters**:
    - `command` (required): The shell command to execute
  - **Returns**: Command output and exit code
  - **Example**:

    ```yaml
    service: unraid.execute_command
    target:
      entity_id: sensor.unraid_tower_cpu_usage
    data:
      command: "uptime"
    ```

### Container Services

- **`unraid.start_container`**: Start a Docker container
  - **Parameters**:
    - `container` (required): The name of the container to start
  - **Example**:

    ```yaml
    service: unraid.start_container
    target:
      entity_id: switch.unraid_tower_docker_plex
    data:
      container: "plex"
    ```

- **`unraid.stop_container`**: Stop a Docker container
  - **Parameters**:
    - `container` (required): The name of the container to stop
  - **Example**:

    ```yaml
    service: unraid.stop_container
    target:
      entity_id: switch.unraid_tower_docker_plex
    data:
      container: "plex"
    ```

- **`unraid.restart_container`**: Restart a Docker container
  - **Parameters**:
    - `container` (required): The name of the container to restart
  - **Example**:

    ```yaml
    service: unraid.restart_container
    target:
      entity_id: switch.unraid_tower_docker_plex
    data:
      container: "plex"
    ```

### VM Services

- **`unraid.start_vm`**: Start a virtual machine
  - **Parameters**:
    - `vm` (required): The name of the VM to start
  - **Example**:

    ```yaml
    service: unraid.start_vm
    target:
      entity_id: switch.unraid_tower_vm_windows10
    data:
      vm: "Windows10"
    ```

- **`unraid.stop_vm`**: Stop a virtual machine
  - **Parameters**:
    - `vm` (required): The name of the VM to stop
  - **Example**:

    ```yaml
    service: unraid.stop_vm
    target:
      entity_id: switch.unraid_tower_vm_windows10
    data:
      vm: "Windows10"
    ```

- **`unraid.restart_vm`**: Restart a virtual machine
  - **Parameters**:
    - `vm` (required): The name of the VM to restart
  - **Example**:

    ```yaml
    service: unraid.restart_vm
    target:
      entity_id: switch.unraid_tower_vm_windows10
    data:
      vm: "Windows10"
    ```

### Script Management

- **`unraid.run_script`**: Execute a user script
  - **Parameters**:
    - `script` (required): The name of the script to run
  - **Returns**: Script output and exit code
  - **Example**:

    ```yaml
    service: unraid.run_script
    target:
      entity_id: button.unraid_tower_script_backup
    data:
      script: "backup"
    ```
