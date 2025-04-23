# Troubleshooting

This page provides solutions to common issues you might encounter when using the Unraid Integration for Home Assistant.

## Installation Issues

### Integration Not Found

**Problem**: The Unraid integration doesn't appear in the integration list.

**Solutions**:
1. Make sure you've installed the integration correctly
2. If installed via HACS, verify it shows as installed in HACS
3. Restart Home Assistant
4. Clear browser cache and reload the page

### Installation Fails

**Problem**: The installation process fails or throws errors.

**Solutions**:
1. Check Home Assistant logs for specific error messages
2. Verify you have the latest version of Home Assistant
3. Try the manual installation method if HACS installation fails
4. Make sure your custom_components directory has the correct permissions

## Connection Issues

### Can't Connect to Unraid Server

**Problem**: Home Assistant can't establish a connection to your Unraid server.

**Solutions**:
1. **Check SSH Status**: Ensure SSH is enabled on your Unraid server (Settings → Management Access)
2. **Verify Network Connectivity**: Make sure your Unraid server is online and accessible from Home Assistant
3. **Firewall Settings**: Check if any firewall is blocking SSH connections (port 22 by default)
4. **Try Different Address**: If using hostname, try using IP address instead, or vice versa
5. **Check Logs**: Review Home Assistant logs for specific error messages

### Authentication Failed

**Problem**: Connection fails due to authentication issues.

**Solutions**:
1. **Verify Credentials**: Double-check your username and password
2. **Special Characters**: If your password contains special characters, make sure they're properly escaped
3. **Change Password**: Try changing your Unraid password temporarily to something simpler (no special characters)
4. **User Permissions**: Ensure the user has sufficient permissions (usually 'root' is required)

### Connection Timeouts

**Problem**: Connection attempts timeout.

**Solutions**:
1. **Network Speed**: Check your network performance
2. **Server Load**: Verify your Unraid server isn't under heavy load
3. **Custom SSH Port**: If using a non-standard SSH port, make sure it's correctly specified
4. **MTU Settings**: Check MTU settings on your network devices

## Sensor Issues

### Missing Sensors

**Problem**: Some expected sensors don't appear.

**Solutions**:
1. **Wait for Update**: Some sensors might take time to appear after initial setup
2. **Reload Integration**: Try removing and re-adding the integration
3. **Feature Availability**: Certain sensors only appear if the feature is available on your server (e.g., UPS sensors)
4. **Check Logs**: Look for error messages related to sensor creation

### Incorrect Sensor Values

**Problem**: Sensors show incorrect or unexpected values.

**Solutions**:
1. **Update Interval**: Adjust the update interval in the integration configuration
2. **Server Load**: High server load can cause inaccurate readings
3. **Restart Integration**: Remove and re-add the integration
4. **Check Unraid Web UI**: Compare values with what's shown in the Unraid web interface

### No Updates to Sensors

**Problem**: Sensor values don't update.

**Solutions**:
1. **Check Update Interval**: Make sure the update interval isn't set too high
2. **Verify Connection**: Ensure the integration still has a connection to the server
3. **Restart Home Assistant**: Sometimes a full restart is needed
4. **Check Logs**: Look for error messages during update attempts

## Docker and VM Control Issues

### Can't Control Docker Containers

**Problem**: Docker containers can't be started, stopped, or controlled.

**Solutions**:
1. **Docker Service**: Verify Docker service is running on the Unraid server
2. **User Permissions**: Ensure the user has permissions to control Docker
3. **Container State**: The container might be in an inconsistent state; try managing it from the Unraid UI first
4. **Name Mismatch**: Container names in Home Assistant must match exactly with Unraid

### VM Controls Not Working

**Problem**: Unable to control VMs from Home Assistant.

**Solutions**:
1. **VM Service**: Make sure VM service is running on Unraid
2. **Libvirt Status**: Check if libvirt service is active
3. **VM State**: The VM might be in a transitional state
4. **Response Time**: VM operations can take time, be patient for status updates

### Delayed Responses

**Problem**: Actions take a long time to reflect in the UI.

**Solutions**:
1. **Update Interval**: Your update interval might be too long
2. **Server Load**: High server load can cause delays
3. **Network Latency**: Check your network connection
4. **Command Queue**: Multiple commands might be processing sequentially

## Service Call Issues

### Service Calls Failing

**Problem**: Service calls return errors or don't execute.

**Solutions**:
1. **Entry ID**: Make sure you're using the correct entry_id
2. **Service Parameters**: Verify all required parameters are provided
3. **Syntax**: Check for syntax errors in your service calls
4. **User Permissions**: Ensure the user has permissions to execute the commands
5. **Check Logs**: Look for specific error messages in the logs

### Finding Your Entry ID

**Problem**: You don't know your entry_id for service calls.

**Solution**:
1. Go to Configuration → Integrations
2. Find your Unraid integration
3. Click on your device entity
4. Click on UNRAID under Device Info
5. The long string in the URL is your entry_id
   * Example URL: `/config/integrations/integration/unraid#config_entry/1234abcd5678efgh`
   * Your entry_id would be: `1234abcd5678efgh`

## Performance Issues

### High CPU Usage

**Problem**: The integration causes high CPU usage on Home Assistant.

**Solutions**:
1. **Increase Intervals**: Set longer update intervals
2. **Reduce Entities**: Remove unnecessary entities if possible
3. **Check Logs**: Look for repeated errors or warnings
4. **Upgrade Hardware**: Consider upgrading your Home Assistant hardware

### Slow UI Response

**Problem**: Home Assistant UI becomes slow after adding the integration.

**Solutions**:
1. **Browser Performance**: Check browser resource usage
2. **HA Resource Usage**: Monitor Home Assistant resource usage
3. **Database Size**: Large databases can slow down performance
4. **Entity Count**: Having too many entities can impact performance

## Logs and Diagnostics

If you're still experiencing issues, check the Home Assistant logs:

1. Go to Configuration → System → Logs
2. Filter for "unraid" to see integration-specific logs
3. Look for error messages or warnings

For more detailed diagnostics:

1. Go to Configuration → Integrations
2. Find the Unraid integration
3. Click the "..." menu
4. Select "Download diagnostics"

## Still Having Issues?

If you're still experiencing problems after trying these solutions:

1. Check the [GitHub Issues](https://github.com/domalab/ha-unraid/issues) to see if others have reported similar problems
2. Open a new issue on GitHub with:
   * Detailed description of the problem
   * Steps to reproduce
   * Home Assistant logs
   * Diagnostic information
   * Your environment details (HA version, Unraid version, etc.) 