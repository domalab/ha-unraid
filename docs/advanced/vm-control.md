# VM Control

The Unraid Integration provides comprehensive capabilities for monitoring and controlling virtual machines (VMs) running on your Unraid server. This guide explains how to effectively use these features.

## Available Features

The VM management features include:

- **Status Monitoring**: Real-time status of VMs (running, stopped, paused)
- **Basic Controls**: Start and stop VMs through switches
- **Advanced Controls**: Pause, resume, hibernate, restart, and force stop VMs through services
- **VM Resource Monitoring**: Track CPU and memory usage (where available)

## VM Switches

Each virtual machine on your Unraid server will appear as a switch entity in Home Assistant. The entity ID will be in the format `switch.unraid_vm_[vm_name]`, where `[vm_name]` is the name of your VM with special characters replaced.

### Using VM Switches

VM switches provide basic on/off functionality:

- **Turn On**: Starts the VM if it's stopped
- **Turn Off**: Gracefully stops the VM if it's running

You can use these switches in the Home Assistant UI, automations, scripts, and scenes like any other switch entity.

```yaml
# Example: Turn on a VM
service: switch.turn_on
target:
  entity_id: switch.unraid_vm_windows_10
```

```yaml
# Example: Turn off a VM
service: switch.turn_off
target:
  entity_id: switch.unraid_vm_ubuntu_server
```

## Advanced VM Controls

For more advanced control, the integration provides several services:

### Pause a VM

Pauses a running VM (freezes the VM's state in memory):

```yaml
service: unraid.vm_pause
data:
  entry_id: your_entry_id
  vm_name: vm_name
```

### Resume a VM

Resumes a paused VM:

```yaml
service: unraid.vm_resume
data:
  entry_id: your_entry_id
  vm_name: vm_name
```

### Restart a VM

Gracefully restarts a running VM:

```yaml
service: unraid.vm_restart
data:
  entry_id: your_entry_id
  vm_name: vm_name
```

### Hibernate a VM

Hibernates a running VM (suspends to disk):

```yaml
service: unraid.vm_hibernate
data:
  entry_id: your_entry_id
  vm_name: vm_name
```

### Force Stop a VM

Forcefully stops a VM (equivalent to pulling the power plug):

```yaml
service: unraid.vm_force_stop
data:
  entry_id: your_entry_id
  vm_name: vm_name
```

!!! warning "Force Stop"
    Using force stop should be a last resort as it may lead to data corruption or file system issues. Only use it when a VM is unresponsive to normal shutdown methods.

!!! note "VM Names"
    The `vm_name` parameter should match the exact VM name as shown in the Unraid VM Manager, not the Home Assistant entity name.

## Best Practices

### VM Management

1. **Graceful Shutdown**: Always use proper shutdown methods when possible to prevent data corruption
2. **Status Verification**: Check VM status before sending commands
3. **Resource Awareness**: Be mindful of starting resource-intensive VMs simultaneously
4. **State Transitions**: Allow VMs sufficient time to complete start/stop operations before sending additional commands

### VM Naming

For best compatibility with Home Assistant:

1. Use simple, consistent naming for VMs in Unraid
2. Avoid special characters in VM names
3. Be aware that entity IDs in Home Assistant will convert spaces and special characters to underscores

## Automation Ideas

### Scheduled VM Power Management

```yaml
automation:
  - alias: "Start VM for Backup"
    trigger:
      - platform: time
        at: "01:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - wed
          - fri
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unraid_vm_backup_server
      - delay: "00:10:00"  # Allow 10 minutes for VM to boot fully
      - service: unraid.execute_command
        data:
          entry_id: your_entry_id
          command: "ssh backup@backup-vm '/usr/local/bin/start_backup.sh'"
      - delay: "02:00:00"  # Allow 2 hours for backup to complete
      - service: switch.turn_off
        target:
          entity_id: switch.unraid_vm_backup_server
```

### Power Management Based on Presence

```yaml
automation:
  - alias: "Start Gaming VM When Home"
    trigger:
      - platform: state
        entity_id: person.gamer
        from: "not_home"
        to: "home"
    condition:
      - condition: time
        after: "17:00:00"
        before: "23:00:00"
      - condition: state
        entity_id: switch.unraid_vm_gaming
        state: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unraid_vm_gaming
      - service: notify.mobile_app
        data:
          title: "Gaming VM Started"
          message: "Your gaming VM is starting up and will be ready in a few minutes."
```

### Resource-Based VM Management

```yaml
automation:
  - alias: "Hibernate VMs on High Server Load"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_cpu_usage
        above: 85
        for:
          minutes: 10
    action:
      - service: unraid.vm_hibernate
        data:
          entry_id: your_entry_id
          vm_name: "non_critical_vm"
      - service: notify.mobile_app
        data:
          title: "VM Hibernated"
          message: "Non-critical VM has been hibernated due to high server load."
```

### Recovery Automations

```yaml
automation:
  - alias: "Restart Frozen VM"
    trigger:
      - platform: state
        entity_id: binary_sensor.unraid_vm_frozen
        to: "on"
        for:
          minutes: 5
    action:
      - service: unraid.vm_force_stop
        data:
          entry_id: your_entry_id
          vm_name: "problematic_vm"
      - delay: "00:00:30"
      - service: switch.turn_on
        target:
          entity_id: switch.unraid_vm_problematic_vm
      - service: notify.mobile_app
        data:
          title: "VM Restarted"
          message: "A frozen VM has been forcefully restarted."
```

## Troubleshooting

### VM Controls Not Working

If you're having issues controlling VMs:

1. **Check VM Service**: Ensure VM service is running on your Unraid server
2. **Libvirt Status**: Verify libvirt service is active
3. **Check Permissions**: Make sure your Unraid user has permissions to control VMs
4. **VM State**: The VM might be in a transitional state, check Unraid UI
5. **SSH Connection**: Verify the SSH connection between Home Assistant and Unraid is working

### Delayed Status Updates

If VM status doesn't update promptly:

1. **Update Interval**: The status may not update until the next polling interval
2. **UI Refresh**: Try refreshing the Home Assistant UI
3. **Restart Integration**: In extreme cases, try reloading the integration

### Status Showing Incorrect State

If VM status seems incorrect:

1. **Check Unraid UI**: Verify the actual VM state in Unraid VM Manager
2. **State Transitions**: During state transitions, status might temporarily report incorrectly
3. **Reload Integration**: Try reloading the Unraid integration

## Advanced Configuration

For advanced users, consider:

1. **Custom Scripts**: Create VM management scripts on your Unraid server
2. **Conditional Automations**: Create complex VM management based on multiple conditions
3. **VM Templates**: Use template VMs in Unraid that can be cloned and started through Home Assistant 