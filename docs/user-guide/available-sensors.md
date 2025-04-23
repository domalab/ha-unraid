# Available Sensors

This page provides detailed information about all the sensors available in the Unraid Integration for Home Assistant.

## System Sensors

### CPU Sensors

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| CPU Usage | `sensor.unraid_cpu_usage` | Current CPU utilization percentage | % |

### Memory Sensors

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| RAM Usage | `sensor.unraid_ram_usage` | Current RAM usage | GB |
| Memory Usage | `sensor.unraid_memory_usage` | Current RAM usage percentage | % |

### System Status Sensors

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Array Status | `sensor.unraid_array_status` | Current status of the array | - |
| Uptime | `sensor.unraid_uptime` | How long the system has been running | Hours |

### Temperature Sensors

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| CPU Temperature | `sensor.unraid_cpu_temp` | Current CPU temperature | °C |
| Motherboard Temperature | `sensor.unraid_motherboard_temp` | Current motherboard temperature | °C |

### Storage Sensors

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Docker VDisk | `sensor.unraid_docker_vdisk` | Docker virtual disk usage | % |
| Log File System | `sensor.unraid_log_filesystem` | Log file system usage | % |
| Boot Usage | `sensor.unraid_boot_usage` | Boot partition usage | % |

### Fan Sensors

Fan sensors are dynamically created based on the available hardware:

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Fan Speed | `sensor.unraid_fan_[id]` | Fan speed for the fan with id | RPM |

## Storage Sensors

### Array Sensor

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Array | `sensor.unraid_array` | Array usage and information | % |

### Individual Disk Sensors

For each disk in your Unraid array (only spinning drives), the following sensor will be available:

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Disk | `sensor.unraid_disk_[name]` | Usage and information for the disk | % |

### Pool Sensors

For each cache pool in your Unraid system:

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Pool | `sensor.unraid_pool_[name]` | Usage and information for the pool | % |

## Network Sensors

For each network interface that's connected and meets criteria:

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| Network Inbound | `sensor.unraid_network_[interface]_inbound` | Inbound traffic rate for the interface | MB/s |
| Network Outbound | `sensor.unraid_network_[interface]_outbound` | Outbound traffic rate for the interface | MB/s |

## UPS Sensors

If you have a UPS connected to your Unraid server and NOMPOWER attribute is available:

| Sensor | Entity ID | Description | Unit |
|--------|-----------|-------------|------|
| UPS Server Power | `sensor.unraid_ups_server_power` | Current power consumption | W |

## Binary Sensors

The integration provides several binary sensors:

| Binary Sensor | Entity ID | Description |
|---------------|-----------|-------------|
| Server Connection | `binary_sensor.unraid_server_connection` | Whether the server is reachable |
| Docker Service | `binary_sensor.unraid_docker_service` | Whether the Docker service is running |
| VM Service | `binary_sensor.unraid_vm_service` | Whether the VM service is running |
| UPS | `binary_sensor.unraid_ups` | Whether the UPS is online (if configured) |
| Parity Check | `binary_sensor.unraid_parity_check` | Whether a parity check is running |
| Parity Disk | `binary_sensor.unraid_parity_disk` | Health status of the parity disk |

### Individual Disk Health Sensors

For each disk in the array and pool:

| Binary Sensor | Entity ID | Description |
|---------------|-----------|-------------|
| Array Disk Health | `binary_sensor.unraid_disk_[name]` | Health status of the array disk |
| Pool Disk Health | `binary_sensor.unraid_pool_[name]` | Health status of the pool disk |

## Using Sensors in Automations

These sensors can be used in automations to trigger actions based on system conditions. For example:

```yaml
automation:
  - alias: "Low Disk Space Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_array
        above: 85
    action:
      - service: notify.mobile_app
        data:
          title: "Unraid Disk Space Warning"
          message: "Your Unraid array is over 85% full. Consider freeing up some space."
```

See the [Examples](../advanced/examples.md) page for more automation ideas using these sensors. 