# Features Overview

The Unraid Integration for Home Assistant provides comprehensive monitoring and control capabilities for your Unraid server. This page outlines the main features and functionality of the integration.

## System Monitoring

### CPU and Memory Sensors

The integration provides detailed information about your Unraid server's CPU and memory usage:

- **CPU Usage**: Shows the current CPU utilization percentage
- **Memory Usage**: Displays the current RAM usage percentage
- **CPU Load**: Shows 1, 5, and 15-minute load averages

### Temperature Sensors

Monitor various temperature readings from your Unraid server:

- **CPU Temperature**: Shows the temperature of your processor
- **Motherboard Temperature**: Displays the temperature of your motherboard
- **Component-specific Temperatures**: Where available, shows temperatures for other components

### System Fans

Monitor the speed of system fans:

- **Fan RPM**: Shows the rotation speed of various fans in your system
- **Fan Status**: Indicates whether fans are operational

### Storage Monitoring

Comprehensive monitoring of your Unraid storage arrays and disks:

- **Array Usage**: Shows the overall array usage percentage
- **Cache Usage**: Displays the usage of cache drives
- **Individual Disk Usage**: Provides usage information for each disk in the array
- **Disk Health**: Displays disk health information (where available)

### Uptime and System Info

Basic system information and status indicators:

- **Uptime**: Shows how long the Unraid server has been running
- **Version**: Displays the Unraid OS version
- **Array Status**: Indicates whether the array is started or stopped

### UPS Monitoring

If you have a UPS connected to your Unraid server:

- **UPS Status**: Online, on battery, or other status
- **Battery Level**: Current battery charge percentage
- **Estimated Runtime**: Time remaining on battery power
- **Input Voltage**: Current input voltage
- **Load Percentage**: UPS load percentage
- **Power Consumption**: Current power consumption (where supported)

## Control Features

### Docker Container Management

Comprehensive Docker container control capabilities:

- **Container Status**: Monitor whether containers are running or stopped
- **Container Switches**: Start and stop containers directly from Home Assistant
- **Advanced Controls**: Pause, resume, and restart containers
- **Command Execution**: Run commands inside containers

### Virtual Machine Control

Complete VM management capabilities:

- **VM Status**: Monitor whether VMs are running, stopped, or paused
- **VM Switches**: Start and stop VMs directly from Home Assistant
- **Advanced Controls**: Pause, resume, hibernate, restart, and force stop VMs

### Command Execution

Execute commands directly on your Unraid server:

- **Shell Commands**: Run any terminal command on the server
- **User Scripts**: Execute user-created scripts
- **Background Execution**: Run commands in the background

## System Control

Control your Unraid system directly from Home Assistant:

- **System Reboot**: Safely reboot your Unraid server
- **System Shutdown**: Safely shut down your Unraid server
- **Array Stop**: Safely stop the Unraid array

## Automation Capabilities

Create powerful automations using the Unraid integration:

- **Event-based Actions**: Trigger actions based on Unraid system events
- **Scheduled Tasks**: Schedule regular tasks on your Unraid server
- **Conditional Logic**: Create complex automations based on server state

## Diagnostics

Comprehensive diagnostic information for troubleshooting:

- **SSH Connectivity**: Validate SSH connection status
- **Disk Health**: Check for potential disk issues
- **Service Status**: Monitor status of Docker and VM services
- **UPS Diagnostics**: Detailed UPS information
- **Parity Check Status**: Monitor parity check operations

## Repair Flows

Automatic detection and guidance for common issues:

- **Connection Issues**: Help resolving connectivity problems
- **Authentication Problems**: Guidance for fixing authentication issues
- **Disk Health Issues**: Alerts for potential disk failures
- **Array Problems**: Notifications about array issues
- **Parity Check Failures**: Alerts about parity check failures

## Available Services

The integration provides several services you can call from automations:

- **unraid.execute_command**: Run a shell command on the Unraid server
- **unraid.execute_in_container**: Run a command inside a Docker container
- **unraid.execute_user_script**: Execute a user script
- **unraid.stop_user_script**: Stop a running user script
- **unraid.system_reboot**: Reboot the Unraid server
- **unraid.system_shutdown**: Shut down the Unraid server
- **unraid.array_stop**: Safely stop the Unraid array
- **unraid.docker_pause**: Pause a Docker container
- **unraid.docker_resume**: Resume a paused Docker container
- **unraid.docker_restart**: Restart a Docker container
- **unraid.vm_pause**: Pause a virtual machine
- **unraid.vm_resume**: Resume a paused virtual machine
- **unraid.vm_restart**: Restart a virtual machine
- **unraid.vm_hibernate**: Hibernate a virtual machine
- **unraid.vm_force_stop**: Force stop a virtual machine 