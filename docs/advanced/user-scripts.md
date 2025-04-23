# User Scripts

The Unraid Integration allows you to execute and manage user scripts on your Unraid server directly from Home Assistant. This guide explains how to effectively use these features.

## Understanding User Scripts

Unraid user scripts are custom scripts created on your Unraid server, typically stored in the `/boot/config/plugins/user.scripts/scripts/` directory. These scripts can perform various tasks, from system maintenance to automated backups and more.

## Available Features

The user script management features include:

- **Script Execution**: Run user scripts remotely from Home Assistant
- **Script Termination**: Stop running scripts
- **Execution Status**: Monitor script execution status
- **Button Controls**: Optional buttons to trigger scripts directly from the UI

## Accessing User Scripts

The integration accesses user scripts that are set up in the Unraid "User Scripts" plugin. If you don't already have this plugin installed on your Unraid server, you'll need to:

1. Open your Unraid Web UI
2. Go to "Apps" (Community Applications)
3. Search for "User Scripts"
4. Install the User Scripts plugin
5. Create your scripts using the plugin interface

## Executing User Scripts

You can execute a user script using the `unraid.execute_user_script` service:

```yaml
service: unraid.execute_user_script
data:
  entry_id: your_entry_id
  script_name: "script_name.sh"
```

Where:
- `your_entry_id` is your Unraid integration entry ID
- `script_name.sh` is the exact name of the script as shown in the User Scripts plugin

### Example: Run a Backup Script

```yaml
service: unraid.execute_user_script
data:
  entry_id: your_entry_id
  script_name: "backup_appdata.sh"
```

## Stopping User Scripts

If you need to stop a running script, you can use the `unraid.stop_user_script` service:

```yaml
service: unraid.stop_user_script
data:
  entry_id: your_entry_id
  script_name: "script_name.sh"
```

!!! warning "Script Termination"
    Forcefully stopping a script may leave background processes running or resources allocated. Use this feature with caution.

## Button Controls

The integration can optionally create button entities for your user scripts, making them easily accessible from the Home Assistant UI. This feature is disabled by default.

To enable buttons for user scripts:

1. Go to Configuration → Integrations
2. Find the Unraid integration
3. Click "Options"
4. Enable the "Create buttons for user scripts" option
5. Save your changes

Once enabled, each user script will appear as a button entity in Home Assistant. The entity ID will follow the format `button.unraid_script_[script_name]`.

## Best Practices

### Script Creation

1. **Error Handling**: Include proper error handling in your scripts
2. **Logging**: Add logging to help with troubleshooting
3. **Idempotence**: Scripts should be idempotent (can be run multiple times without side effects)
4. **Status Indication**: Return proper exit codes to indicate success or failure

### Example Script Structure

Here's a recommended structure for Unraid user scripts:

```bash
#!/bin/bash
# Description: My Useful Script
# Author: Your Name
# Date: YYYY-MM-DD

# Setup error handling
set -e
trap 'echo "Error occurred at line $LINENO"; exit 1' ERR

# Log start
echo "Starting script $(basename "$0") at $(date)"

# Main script content
# ...

# Log completion
echo "Script completed successfully at $(date)"
exit 0
```

## Automation Examples

### Scheduled Backup with Notification

```yaml
automation:
  - alias: "Weekly Appdata Backup"
    trigger:
      - platform: time
        at: "03:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: unraid.execute_user_script
        data:
          entry_id: your_entry_id
          script_name: "backup_appdata.sh"
      - service: notify.mobile_app
        data:
          title: "Backup Started"
          message: "Weekly appdata backup has started."
```

### User Script with Parameter Passing

While the integration doesn't directly support passing parameters to user scripts, you can work around this by:

1. Creating multiple scripts for different parameter sets
2. Using environment variables in your scripts
3. Creating a wrapper script that accepts parameters via environment variables

Example wrapper script:

```bash
#!/bin/bash
# File: backup_with_params.sh

# Default values
BACKUP_DESTINATION="/mnt/user/backups"
COMPRESSION_LEVEL="9"

# Override with environment variables if they exist
[ -n "$CUSTOM_DESTINATION" ] && BACKUP_DESTINATION="$CUSTOM_DESTINATION"
[ -n "$CUSTOM_COMPRESSION" ] && COMPRESSION_LEVEL="$CUSTOM_COMPRESSION"

# Execute the actual backup with parameters
/mnt/user/scripts/actual_backup.sh "$BACKUP_DESTINATION" "$COMPRESSION_LEVEL"
```

Then in Home Assistant:

```yaml
service: unraid.execute_command
data:
  entry_id: your_entry_id
  command: "CUSTOM_DESTINATION='/mnt/user/special' CUSTOM_COMPRESSION='5' /boot/config/plugins/user.scripts/scripts/backup_with_params.sh"
```

## Troubleshooting

### Script Not Found

If you get a "Script not found" error:

1. **Check Name**: Verify the exact script name (case-sensitive)
2. **Plugin Installed**: Make sure the User Scripts plugin is installed on Unraid
3. **Script Location**: Verify the script is properly registered in the User Scripts plugin

### Script Execution Fails

If the script runs but fails:

1. **Script Permissions**: Ensure the script has execute permissions (`chmod +x script.sh`)
2. **Error Handling**: Check if your script has proper error handling
3. **Dependencies**: Verify all required dependencies are installed
4. **Unraid UI**: Try running the script directly from the Unraid UI to see specific errors

### Finding Your Entry ID

Not sure what your entry_id is? Here's how to find it:

1. Go to Configuration → Integrations
2. Find your Unraid integration
3. Click on your device entity
4. Click on UNRAID under Device Info
5. The long string in the URL is your entry_id
   * Example URL: `/config/integrations/integration/unraid#config_entry/1234abcd5678efgh`
   * Your entry_id would be: `1234abcd5678efgh`

## Advanced Usage

### Creating Complex Scripts

For more complex operations, consider:

1. **Bash Functions**: Organize your code into functions
2. **External Dependencies**: Use tools and scripts already available on Unraid
3. **Status Files**: Use status files to track long-running operations
4. **Locking**: Implement file locks to prevent concurrent execution

### Monitoring Script Execution

For long-running scripts, you can:

1. **Create Status Sensors**: Have scripts update a file that Home Assistant monitors
2. **Log Parsing**: Parse script logs for status updates
3. **Completion Notification**: Have scripts trigger a Home Assistant webhook upon completion 