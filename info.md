# Unraid Integration for Home Assistant

This custom integration allows you to monitor and control your Unraid server from Home Assistant.

## Features

- Monitor CPU, RAM, Boot, Cache, Array Disks, and Array usage
- Monitor UPS connected to Unraid
- Control Docker containers
- Manage VMs
- Execute shell commands
- Manage user scripts

## Installation

1. Copy the `unraid` folder into your `custom_components` directory.
2. Restart Home Assistant.
3. Go to Configuration > Integrations.
4. Click the "+ ADD INTEGRATION" button.
5. Search for "Unraid" and select it.
6. Follow the configuration steps.

## Configuration

During the setup, you'll need to provide:

- Host: The IP address or hostname of your Unraid server
- Username: Your Unraid username (usually 'root')
- Password: Your Unraid password
- Port: SSH port (usually 22)
- Ping Interval: How often to check if the server is online (in seconds)
- Update Interval: How often to update sensor data (in seconds)

## Sensors

- CPU Usage
- RAM Usage
- Array Usage
- Individual Array Disks
- Uptime

## Switches

- Docker Containers: Turn on/off Docker containers
- VMs: Turn on/off Virtual Machines

## Services

- `unraid.execute_command`: Execute a shell command on the Unraid server
- `unraid.execute_in_container`: Execute a command in a Docker container
- `unraid.execute_user_script`: Execute a user script
- `unraid.stop_user_script`: Stop a running user script

## Examples

### Execute a shell command

```yaml
service: unraid.execute_command
data:
  entry_id: YOUR_ENTRY_ID
  command: "echo 'Hello from Home Assistant' > /boot/config/plugins/user.scripts/scripts/ha_test.sh"