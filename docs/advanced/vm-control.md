---
layout: default
title: VM Control
---

# Virtual Machine Management

This guide explains how to manage Virtual Machines (VMs) on your Unraid server through Home Assistant.

## Available Controls

The Unraid integration provides the following VM controls:

- View VM status
- Start/Stop VMs
- Monitor VM states
- Execute VM-related commands

## Entity Types

Each VM appears as a switch entity in Home Assistant:

```
switch.unraid_vm_[vm_name]
```

Example entities:

- `switch.unraid_vm_windows10`
- `switch.unraid_vm_ubuntu`
- `switch.unraid_vm_gameserver`

## Basic Controls

### Start VM

```yaml
# Using switch entity
service: switch.turn_on
target:
  entity_id: switch.unraid_vm_windows10

# Using service call
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "virsh start windows10"
```

### Stop VM

```yaml
# Using switch entity
service: switch.turn_off
target:
  entity_id: switch.unraid_vm_windows10

# Using service call
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "virsh shutdown windows10"
```

## Advanced VM Management

### Example Automations

#### 1. Schedule VM Start/Stop

```yaml
alias: "Start Gaming VM on Weekend Evenings"
trigger:
  - platform: time
    at: "18:00:00"
condition:
  - condition: time
    weekday:
      - fri
      - sat
      - sun
action:
  - service: switch.turn_on
    target:
      entity_id: switch.unraid_vm_gameserver
```

#### 2. Power Management

```yaml
alias: "Shutdown VMs on UPS Event"
trigger:
  - platform: numeric_state
    entity_id: sensor.ups_battery_charge
    below: 50
action:
  - service: switch.turn_off
    target:
      entity_id: switch.unraid_vm_windows10
  - delay:
      minutes: 1
  - service: switch.turn_off
    target:
      entity_id: switch.unraid_vm_ubuntu
```

#### 3. VM Maintenance Schedule

```yaml
alias: "Weekly VM Maintenance"
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: switch.turn_off
    target:
      entity_id: switch.unraid_vm_windows10
  - delay:
      minutes: 5
  - service: switch.turn_on
    target:
      entity_id: switch.unraid_vm_windows10
```

## Monitoring VMs

### VM Status

Monitor VM status through the switch entity's state:

- `on` = VM is running
- `off` = VM is stopped

### Check VM Status

```yaml
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "virsh list --all"
```

## Best Practices

1. **Graceful Shutdown**
   - Always use graceful shutdown when possible
   - Allow sufficient time for OS shutdown
   - Monitor shutdown completion

2. **Resource Management**
   - Monitor VM resource usage
   - Schedule intensive tasks appropriately
   - Balance VM workloads

3. **Error Handling**
   - Implement proper error checking
   - Add notification on failures
   - Log important events

4. **Startup/Shutdown Order**
   - Consider dependencies between VMs
   - Implement proper delays
   - Verify successful state changes

## Common VM Operations

### Force Stop VM (Use with Caution)

```yaml
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "virsh destroy windows10"
```

### Check VM Information

```yaml
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "virsh dominfo windows10"
```

## Troubleshooting

1. **VM Won't Start**
   - Check VM configuration
   - Verify resource availability
   - Check Unraid logs
   - Verify permissions

2. **VM Won't Stop**
   - Try graceful shutdown first
   - Allow sufficient timeout
   - Use force stop as last resort
   - Check VM status in Unraid

3. **VM Performance Issues**
   - Monitor resource usage
   - Check for conflicts
   - Verify hardware passthrough
   - Review VM settings

## Security Considerations

1. **Access Control**
   - Limit VM control access
   - Monitor VM operations
   - Log significant events

2. **Resource Protection**
   - Set resource limits
   - Monitor usage patterns
   - Implement safeguards

3. **Network Security**
   - Configure proper network isolation
   - Monitor VM network activity
   - Implement appropriate firewalls
