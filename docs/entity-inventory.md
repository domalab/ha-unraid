# Entity Inventory - Unraid Home Assistant Integration

This document provides a comprehensive catalog of all entities created by the Unraid Home Assistant integration. This serves as a developer reference for creating consistent Unraid integrations across different Home Assistant implementations.

## Overview

The Unraid integration creates entities across multiple platforms:
- **Sensors**: System metrics, storage usage, network statistics, UPS monitoring
- **Binary Sensors**: Status indicators, health monitoring, connectivity checks
- **Switches**: VM control, Docker container management
- **Buttons**: System actions, user script execution

## Update Intervals & Polling Behavior

### Coordinator Update Intervals
- **General Interval**: 1-60 minutes (default: 5 minutes) - configurable
- **Disk Interval**: 5 minutes to 24 hours (default: 60 minutes) - configurable

### Cache TTL Settings
- **Static Data**: 1 hour (disk mapping, device serials/models)
- **Semi-Dynamic Data**: 2-10 minutes (system stats, Docker/VM info)
- **Real-Time Data**: 15 seconds to 1 minute (network stats, CPU/memory)
- **Critical Monitoring**: 30 seconds (disk power state, SMART alerts)

### Sensor Priority Levels
- **Critical**: 60 seconds (array status, parity status, system state)
- **High**: 2 minutes (CPU, memory, temperatures)
- **Medium**: 5 minutes (storage usage, Docker stats)
- **Low**: 15 minutes (static information, detailed attributes)

## Entity Naming Conventions

### Unique ID Format
`{entry_id}_{component}_{feature}_{subfeature}`

### Entity ID Format
`{platform}.{hostname}_{feature}_{subfeature}`

### Device Naming
- **Main Server**: `{hostname.title()}`
- **System Components**: `Unraid System ({hostname})`
- **Docker Containers**: `{container_name}`
- **Virtual Machines**: `{vm_name}`
- **Storage Devices**: `Unraid Disk ({disk_name})`

## Sensors

### System Sensors

#### CPU Usage Sensor
- **Entity ID**: `sensor.{hostname}_cpu_usage`
- **Unique ID**: `{entry_id}_system_cpu_usage`
- **Display Value**: CPU utilization percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:cpu-64-bit`
- **Precision**: 1 decimal place
- **Update Frequency**: High priority (2 minutes)
- **Availability**: Always available when system_stats data exists

**Attributes:**
```json
{
  "cores": 8,
  "threads": 16,
  "model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz",
  "architecture": "x86_64",
  "load_average": [1.2, 1.5, 1.8]
}
```

#### RAM Usage Sensor
- **Entity ID**: `sensor.{hostname}_ram_usage`
- **Unique ID**: `{entry_id}_system_ram_usage`
- **Display Value**: RAM usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:memory`
- **Precision**: 1 decimal place
- **Update Frequency**: High priority (2 minutes)

**Attributes:**
```json
{
  "total_gb": 32.0,
  "used_gb": 12.5,
  "available_gb": 19.5,
  "cached_gb": 8.2,
  "buffers_gb": 0.8
}
```

#### Uptime Sensor
- **Entity ID**: `sensor.{hostname}_uptime`
- **Unique ID**: `{entry_id}_system_uptime`
- **Display Value**: System uptime in seconds
- **Device Class**: `duration`
- **State Class**: `measurement`
- **Unit**: `s` (seconds)
- **Icon**: `mdi:clock-outline`
- **Update Frequency**: Medium priority (5 minutes)

**Attributes:**
```json
{
  "uptime_days": 15,
  "uptime_hours": 2,
  "uptime_minutes": 34,
  "boot_time": "2024-01-15T08:30:00Z"
}
```

#### Temperature Sensors

##### CPU Temperature
- **Entity ID**: `sensor.{hostname}_cpu_temp`
- **Unique ID**: `{entry_id}_system_cpu_temp`
- **Display Value**: CPU temperature in Celsius
- **Device Class**: `temperature`
- **State Class**: `measurement`
- **Unit**: `°C`
- **Icon**: `mdi:thermometer`
- **Precision**: 1 decimal place
- **Update Frequency**: High priority (2 minutes)
- **Availability**: Only when temperature sensors are available

