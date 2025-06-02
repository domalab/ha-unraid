# Unraid Integration for Home Assistant

[![HACS Integration][hacsbadge]][hacs]
[![GitHub Last Commit](https://img.shields.io/github/last-commit/domalab/ha-unraid)](https://github.com/domalab/ha-unraid/commits/main)
[![Community Forum](https://img.shields.io/badge/Community-Forum-blue)](https://community.home-assistant.io/t/unraid-integration)
[![License](https://img.shields.io/github/license/domalab/ha-unraid)](./LICENSE)
[![Documentation](https://img.shields.io/badge/Documentation-GitHub%20Pages-blue)](https://domalab.github.io/ha-unraid/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/domalab/ha-unraid)

This custom integration allows you to monitor and control your Unraid server from Home Assistant. Unraid is a popular NAS (Network Attached Storage) operating system that provides flexible storage, virtualization, and application support.

## ⚠️ Project Direction Update: Moving to GraphQL API

I wanted to share an important update regarding the future development of this integration. After careful consideration, I've decided to focus my efforts on developing a new version that utilizes Unraid's official GraphQL API instead of continuing with the current SSH-based implementation.

### Why this change?

- **Improved Reliability**: The GraphQL API provides a more stable and officially supported method of interacting with Unraid
- **Better Performance**: Direct API access should result in faster response times and less system overhead
- **Future-Proof**: As Unraid continues to develop their API, we'll benefit from new capabilities without requiring extensive rewrites
- **Reduced Edge Cases**: Many of the current integration's limitations stem from the varied environments where SSH commands can behave differently

### What this means for users

The current SSH-based integration will remain available but will enter maintenance mode. I won't be actively developing new features or addressing edge cases for it. Instead, I'm channeling those efforts into the new GraphQL-based integration, which I believe will provide a better experience for everyone in the long run.

For those who need immediate fixes for specific edge cases in the current integration, I encourage you to fork the repository and adapt it to your needs. Pull requests are still welcome and will be reviewed, though my primary development focus will be on the new approach.

### Timeline & Progress

I've already begun work on the new integration and will share updates as development progresses.

I appreciate your understanding and continued support as we move toward this improved implementation.

### Beta GraphQL Integration Available

For those interested in trying the new approach, a beta version of the GraphQL-based integration is now available! The [Unraid Connect integration](https://github.com/domalab/ha-unraid-connect) leverages Unraid's official GraphQL API and represents the future direction of this project.

**Important Notes:**

- This is currently in **beta phase** - expect some rough edges
- You can view current issues and track development progress on the GitHub repository
- Remaining issues will be addressed as the Unraid API Team releases more updates and improvements

If you're comfortable with beta software and want to help shape the future of Unraid integration with Home Assistant, give it a try.

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

## Documentation

Comprehensive documentation is available on our [Documentation Site](https://domalab.github.io/ha-unraid/):

- [Installation Guide](https://domalab.github.io/ha-unraid/user-guide/installation/)
- [Features Overview](https://domalab.github.io/ha-unraid/user-guide/features/)
- [Examples and Use Cases](https://domalab.github.io/ha-unraid/advanced/examples/)
- [Troubleshooting Guide](https://domalab.github.io/ha-unraid/user-guide/troubleshooting/)
- [Docker Management](https://domalab.github.io/ha-unraid/advanced/docker-management/)
- [VM Control](https://domalab.github.io/ha-unraid/advanced/vm-control/)
- [User Scripts](https://domalab.github.io/ha-unraid/advanced/user-scripts/)
- [Contributing Guide](https://domalab.github.io/ha-unraid/development/contributing/)

## Contributing

Contributions to this integration are welcome. Please fork the repository and submit a pull request with your changes. Make sure to follow the contribution guidelines. See our [Contributing Guide](https://domalab.github.io/ha-unraid/development/contributing/) for more details.

## License

This integration is released under the Apache License.

## Disclaimer

This integration is not officially associated with or endorsed by UNRAID. UNRAID trademarks belong to UNRAID, and this integration is independently developed.

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg
