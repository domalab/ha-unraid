# Installation Guide

This page guides you through the installation and initial configuration of the Unraid Integration for Home Assistant.

## Prerequisites

Before you begin, ensure:

1. You have Home Assistant installed and running
2. Your Unraid server is operational and accessible on your network
3. **SSH is enabled on your Unraid server** (this is disabled by default)

!!! warning "SSH must be enabled"
    SSH is disabled by default in Unraid. You need to enable it in Settings → Management Access before using this integration.

## Installation Methods

There are two ways to install the Unraid Integration:

### HACS (Recommended)

The easiest way to install the integration is through HACS (Home Assistant Community Store):

1. Ensure HACS is installed in your Home Assistant instance
2. Go to HACS → Integrations → + Explore & Add Repositories
3. Search for "Unraid"
4. Click on "Unraid Integration" in the search results
5. Click "Download"
6. Restart Home Assistant

Alternatively, you can use this button to add the repository directly:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=ha-unraid&category=integration)

### Manual Installation

If you prefer to install the integration manually:

1. Download the latest release from the [GitHub repository](https://github.com/domalab/ha-unraid)
2. Extract the `unraid` folder from the archive
3. Copy the `unraid` folder to your Home Assistant `/config/custom_components/` directory
4. Restart Home Assistant

## Configuration

Once the integration is installed, you need to add and configure it:

1. Go to Home Assistant → Settings → Devices & Services
2. Click the "+ ADD INTEGRATION" button
3. Search for "Unraid" and select it
4. Fill in the configuration form:
   - **Host**: The IP address or hostname of your Unraid server
   - **Username**: Your Unraid username (usually 'root')
   - **Password**: Your Unraid password
   - **Port**: SSH port (usually 22)
   - **General Update Interval**: How often to update non-disk sensors (1-60 minutes, default: 5)
   - **Disk Update Interval**: How often to update disk information (1-24 hours, default: 1)
5. Click "Submit"

!!! tip "Update intervals"
    Setting lower intervals will provide more up-to-date information but may increase system load. For most users, the default values are a good balance.

## Verifying the Installation

After completing the configuration, you should see the Unraid integration in your Home Assistant instance:

1. Go to Settings → Devices & Services
2. Find the Unraid integration in the list
3. You should see your Unraid server as a device
4. Explore the available entities under the device

## Troubleshooting

If you encounter issues during installation or configuration:

1. Ensure SSH is enabled on your Unraid server
2. Verify your username and password are correct
3. Check that the hostname/IP address is accessible from your Home Assistant instance
4. Make sure the SSH port (usually 22) is not blocked by a firewall
5. Check the Home Assistant logs for error messages

For more troubleshooting tips, see the [Troubleshooting](troubleshooting.md) page.

## Next Steps

Once installation is complete, you can:

- Explore the [Features](features.md) of the integration
- Set up [Docker Container Management](../advanced/docker-management.md)
- Configure [VM Control](../advanced/vm-control.md)
- Check out [Example Automations](../advanced/examples.md) 