**Attributes:**
```json
{
  "sensor_name": "coretemp-isa-0000",
  "critical_temp": 100,
  "max_temp": 85,
  "alarm": false
}
```

##### Motherboard Temperature
- **Entity ID**: `sensor.{hostname}_motherboard_temp`
- **Unique ID**: `{entry_id}_system_motherboard_temp`
- **Display Value**: Motherboard temperature in Celsius
- **Device Class**: `temperature`
- **State Class**: `measurement`
- **Unit**: `°C`
- **Icon**: `mdi:thermometer`
- **Precision**: 1 decimal place
- **Update Frequency**: High priority (2 minutes)
- **Availability**: Only when motherboard temperature sensors are available

#### Storage System Sensors

##### Docker Storage
- **Entity ID**: `sensor.{hostname}_docker_vdisk`
- **Unique ID**: `{entry_id}_system_docker_vdisk`
- **Display Value**: Docker virtual disk usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:docker`
- **Precision**: 1 decimal place
- **Update Frequency**: Medium priority (5 minutes)

**Attributes:**
```json
{
  "total_gb": 20.0,
  "used_gb": 8.5,
  "available_gb": 11.5,
  "mount_point": "/var/lib/docker"
}
```

##### Log Storage
- **Entity ID**: `sensor.{hostname}_log_filesystem`
- **Unique ID**: `{entry_id}_system_log_filesystem`
- **Display Value**: Log filesystem usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:file-document-outline`
- **Precision**: 1 decimal place

##### Boot Storage
- **Entity ID**: `sensor.{hostname}_boot_usage`
- **Unique ID**: `{entry_id}_system_boot_usage`
- **Display Value**: Boot partition usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:harddisk`
- **Precision**: 1 decimal place

#### Fan Sensors (Dynamic)
- **Entity ID**: `sensor.{hostname}_fan_{fan_id}`
- **Unique ID**: `{entry_id}_system_fan_{fan_id}`
- **Display Value**: Fan speed in RPM
- **State Class**: `measurement`
- **Unit**: `RPM`
- **Icon**: `mdi:fan`
- **Precision**: 0 decimal places
- **Update Frequency**: Medium priority (5 minutes)
- **Availability**: Only when fan sensors are detected

**Attributes:**
```json
{
  "fan_label": "CPU Fan",
  "min_rpm": 0,
  "max_rpm": 2000,
  "alarm": false
}
```

#### Intel GPU Sensor (Conditional)
- **Entity ID**: `sensor.{hostname}_intel_gpu_usage`
- **Unique ID**: `{entry_id}_system_intel_gpu_usage`
- **Display Value**: Intel GPU usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:expansion-card`
- **Precision**: 1 decimal place
- **Availability**: Only when Intel GPU is detected

**Attributes:**
```json
{
  "model": "Intel UHD Graphics 630",
  "driver": "i915",
  "memory_used_mb": 256,
  "memory_total_mb": 1024
}
```

### Storage Sensors

#### Array Usage Sensor
- **Entity ID**: `sensor.{hostname}_array`
- **Unique ID**: `{entry_id}_storage_array`
- **Display Value**: Array usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:harddisk`
- **Precision**: 1 decimal place
- **Update Frequency**: Medium priority (5 minutes)

**Attributes:**
```json
{
  "total_tb": 12.5,
  "used_tb": 8.2,
  "free_tb": 4.3,
  "num_disks": 6,
  "num_data_disks": 4,
  "num_parity_disks": 2,
  "array_state": "Started",
  "protection": "Protected"
}
```

#### Individual Disk Sensors (Dynamic)
- **Entity ID**: `sensor.{hostname}_disk_{disk_name}`
- **Unique ID**: `{entry_id}_storage_disk_{disk_name}`
- **Display Value**: Disk usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:harddisk`
- **Precision**: 1 decimal place
- **Update Frequency**: Disk interval (default 60 minutes)
- **Availability**: Only for spinning drives (non-SSD)

