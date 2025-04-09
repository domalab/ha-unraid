---
layout: default
title: Installation Guide
---

This guide will walk you through the process of installing and configuring the Home Assistant Unraid Integration.

## Prerequisites

- Home Assistant instance (version 2023.3.0 or newer)
- Unraid server with SSH access
- SSH credentials (username and password)
- Unraid server with SSH enabled (this is enabled by default)

## Preparing Your Unraid Server

Before installing the integration, ensure your Unraid server is properly configured:

1. **Enable SSH**: SSH should be enabled by default on Unraid. You can verify this in the Unraid web UI under Settings > Management Access.

2. **Create a Strong Password**: Ensure you have a strong password for the root user. This can be changed in the Unraid web UI under Users.

3. **Note Your Server IP**: Make note of your Unraid server's IP address. You can find this in the Unraid web UI dashboard or by running `ifconfig` in the Unraid console.

## Installation Methods

### HACS (Recommended)

1. Ensure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Go to HACS > Integrations
3. Click the "+ Explore & Download Repositories" button
4. Search for "Unraid"
5. Click on "Unraid" in the search results
6. Click "Download"
7. Restart Home Assistant

Alternatively, you can use this button to add the repository directly:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=https%3A%2F%2Fgithub.com%2Fdomalab%2Fha-unraid&category=integration)

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/domalab/ha-unraid/releases)
2. Extract the `unraid` folder into your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to Home Assistant > Settings > Devices & Services
2. Click the "+ Add Integration" button
3. Search for "Unraid" and select it
4. Enter your Unraid server details:
   - **Host**: IP address or hostname of your Unraid server
   - **Username**: SSH username (usually "root")
   - **Password**: SSH password
   - **Port**: SSH port (default is 22)
5. Click "Submit"

### Integration Discovery

The integration will automatically discover various components of your Unraid server:

- **System Information**: CPU, memory, and disk usage
- **Docker Containers**: All Docker containers running on your server
- **Virtual Machines**: All VMs configured on your server
- **User Scripts**: Any user scripts configured on your server
- **UPS**: UPS information if connected

### Configuration Options

After adding the integration, you can configure additional options:

1. Go to Settings > Devices & Services
2. Find the Unraid integration and click "Configure"
3. Adjust the following settings as needed:
   - **General Update Interval**: How often to update general system information (in minutes)
     - Default: 5 minutes
     - Recommended: 5-15 minutes
   - **Disk Update Interval**: How often to update disk information (in hours)
     - Default: 1 hour
     - Recommended: 1-6 hours
   - **UPS Monitoring**: Enable if you have a UPS connected to your Unraid server

### Performance Considerations

- **Update Intervals**: Shorter update intervals provide more current data but increase server load and network traffic
- **Disk Updates**: Disk information updates are more resource-intensive, so they're performed less frequently
- **SSH Connections**: Each update requires SSH connections to your Unraid server

## Troubleshooting

### Common Installation Issues

#### Connection Failed

If you see "Cannot connect to Unraid server" during setup:

1. **Verify SSH Credentials**: Double-check your username and password
2. **Check Network Connectivity**: Ensure Home Assistant can reach your Unraid server
   - Try pinging your Unraid server from another device on the same network
   - Check firewall settings on both Home Assistant and Unraid
3. **SSH Service**: Verify SSH is running on your Unraid server
   - In the Unraid web UI, go to Settings > Management Access
   - Ensure "SSH" is set to "Enabled"

#### Integration Not Found

If "Unraid" doesn't appear in the integrations list:

1. **HACS Installation**: Verify the integration was properly installed via HACS
2. **Restart Home Assistant**: Sometimes a restart is needed after installation
3. **Check Logs**: Look for any errors related to the integration in Home Assistant logs

### Viewing Logs

To view logs related to the integration:

1. Go to Home Assistant > Settings > System > Logs
2. Set the filter to "unraid"
3. Set the level to "Debug" for more detailed information

### Getting Help

If you're still experiencing issues:

1. Check our comprehensive [Troubleshooting Guide](troubleshooting.md)
2. Search for existing issues on the [GitHub repository](https://github.com/domalab/ha-unraid/issues)
3. Open a new issue with detailed information about your problem

When reporting issues, please include:

- Home Assistant version
- Unraid version
- Integration version
- Relevant error messages from logs
