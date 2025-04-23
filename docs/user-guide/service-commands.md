# How to Use Unraid Service Commands

This page provides detailed information about the service commands available in the Unraid Integration for Home Assistant and how to use them effectively.

## Understanding Service Commands

The Unraid integration provides several service commands that allow you to control your Unraid server and its features from Home Assistant. These commands can be used in automations, scripts, or triggered manually from the Developer Tools.

## Finding Your Entry ID

Before using any of the service commands, you'll need to know your Unraid integration's `entry_id`. This is a unique identifier for your Unraid server instance in Home Assistant.

To find your entry_id:

1. Go to Configuration → Integrations
2. Find your Unraid integration
3. Click on your device entity
4. Click on UNRAID under Device Info
5. The long string in the URL is your entry_id
   * Example URL: `/config/integrations/integration/unraid#config_entry/1234abcd5678efgh`
   * Your entry_id would be: `1234abcd5678efgh`

## Available Service Commands

### Basic Command Execution

#### Execute Command

```yaml
service: unraid.execute_command
data:
  entry_id: your_entry_id
  command: "your_command_here"
```

This service lets you run any shell command on your Unraid server. For example:

```yaml
service: unraid.execute_command
data:
  entry_id: your_entry_id
  command: "ls -la /mnt/user/data"
```

#### Execute Command in Background

```yaml
service: unraid.execute_command
data:
  entry_id: your_entry_id
  command: "your_command_here"
  background: true
```

This runs a command in the background, allowing it to continue running after the service call completes. Useful for long-running operations.

### User Scripts

#### Execute User Script

```yaml
service: unraid.execute_user_script
data:
  entry_id: your_entry_id
  script_name: "script_name.sh"
```

This service runs a user script that has been created in the Unraid User Scripts plugin. The `script_name` must match exactly as it appears in the User Scripts plugin.

#### Stop User Script

```yaml
service: unraid.stop_user_script
data:
  entry_id: your_entry_id
  script_name: "script_name.sh"
```

This service stops a running user script.

### System Commands

#### System Reboot

```yaml
service: unraid.system_reboot
data:
  entry_id: your_entry_id
```

This service safely reboots your Unraid server.

#### System Shutdown

```yaml
service: unraid.system_shutdown
data:
  entry_id: your_entry_id
```

This service safely shuts down your Unraid server.

#### Array Stop

```yaml
service: unraid.array_stop
data:
  entry_id: your_entry_id
```

This service safely stops the Unraid array.

### Docker Container Management

#### Docker Pause

```yaml
service: unraid.docker_pause
data:
  entry_id: your_entry_id
  container: "container_name"
```

This service pauses a running Docker container (freezes its processes without stopping it).

#### Docker Resume

```yaml
service: unraid.docker_resume
data:
  entry_id: your_entry_id
  container: "container_name"
```

This service resumes a paused Docker container.

#### Docker Restart

```yaml
service: unraid.docker_restart
data:
  entry_id: your_entry_id
  container: "container_name"
```

This service gracefully restarts a Docker container.

#### Execute in Container

```yaml
service: unraid.execute_in_container
data:
  entry_id: your_entry_id
  container: "container_name"
  command: "command_to_run"
```

This service executes a command inside a running Docker container.

### VM Management

#### VM Pause

```yaml
service: unraid.vm_pause
data:
  entry_id: your_entry_id
  vm_name: "vm_name"
```

This service pauses a running virtual machine.

#### VM Resume

```yaml
service: unraid.vm_resume
data:
  entry_id: your_entry_id
  vm_name: "vm_name"
```

This service resumes a paused virtual machine.

#### VM Restart

```yaml
service: unraid.vm_restart
data:
  entry_id: your_entry_id
  vm_name: "vm_name"
```

This service gracefully restarts a virtual machine.

#### VM Hibernate

```yaml
service: unraid.vm_hibernate
data:
  entry_id: your_entry_id
  vm_name: "vm_name"
```

This service hibernates a virtual machine (suspends to disk).

#### VM Force Stop

```yaml
service: unraid.vm_force_stop
data:
  entry_id: your_entry_id
  vm_name: "vm_name"
```

This service forcefully stops a virtual machine. Use with caution as it's equivalent to pulling the power plug.

## Using Services in Automations

Service commands are most powerful when used in automations. Here are some examples:

### Weekly Maintenance Reboot

```yaml
automation:
  - alias: "Weekly Unraid Reboot"
    trigger:
      - platform: time
        at: "04:00:00"
    condition:
      - condition: time
        weekday:
          - mon
    action:
      - service: unraid.system_reboot
        data:
          entry_id: your_entry_id
```

### Execute Backup Script When Home Assistant Starts

```yaml
automation:
  - alias: "Run Backup After HA Start"
    trigger:
      - platform: homeassistant
        event: start
    action:
      - delay: "00:05:00"  # Wait 5 minutes after startup
      - service: unraid.execute_user_script
        data:
          entry_id: your_entry_id
          script_name: "backup_ha.sh"
```

### Restart a Problematic Container

```yaml
automation:
  - alias: "Restart Container on Error"
    trigger:
      - platform: state
        entity_id: binary_sensor.container_health
        to: "off"
    action:
      - service: unraid.docker_restart
        data:
          entry_id: your_entry_id
          container: "problematic_container"
```

## Tips for Working with Services

### Error Handling

Always consider what might happen if a service command fails. For critical operations, consider:

- Setting up notifications to alert you of failures
- Adding conditional checks before executing commands
- Testing thoroughly before relying on automations

### Sequencing Commands

When executing multiple commands in sequence, use the `delay` action to ensure each command has time to complete:

```yaml
action:
  - service: unraid.execute_command
    data:
      entry_id: your_entry_id
      command: "first_command"
  - delay: "00:00:10"  # Wait 10 seconds
  - service: unraid.execute_command
    data:
      entry_id: your_entry_id
      command: "second_command"
```

### Command Security

Be cautious with the commands you execute on your Unraid server. Avoid:

- Commands that could compromise system security
- Commands that could cause data loss
- Commands with hardcoded sensitive information

Instead, consider:
- Using environment variables for sensitive information
- Creating specific user scripts with limited capabilities
- Testing commands manually before automation

## Troubleshooting

If you encounter issues with service commands:

1. **Check Logs**: Look at Home Assistant logs for error messages
2. **Verify Entry ID**: Make sure your entry_id is correct
3. **Test Manually**: Try running the command directly on Unraid
4. **Check Permissions**: Ensure your user has permissions to execute the command
5. **Verify Command Syntax**: Double-check command syntax and escape special characters 