**Attributes:**
```json
{
  "total_gb": 2000.0,
  "used_gb": 1200.0,
  "free_gb": 800.0,
  "device": "/dev/sdb1",
  "filesystem": "xfs",
  "mount_point": "/mnt/disk1",
  "disk_type": "HDD",
  "temperature": 35,
  "power_state": "active",
  "smart_status": "PASSED"
}
```

#### Pool Sensors (Dynamic)
- **Entity ID**: `sensor.{hostname}_pool_{pool_name}`
- **Unique ID**: `{entry_id}_storage_pool_{pool_name}`
- **Display Value**: Pool usage percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:harddisk`
- **Precision**: 1 decimal place
- **Update Frequency**: Disk interval (default 60 minutes)
- **Availability**: Only for SSD pools/cache drives

**Attributes:**
```json
{
  "total_gb": 500.0,
  "used_gb": 125.0,
  "free_gb": 375.0,
  "pool_type": "cache",
  "raid_level": "RAID1",
  "num_devices": 2,
  "devices": ["/dev/nvme0n1", "/dev/nvme1n1"],
  "filesystem": "btrfs"
}
```

### Network Sensors

#### Network Inbound Sensor
- **Entity ID**: `sensor.{hostname}_network_inbound`
- **Unique ID**: `{entry_id}_network_inbound`
- **Display Value**: Inbound data rate
- **Device Class**: `data_rate`
- **State Class**: `measurement`
- **Unit**: Dynamic (B/s, KB/s, MB/s, GB/s)
- **Icon**: `mdi:arrow-down`
- **Precision**: 2 decimal places
- **Update Frequency**: Real-time (15 seconds)

**Attributes:**
```json
{
  "interface": "eth0",
  "bytes_received": 1234567890,
  "packets_received": 987654,
  "errors": 0,
  "dropped": 0
}
```

#### Network Outbound Sensor
- **Entity ID**: `sensor.{hostname}_network_outbound`
- **Unique ID**: `{entry_id}_network_outbound`
- **Display Value**: Outbound data rate
- **Device Class**: `data_rate`
- **State Class**: `measurement`
- **Unit**: Dynamic (B/s, KB/s, MB/s, GB/s)
- **Icon**: `mdi:arrow-up`
- **Precision**: 2 decimal places
- **Update Frequency**: Real-time (15 seconds)

**Attributes:**
```json
{
  "interface": "eth0",
  "bytes_sent": 987654321,
  "packets_sent": 654321,
  "errors": 0,
  "dropped": 0
}
```

### UPS Sensors (Conditional)

#### UPS Power Consumption
- **Entity ID**: `sensor.{hostname}_ups_current_consumption`
- **Unique ID**: `{entry_id}_ups_current_consumption`
- **Display Value**: Current power consumption in watts
- **Device Class**: `power`
- **State Class**: `measurement`
- **Unit**: `W`
- **Icon**: `mdi:power-plug`
- **Precision**: 1 decimal place
- **Update Frequency**: Medium priority (2 minutes)
- **Availability**: Only when UPS is configured and detected

**Attributes:**
```json
{
  "ups_model": "APC Smart-UPS 1500",
  "input_voltage": 120.0,
  "output_voltage": 120.0,
  "battery_charge": 100,
  "estimated_runtime": 3600,
  "ups_status": "Online"
}
```

#### UPS Energy Consumption
- **Entity ID**: `sensor.{hostname}_ups_energy_consumption`
- **Unique ID**: `{entry_id}_ups_energy_consumption`
- **Display Value**: Total energy consumption in kWh
- **Device Class**: `energy`
- **State Class**: `total_increasing`
- **Unit**: `kWh`
- **Icon**: `mdi:lightning-bolt`
- **Precision**: 3 decimal places
- **Update Frequency**: Medium priority (2 minutes)

#### UPS Load Percentage
- **Entity ID**: `sensor.{hostname}_ups_load_percentage`
- **Unique ID**: `{entry_id}_ups_load_percentage`
- **Display Value**: UPS load percentage
- **Device Class**: `power_factor`
- **State Class**: `measurement`
- **Unit**: `%`
- **Icon**: `mdi:gauge`
- **Precision**: 1 decimal place
- **Update Frequency**: Medium priority (2 minutes)

### Docker Sensors

#### Running Containers
- **Entity ID**: `sensor.{hostname}_containers_running`
- **Unique ID**: `{entry_id}_docker_containers_running`
- **Display Value**: Number of running containers
- **Icon**: `mdi:docker`
- **Entity Category**: `diagnostic`
- **Update Frequency**: Medium priority (5 minutes)
- **Availability**: Only when Docker service is running

**Attributes:**
```json
{
  "container_names": ["plex", "sonarr", "radarr"],
  "total_containers": 15,
  "paused_containers": 2,
  "stopped_containers": 10
}
```

#### Paused Containers
- **Entity ID**: `sensor.{hostname}_containers_paused`
- **Unique ID**: `{entry_id}_docker_containers_paused`
- **Display Value**: Number of paused containers
- **Icon**: `mdi:docker`
- **Entity Category**: `diagnostic`
- **Update Frequency**: Medium priority (5 minutes)

## Binary Sensors

### System Status Binary Sensors

#### Server Connection
- **Entity ID**: `binary_sensor.{hostname}_ssh_connectivity`
- **Unique ID**: `{entry_id}_diagnostics_ssh_connectivity`
- **Display Value**: Connection status (on/off)
- **Device Class**: `connectivity`
- **Entity Category**: `diagnostic`
- **Icon**: `mdi:server-network`
- **Update Frequency**: Critical priority (60 seconds)
- **State Values**:
  - `on`: Server is reachable via SSH
  - `off`: Server is not reachable

**Attributes:**
```json
{
  "last_successful_connection": "2024-01-30T10:15:00Z",
  "connection_method": "SSH",
  "port": 22,
  "response_time_ms": 45
}
```

#### Docker Service Status
- **Entity ID**: `binary_sensor.{hostname}_docker_service`
- **Unique ID**: `{entry_id}_diagnostics_docker_service`
- **Display Value**: Docker service status (on/off)
- **Device Class**: `running`
- **Entity Category**: `diagnostic`
- **Icon**: `mdi:docker`
- **Update Frequency**: Medium priority (5 minutes)
- **State Values**:
  - `on`: Docker service is running
  - `off`: Docker service is stopped

#### VM Service Status
- **Entity ID**: `binary_sensor.{hostname}_vm_service`
- **Unique ID**: `{entry_id}_diagnostics_vm_service`
- **Display Value**: VM service status (on/off)
- **Device Class**: `running`
- **Entity Category**: `diagnostic`
- **Icon**: `mdi:desktop-tower`
- **Update Frequency**: Medium priority (5 minutes)
- **State Values**:
  - `on`: VM service is running
  - `off`: VM service is stopped

### Array Status Binary Sensors

#### Array Health
- **Entity ID**: `binary_sensor.{hostname}_array_health`
- **Unique ID**: `{entry_id}_array_health`
- **Display Value**: Array health status (on/off)
- **Device Class**: `problem`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Critical priority (60 seconds)
- **State Values**:
  - `on`: Array has problems/errors
  - `off`: Array is healthy

**Attributes:**
```json
{
  "array_state": "Started",
  "protection_status": "Protected",
  "num_errors": 0,
  "last_check": "2024-01-29T02:00:00Z",
  "sync_errors": 0,
  "parity_errors": 0
}
```

#### Array Status
- **Entity ID**: `binary_sensor.{hostname}_array_status`
- **Unique ID**: `{entry_id}_array_status`
- **Display Value**: Array running status (on/off)
- **Device Class**: `running`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Critical priority (60 seconds)
- **State Values**:
  - `on`: Array is started
  - `off`: Array is stopped

### Disk Health Binary Sensors (Dynamic)

#### Array Disk Health
- **Entity ID**: `binary_sensor.{hostname}_disk_{disk_name}_health`
- **Unique ID**: `{entry_id}_disk_{disk_name}_health`
- **Display Value**: Disk health status (on/off)
- **Device Class**: `problem`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Disk interval (default 60 minutes)
- **State Values**:
  - `on`: Disk has problems/errors
  - `off`: Disk is healthy
- **Availability**: Only for array disks (disk1, disk2, etc.)

**Attributes:**
```json
{
  "smart_status": "PASSED",
  "temperature": 35,
  "power_on_hours": 12345,
  "reallocated_sectors": 0,
  "pending_sectors": 0,
  "offline_uncorrectable": 0,
  "device": "/dev/sdb",
  "model": "WD Red 4TB",
  "serial": "WD-WCC4N1234567"
}
```

#### Pool Disk Health
- **Entity ID**: `binary_sensor.{hostname}_pool_{pool_name}_health`
- **Unique ID**: `{entry_id}_pool_{pool_name}_health`
- **Display Value**: Pool health status (on/off)
- **Device Class**: `problem`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Disk interval (default 60 minutes)
- **State Values**:
  - `on`: Pool has problems/errors
  - `off`: Pool is healthy
- **Availability**: Only for SSD pools/cache drives

#### Parity Disk Health
- **Entity ID**: `binary_sensor.{hostname}_parity_disk_health`
- **Unique ID**: `{entry_id}_parity_disk_health`
- **Display Value**: Parity disk health status (on/off)
- **Device Class**: `problem`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Disk interval (default 60 minutes)
- **State Values**:
  - `on`: Parity disk has problems/errors
  - `off`: Parity disk is healthy
- **Availability**: Only when parity disk is configured

#### Parity Check Status
- **Entity ID**: `binary_sensor.{hostname}_parity_check`
- **Unique ID**: `{entry_id}_parity_check`
- **Display Value**: Parity check running status (on/off)
- **Device Class**: `running`
- **Icon**: `mdi:harddisk`
- **Update Frequency**: Critical priority (60 seconds)
- **State Values**:
  - `on`: Parity check is running
  - `off`: Parity check is not running

**Attributes:**
```json
{
  "status": "idle",
  "progress": 0,
  "speed": "0 MB/s",
  "elapsed_time": "00:00:00",
  "estimated_completion": null,
  "last_check_date": "2024-01-29",
  "last_check_duration": "4:32:15",
  "last_check_errors": 0,
  "next_scheduled_check": "2024-02-29T02:00:00Z"
}
```

### UPS Binary Sensors (Conditional)

#### UPS Status
- **Entity ID**: `binary_sensor.{hostname}_ups_status`
- **Unique ID**: `{entry_id}_ups_status`
- **Display Value**: UPS online status (on/off)
- **Device Class**: `power`
- **Icon**: `mdi:battery-charging`
- **Update Frequency**: Medium priority (2 minutes)
- **State Values**:
  - `on`: UPS is online/normal
  - `off`: UPS is on battery/problem
- **Availability**: Only when UPS is configured and detected

**Attributes:**
```json
{
  "ups_status": "Online",
  "battery_charge": 100,
  "estimated_runtime": 3600,
  "input_voltage": 120.0,
  "output_voltage": 120.0,
  "load_percentage": 25,
  "last_test": "2024-01-25T10:00:00Z"
}
```

## Switches

### Virtual Machine Switches (Dynamic)

#### VM Power Control
- **Entity ID**: `switch.{hostname}_vm_{vm_name}`
- **Unique ID**: `{entry_id}_vm_{safe_vm_name}`
- **Display Value**: VM power state (on/off)
- **Icon**: `mdi:desktop-tower`
- **Update Frequency**: Medium priority (5 minutes)
- **State Values**:
  - `on`: VM is running
  - `off`: VM is stopped/paused
- **Availability**: Only for configured VMs
- **Device**: Individual device per VM

**Actions:**
- **Turn On**: Starts the virtual machine
- **Turn Off**: Gracefully shuts down the virtual machine

**Attributes:**
```json
{
  "status": "running",
  "os_type": "Windows 10",
  "cpu_cores": 4,
  "memory_mb": 8192,
  "autostart": true,
  "template": "Windows 10",
  "description": "Gaming VM"
}
```

**Entity Naming Notes:**
- VM names are normalized to create safe entity IDs
- Names starting with numbers get prefixed with "vm_"
- Collision detection ensures unique entity IDs
- Special characters are replaced with underscores

### Docker Container Switches (Dynamic)

#### Container Control
- **Entity ID**: `switch.{hostname}_container_{container_name}`
- **Unique ID**: `{entry_id}_docker_{safe_container_name}`
- **Display Value**: Container state (on/off)
- **Icon**: `mdi:docker`
- **Update Frequency**: Medium priority (5 minutes)
- **State Values**:
  - `on`: Container is running
  - `off`: Container is stopped/paused
- **Availability**: Only for Docker containers
- **Device**: Individual device per container

**Actions:**
- **Turn On**: Starts the Docker container
- **Turn Off**: Stops the Docker container

**Attributes:**
```json
{
  "status": "running",
  "image": "linuxserver/plex:latest",
  "ports": ["32400:32400/tcp"],
  "volumes": ["/mnt/user/media:/media"],
  "autostart": true,
  "network_mode": "bridge",
  "cpu_usage": 15.2,
  "memory_usage_mb": 512
}
```

## Buttons

### System Control Buttons

#### Reboot Button
- **Entity ID**: `button.{hostname}_reboot`
- **Unique ID**: `{entry_id}_reboot`
- **Name**: "Reboot"
- **Icon**: `mdi:restart`
- **Entity Category**: `config`
- **Entity Registry Enabled**: `true` (enabled by default)
- **Device**: Main server device

**Action**: Executes system reboot with no delay

**Attributes:**
```json
{
  "last_pressed": "2024-01-30T10:15:00Z",
  "action_type": "system_reboot",
  "delay_seconds": 0
}
```

#### Shutdown Button
- **Entity ID**: `button.{hostname}_shutdown`
- **Unique ID**: `{entry_id}_shutdown`
- **Name**: "Shutdown"
- **Icon**: `mdi:power`
- **Entity Category**: `config`
- **Entity Registry Enabled**: `true` (enabled by default)
- **Device**: Main server device

**Action**: Executes system shutdown with no delay

**Attributes:**
```json
{
  "last_pressed": "2024-01-30T10:15:00Z",
  "action_type": "system_shutdown",
  "delay_seconds": 0
}
```

### User Script Buttons (Dynamic)

#### Script Execution Button (Foreground)
- **Entity ID**: `button.{hostname}_script_{script_name}_run`
- **Unique ID**: `{entry_id}_script_{script_name}_run`
- **Name**: "{script_name}"
- **Icon**: `mdi:script-text-play`
- **Entity Category**: `config`
- **Entity Registry Enabled**: `false` (disabled by default)
- **Device**: Main server device
- **Availability**: Only for scripts that support foreground execution

**Action**: Executes user script in foreground mode

**Attributes:**
```json
{
  "running": false,
  "last_executed_at": "2024-01-30T09:30:00Z",
  "execution_type": "foreground",
  "status": "completed",
  "last_result": "Script completed successfully",
  "completed_at": "2024-01-30T09:32:15Z"
}
```

#### Script Execution Button (Background)
- **Entity ID**: `button.{hostname}_script_{script_name}_background`
- **Unique ID**: `{entry_id}_script_{script_name}_background`
- **Name**: "{script_name} (Background)"
- **Icon**: `mdi:script-text-play-outline`
- **Entity Category**: `config`
- **Entity Registry Enabled**: `false` (disabled by default)
- **Device**: Main server device
- **Availability**: Only for scripts that support background execution

**Action**: Executes user script in background mode

**Attributes:**
```json
{
  "running": true,
  "last_executed_at": "2024-01-30T09:30:00Z",
  "execution_type": "background",
  "status": "running",
  "last_result": "Script started in background",
  "completed_at": null
}
```

**Script Button Notes:**
- Scripts can have both foreground and background buttons
- Some scripts may be restricted to one execution mode
- Output is truncated to 1000 characters for attributes
- Background scripts maintain "running" state until completion

## Device Organization

### Main Server Device
- **Identifiers**: `{DOMAIN}_{entry_id}`
- **Name**: `{hostname.title()}`
- **Manufacturer**: "Lime Technology"
- **Model**: "Unraid Server"

**Associated Entities:**
- System sensors (CPU, RAM, temperatures, etc.)
- System binary sensors (connectivity, services)
- System buttons (reboot, shutdown)
- User script buttons
- UPS sensors (if configured)

### System Component Device
- **Identifiers**: `{DOMAIN}_{entry_id}_system`
- **Name**: `Unraid System ({hostname})`
- **Manufacturer**: "Lime Technology"
- **Model**: "Unraid Server"

**Associated Entities:**
- Detailed system sensors
- Storage system sensors (Docker, logs, boot)

### Storage Devices (Dynamic)
- **Identifiers**: `{DOMAIN}_{entry_id}_disk_{disk_name}`
- **Name**: `Unraid Disk ({disk_name})`
- **Manufacturer**: Extracted from disk model
- **Model**: Disk model information

**Associated Entities:**
- Individual disk sensors
- Disk health binary sensors

### Virtual Machine Devices (Dynamic)
- **Identifiers**: `{DOMAIN}_{entry_id}_vm_{vm_name}`
- **Name**: `{vm_name}`
- **Manufacturer**: "Unraid"
- **Model**: "Virtual Machine"

**Associated Entities:**
- VM power switch
- VM-specific sensors (if any)

### Docker Container Devices (Dynamic)
- **Identifiers**: `{DOMAIN}_{entry_id}_docker_{container_name}`
- **Name**: `{container_name}`
- **Manufacturer**: "Docker"
- **Model**: "Container Engine"

**Associated Entities:**
- Container power switch
- Container-specific sensors (if any)

### UPS Device (Conditional)
- **Identifiers**: `{DOMAIN}_{entry_id}_ups`
- **Name**: `Unraid UPS ({hostname})`
- **Manufacturer**: UPS manufacturer
- **Model**: UPS model

**Associated Entities:**
- UPS power sensors
- UPS status binary sensors

## Entity Availability Conditions

### Always Available
- Server connection binary sensor
- System control buttons (reboot/shutdown)

### Conditional Availability
- **Intel GPU Sensor**: Only when Intel GPU is detected
- **Temperature Sensors**: Only when temperature sensors are available
- **Fan Sensors**: Only when fan sensors are detected
- **UPS Entities**: Only when UPS is configured and detected
- **Docker Entities**: Only when Docker service is running
- **VM Entities**: Only when VMs are configured
- **User Script Buttons**: Only when user scripts are available
- **Disk/Pool Sensors**: Only for detected storage devices

### Data-Dependent Availability
- **Array Status**: Only when array data is available
- **Parity Sensors**: Only when parity is configured
- **Network Sensors**: Only when network interface data is available

## Performance Considerations

### Entity Creation Strategy
- Entities are created dynamically based on available hardware/services
- Unused entities are not created to reduce overhead
- Entity availability is checked before creation

### Update Optimization
- Critical entities update every 60 seconds
- High-priority entities update every 2 minutes
- Medium-priority entities update every 5 minutes
- Low-priority entities update every 15 minutes
- Disk-related entities follow separate configurable interval

### Caching Strategy
- Static data cached for 1 hour
- Semi-dynamic data cached for 2-10 minutes
- Real-time data cached for 15 seconds to 1 minute
- Cache cleanup prevents memory issues

This entity inventory provides a complete reference for developers creating Unraid integrations, ensuring consistency in entity naming, attributes, and behavior across different implementations.
