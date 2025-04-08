# Unraid Integration for Home Assistant

[![HACS Integration][hacsbadge]][hacs]
[![GitHub Last Commit](https://img.shields.io/github/last-commit/domalab/ha-unraid?style=for-the-badge)](https://github.com/domalab/ha-unraid/commits/main)
[![Community Forum](https://img.shields.io/badge/Community-Forum-blue?style=for-the-badge)](https://community.home-assistant.io/t/unraid-integration)
[![License](https://img.shields.io/github/license/domalab/ha-unraid?style=for-the-badge)](./LICENSE)
[![Quality Scale](https://img.shields.io/badge/Quality%20Scale-Platinum-blue?style=for-the-badge)](https://developers.home-assistant.io/docs/integration_quality_scale_index)

This custom integration allows you to monitor and control your Unraid server from Home Assistant. Unraid is a popular NAS (Network Attached Storage) operating system that provides flexible storage, virtualization, and application support.

## Features

- Monitor CPU, RAM, Boot, Cache, Array Disks, and Array usage
- Monitor CPU and Motherboard temperature
- Monitor System Fans
- Monitor UPS Connected
- Control Docker containers
- Control VMs
- Execute shell commands
- Buttons for user scripts
- Manage user scripts
- Automatic repair flows for common issues
- Advanced config flow validation
- Comprehensive diagnostics

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=ha-unraid&category=integration)

### Manual

1. Copy the `unraid` folder into your `custom_components` directory.
2. Restart Home Assistant.
3. Go to Configuration > Integrations.
4. Click the "+ ADD INTEGRATION" button.
5. Search for "Unraid" and select it.
6. Follow the configuration steps.

## Configuration

> **IMPORTANT:** SSH is disabled by default. SSH needs to be enabled on Unraid --> Settings --> Management Access

During the setup, you'll need to provide:

- Host: The IP address or hostname of your Unraid server
- Username: Your Unraid username (usually 'root')
- Password: Your Unraid password
- Port: SSH port (usually 22)
- General Update Interval (Minutes): How often to update non-disk sensors (1-60 minutes). Default is 5 minutes.
- Disk Update Interval (Hours): How often to update disk information (1-24 hours). Default is 1 hour

Note: Setting lower intervals will provide more up-to-date information but may increase system load.

## Sensors

- CPU Usage: Shows the current CPU utilization percentage.
- RAM Usage: Displays the current RAM usage percentage.
- CPU and Motherboard Temps: Shows CPU and Motherboard temperatures
- System Fans : Shows System Fans and RPM
- Array Usage: Shows the overall array usage percentage.
- Individual Array Disks: Displays usage information for each disk in the array.
- Uptime: Shows how long the Unraid server has been running.
- UPS Power: Displays information about the UPS power consumption

## Diagnostics

- UPS Status: Displays information about the connected UPS (if available).
- Disk Health: Displays disk health information
- VM and Docker Service: Displays information about docker and vm services
- SSH Connectivity: Display information about integration connected to Unraid via SSH
- Parity Check: Displays information if parity check is enabled.

## Repair Flows

The integration includes automatic repair flows for common issues:

- Connection Issues: Helps you fix connection problems to your Unraid server
- Authentication Problems: Guides you through fixing authentication issues
- Disk Health Issues: Alerts you about potential disk failures and provides guidance
- Array Problems: Notifies you about array issues and suggests solutions
- Parity Check Failures: Alerts you about parity check failures

## Config Flow Validation

The integration includes advanced validation during setup:

- Hostname/IP Validation: Ensures the hostname or IP address is in a valid format
- Port Validation: Verifies the SSH port is within a valid range (1-65535)
- Credential Validation: Ensures username and password are not empty
- Connection Testing: Tests the connection before completing setup

## Switches

- Docker Containers: Turn on/off Docker containers
- VMs: Turn on/off Virtual Machines

## Services

- `unraid.execute_command`: Execute a shell command on the Unraid server
- `unraid.execute_in_container`: Execute a command in a Docker container
- `unraid.execute_user_script`: Execute a user script
- `unraid.stop_user_script`: Stop a running user script
- `unraid.system_reboot`: Reboot Unraid
- `unraid.system_shutdown`: Shutdown Unraid

### Docker Container Services

- `unraid.docker_pause`: Pause a running Docker container
- `unraid.docker_resume`: Resume a paused Docker container
- `unraid.docker_restart`: Restart a Docker container

### VM Services

- `unraid.vm_pause`: Pause a running virtual machine
- `unraid.vm_resume`: Resume a paused virtual machine
- `unraid.vm_restart`: Restart a running virtual machine
- `unraid.vm_hibernate`: Hibernate a running virtual machine (suspend to disk)
- `unraid.vm_force_stop`: Force stop a virtual machine (equivalent to pulling the power plug)

## Buttons

- Buttons to control user scripts (Disabled by default)
- Buttons to control system reboot and shutdown (Disabled by default)

## Troubleshooting

### Connection Issues

- Ensure SSH is enabled on your Unraid server (Settings > Management Access)
- Verify the hostname/IP address is correct
- Check that the SSH port is correct (usually 22)
- Ensure your username and password are correct
- Check your network connectivity

### Performance Issues

- Increase the update intervals if the integration is causing high CPU usage
- Disable sensors you don't need
- Ensure your Unraid server has adequate resources

## Contributing

Contributions to this integration are welcome. Please fork the repository and submit a pull request with your changes. Make sure to follow the contribution guidelines.

## License

This integration is released under the Apache License.

## Disclaimer

This integration is not officially associated with or endorsed by UNRAID. UNRAID trademarks belong to UNRAID, and this integration is independently developed.

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge
