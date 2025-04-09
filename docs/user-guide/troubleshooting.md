---
layout: default
title: Troubleshooting Guide
---

This guide provides solutions to common issues you might encounter with the Home Assistant Unraid Integration.

## Connection Issues

### Cannot Connect to Unraid Server

If you're having trouble connecting to your Unraid server:

1. **Check SSH Credentials**: Verify that your username and password are correct
2. **Verify SSH Access**: Try connecting to your Unraid server via SSH from another device
3. **Check Network Connectivity**: Ensure that Home Assistant can reach your Unraid server
4. **Firewall Settings**: Check if there's a firewall blocking the connection
5. **SSH Configuration**: Verify that SSH is enabled on your Unraid server

### SSH Log Spam

If you notice excessive SSH log entries in your Unraid syslog:

1. **Update to Latest Version**: The latest version includes optimizations to reduce SSH connections
2. **Increase Update Intervals**: Increase the update intervals in the integration options
3. **Disable Unused Features**: Disable monitoring for components you don't need

## Data Collection Issues

### Missing or Incorrect Disk Information

If disk information is missing or incorrect:

1. **Check Disk Permissions**: Ensure the SSH user has permissions to access disk information
2. **Verify Disk Mapping**: Check if the disk mapping is correct in the Unraid UI
3. **ZFS Support**: For ZFS-based cache pools, be aware that support is currently in development

### Temperature Sensor Issues

If temperature sensors are not working correctly:

1. **NVMe Drives**: NVMe temperature parsing is being improved in upcoming releases
2. **USB Boot Drives**: USB boot drives may not support SMART commands
3. **Check SMART Support**: Verify that your disks support SMART commands

### International Format Parsing Errors

If you see errors related to parsing speeds or dates:

1. **Log Errors**: Check the Home Assistant logs for specific parsing errors
2. **Update to Latest Version**: Fixes for international format parsing are planned

## Docker and VM Issues

### Cannot Control Docker Containers

If you're unable to control Docker containers:

1. **Docker Service**: Verify that the Docker service is running on your Unraid server
2. **Permissions**: Ensure the SSH user has permissions to control Docker
3. **Container State**: Check if the container is in a state that allows the requested operation

### VM Control Not Working

If VM control is not working:

1. **Libvirt Service**: Verify that the libvirt service is running on your Unraid server
2. **VM State**: Check if the VM is in a state that allows the requested operation
3. **Permissions**: Ensure the SSH user has permissions to control VMs

## Performance Issues

### High Resource Usage

If the integration is using too many resources:

1. **Update Intervals**: Increase the update intervals in the integration options
2. **Disable Unused Features**: Disable monitoring for components you don't need
3. **Check Cache Settings**: Verify that caching is working correctly

### Slow Updates

If updates are taking too long:

1. **Network Performance**: Check the network performance between Home Assistant and Unraid
2. **Server Load**: Verify that your Unraid server is not under heavy load
3. **Disk Performance**: Check if disk operations are slow on your Unraid server

## Reporting Issues

If you encounter an issue not covered in this guide:

1. **Check Logs**: Look for error messages in the Home Assistant logs
2. **Search Existing Issues**: Check if the issue has already been reported on [GitHub](https://github.com/domalab/ha-unraid/issues)
3. **Report New Issue**: If it's a new issue, report it on GitHub with detailed information:
   - Home Assistant version
   - Unraid version
   - Integration version
   - Error messages
   - Steps to reproduce the issue
