# Unraid Integration for Home Assistant

[![HACS Integration][hacsbadge]][hacs]
[![GitHub Last Commit](https://img.shields.io/github/last-commit/domalab/ha-unraid)](https://github.com/domalab/ha-unraid/commits/main)
[![Community Forum](https://img.shields.io/badge/Community-Forum-blue)](https://community.home-assistant.io/t/unraid-integration)
[![License](https://img.shields.io/github/license/domalab/ha-unraid)](./LICENSE)
[![Documentation](https://img.shields.io/badge/Documentation-GitHub%20Pages-blue)](https://domalab.github.io/ha-unraid/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/domalab/ha-unraid)

This custom integration allows you to monitor and control your Unraid server from Home Assistant. Unraid is a popular NAS (Network Attached Storage) operating system that provides flexible storage, virtualization, and application support.

## ⚠️ Project Status Update

Due to time constraints, I am no longer able to actively develop and support this integration. 

### Recommended Alternative

I encourage users to check out **[chris-mc1's Unraid API integration](https://github.com/chris-mc1/unraid_api)**, which is under active development and provides an alternative solution for integrating Unraid with Home Assistant.

### What this means

- This repository will remain available for reference and forking
- No new features or bug fixes will be implemented
- Pull requests may not be reviewed or merged
- Issues will not be actively addressed

Thank you for your understanding and support. I hope the recommended alternative integration serves your needs well.

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

## Development Environment

This project provides a complete development environment using Visual Studio Code Dev Containers, making it easy for contributors to get started with a fully configured Home Assistant development setup.

### Prerequisites

Before setting up the development environment, ensure you have the following installed:

- **Docker**: Required for running the development container
  - [Install Docker Desktop](https://docs.docker.com/get-docker/) (Windows/Mac)
  - [Install Docker Engine](https://docs.docker.com/engine/install/) (Linux)
- **Visual Studio Code**: The primary development environment
  - [Download VS Code](https://code.visualstudio.com/)
- **Dev Containers Extension**: Enables devcontainer support in VS Code
  - [Install Dev Containers Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Devcontainer Setup

The project includes a pre-configured development container that provides:
- Python 3.13 environment
- Home Assistant with debugging capabilities
- Pre-installed development dependencies (ruff, colorlog, asyncssh)
- VS Code extensions for Python development, linting, and GitHub integration
- Automatic port forwarding for Home Assistant (port 8123)

#### Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/domalab/ha-unraid.git
   cd ha-unraid
   ```

2. **Open in VS Code**:
   ```bash
   code .
   ```

3. **Open in Dev Container**:
   - When VS Code opens, you should see a notification to "Reopen in Container"
   - Alternatively, press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac) and select "Dev Containers: Reopen in Container"
   - Or click the green button in the bottom-left corner and select "Reopen in Container"

4. **Wait for container setup**:
   - The container will build and install dependencies automatically
   - The `scripts/setup` command runs automatically to install Python requirements

### Development Workflow

#### Starting Home Assistant for Testing

The development environment includes a dedicated script to run Home Assistant with the integration loaded:

```bash
scripts/develop
```

This command:
- Creates a `config` directory if it doesn't exist
- Initializes Home Assistant configuration
- Sets up the Python path to include the custom components
- Starts Home Assistant in debug mode with the integration loaded
- Makes Home Assistant available at `http://localhost:8123`

#### Code Formatting and Linting

The project uses Ruff for code formatting and linting:

```bash
scripts/lint
```

This command:
- Formats code according to project standards
- Fixes linting issues automatically where possible
- Should be run before committing changes

#### Testing the Integration

1. **Start the development environment**:
   ```bash
   scripts/develop
   ```

2. **Access Home Assistant**:
   - Open your browser to `http://localhost:8123`
   - Complete the initial Home Assistant setup if prompted

3. **Add the Unraid integration**:
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "Unraid" and configure with your Unraid server details

4. **Debug and develop**:
   - The integration runs with debug logging enabled
   - Check the Home Assistant logs for detailed information
   - Make changes to the code and restart Home Assistant to test

### Configuration and Files

#### Key Development Files

- **`.devcontainer.json`**: Defines the development container configuration
- **`config/configuration.yaml`**: Home Assistant configuration for development
- **`scripts/setup`**: Installs Python dependencies
- **`scripts/develop`**: Starts Home Assistant in development mode
- **`scripts/lint`**: Formats and lints the code
- **`requirements.txt`**: Python dependencies for development

#### Development Configuration

The development Home Assistant instance is configured with:
- Debug mode enabled
- Debug logging for the Unraid integration
- Default Home Assistant integrations loaded
- Custom components path set to include this project

### Additional Developer Resources

#### Available Commands

- **Setup environment**: `scripts/setup`
- **Start development server**: `scripts/develop`
- **Format and lint code**: `scripts/lint`

#### Development Tips

- **Hot reload**: Restart Home Assistant to see code changes
- **Debugging**: Use VS Code's integrated debugger with the Python extension
- **Logging**: Check Home Assistant logs for integration-specific debug information
- **Testing**: Test with a real Unraid server or mock the SSH connections for unit testing

#### VS Code Extensions Included

The devcontainer automatically installs these helpful extensions:
- **Ruff**: Python linting and formatting
- **Python & Pylance**: Python language support and IntelliSense
- **GitHub Pull Requests**: GitHub integration for pull requests
- **Coverage Gutters**: Code coverage visualization

#### Port Forwarding

The development container automatically forwards:
- **Port 8123**: Home Assistant web interface

## Contributing

Contributions to this integration are welcome. Please fork the repository and submit a pull request with your changes. Make sure to follow the contribution guidelines and use the development environment described above. See our [Contributing Guide](https://domalab.github.io/ha-unraid/development/contributing/) for more details.

### Development Workflow for Contributors

1. Set up the development environment using the instructions above
2. Create a new branch for your feature or bug fix
3. Make your changes and test them using `scripts/develop`
4. Run `scripts/lint` to ensure code quality
5. Test your changes thoroughly with a real Unraid server
6. Submit a pull request with a clear description of your changes

## License

This integration is released under the Apache License.

## Disclaimer

This integration is not officially associated with or endorsed by UNRAID. UNRAID trademarks belong to UNRAID, and this integration is independently developed.

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg
