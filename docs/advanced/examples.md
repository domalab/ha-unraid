---
layout: default
title: Examples and Use Cases
---

This page provides practical examples and use cases for the Home Assistant Unraid Integration. These examples demonstrate how to leverage the integration's features in your home automation setup.

## Monitoring Examples

### System Health Dashboard

Create a dedicated dashboard for monitoring your Unraid server's health:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Unraid System Health
    entities:
      - entity: sensor.unraid_tower_cpu_usage
      - entity: sensor.unraid_tower_memory_usage
      - entity: sensor.unraid_tower_cpu_temperature
      - entity: sensor.unraid_tower_uptime

  - type: horizontal-stack
    cards:
      - type: gauge
        name: CPU Usage
        entity: sensor.unraid_tower_cpu_usage
        min: 0
        max: 100
        severity:
          green: 0
          yellow: 50
          red: 80

      - type: gauge
        name: Memory Usage
        entity: sensor.unraid_tower_memory_usage
        min: 0
        max: 100
        severity:
          green: 0
          yellow: 70
          red: 90
```

### Disk Health Monitoring

Monitor the health of your array disks:

```yaml
type: entities
title: Unraid Disk Health
entities:
  - entity: binary_sensor.unraid_tower_array_status
  - entity: sensor.unraid_tower_array_usage
  - entity: sensor.unraid_tower_array_protection
  - type: divider
  - entity: sensor.unraid_tower_disk_disk1_temperature
  - entity: binary_sensor.unraid_tower_disk_disk1_smart_status
  - entity: sensor.unraid_tower_disk_disk1_usage
  - type: divider
  - entity: sensor.unraid_tower_disk_disk2_temperature
  - entity: binary_sensor.unraid_tower_disk_disk2_smart_status
  - entity: sensor.unraid_tower_disk_disk2_usage
```

## Automation Examples

### Notify on High CPU Temperature

Get notified when your CPU temperature exceeds a safe threshold:

```yaml
alias: Notify on High CPU Temperature
description: Send a notification when CPU temperature is too high
trigger:
  - platform: numeric_state
    entity_id: sensor.unraid_tower_cpu_temperature
    above: 75
condition: []
action:
  - service: notify.mobile_app
    data:
      title: "Unraid CPU Temperature Alert"
      message: "CPU temperature is {{ states('sensor.unraid_tower_cpu_temperature') }}°C!"
      data:
        push:
          sound: default
mode: single
```

### Restart Plex When Stuck

Automatically restart Plex when it becomes unresponsive:

```yaml
alias: Restart Plex When Stuck
description: Restart Plex container when it's not responding
trigger:
  - platform: state
    entity_id: binary_sensor.plex_responsive
    to: "off"
    for:
      minutes: 5
condition:
  - condition: state
    entity_id: binary_sensor.unraid_tower_docker_plex
    state: "on"
action:
  - service: unraid.restart_container
    target:
      entity_id: switch.unraid_tower_docker_plex
    data:
      container: "plex"
  - service: notify.mobile_app
    data:
      title: "Plex Restarted"
      message: "Plex was unresponsive and has been automatically restarted."
mode: single
```

### Schedule VM Startup and Shutdown

Automatically start and stop a VM on a schedule:

```yaml
alias: Schedule Windows VM
description: Start Windows VM in the morning and shut it down at night
trigger:
  - platform: time
    at: "08:00:00"
  - platform: time
    at: "22:00:00"
condition: []
action:
  - if:
      - condition: trigger
        id: "1"
    then:
      - service: unraid.start_vm
        target:
          entity_id: switch.unraid_tower_vm_windows10
        data:
          vm: "Windows10"
    else:
      - service: unraid.stop_vm
        target:
          entity_id: switch.unraid_tower_vm_windows10
        data:
          vm: "Windows10"
mode: single
```

## Script Examples

### Run Backup Script and Notify

Run a backup script on Unraid and notify when complete:

```yaml
alias: Run Unraid Backup
sequence:
  - service: unraid.run_script
    target:
      entity_id: button.unraid_tower_script_backup
    data:
      script: "backup"
  - wait_for_trigger:
      - platform: state
        entity_id: sensor.unraid_tower_script_backup_status
        to: "completed"
    timeout:
      hours: 2
  - service: notify.mobile_app
    data:
      title: "Unraid Backup Complete"
      message: "The backup script has completed successfully."
mode: single
```

### Monitor Parity Check Progress

Create a script to monitor parity check progress:

```yaml
alias: Monitor Parity Check
sequence:
  - repeat:
      while:
        - condition: template
          value_template: "{{ states('sensor.unraid_tower_parity_status') == 'running' }}"
      sequence:
        - service: persistent_notification.create
          data:
            title: "Parity Check Progress"
            message: >
              Parity check is {{ state_attr('sensor.unraid_tower_parity_status', 'percentage') }}% complete.
              Estimated time remaining: {{ state_attr('sensor.unraid_tower_parity_status', 'time_remaining') }}.
        - delay:
            minutes: 15
  - service: notify.mobile_app
    data:
      title: "Parity Check Complete"
      message: "The parity check has completed."
mode: restart
```

## Advanced Examples

### Energy-Saving Mode

Create an energy-saving mode that stops non-essential containers and VMs:

```yaml
alias: Unraid Energy Saving Mode
sequence:
  - service: input_boolean.turn_on
    target:
      entity_id: input_boolean.unraid_energy_saving
  - service: unraid.stop_container
    data:
      container: "plex"
  - service: unraid.stop_container
    data:
      container: "sonarr"
  - service: unraid.stop_container
    data:
      container: "radarr"
  - service: unraid.stop_vm
    data:
      vm: "Windows10"
  - service: notify.mobile_app
    data:
      title: "Energy Saving Mode Activated"
      message: "Non-essential Unraid services have been stopped."
mode: single
```

### Server Maintenance Mode

Create a maintenance mode for your Unraid server:

```yaml
alias: Unraid Maintenance Mode
sequence:
  - service: input_boolean.turn_on
    target:
      entity_id: input_boolean.unraid_maintenance
  - service: unraid.execute_command
    data:
      command: "echo 'Entering maintenance mode' > /tmp/maintenance.log"
  - service: notify.mobile_app
    data:
      title: "Maintenance Mode Activated"
      message: "Unraid server is now in maintenance mode."
  - wait_for_trigger:
      - platform: state
        entity_id: input_boolean.unraid_maintenance
        to: "off"
    timeout:
      hours: 4
  - service: unraid.execute_command
    data:
      command: "echo 'Exiting maintenance mode' >> /tmp/maintenance.log"
  - service: notify.mobile_app
    data:
      title: "Maintenance Mode Deactivated"
      message: "Unraid server is no longer in maintenance mode."
mode: restart
```

## Integration with Other Systems

### Control Unraid Based on Presence

Start or stop services based on presence detection:

```yaml
alias: Unraid Presence Control
description: Control Unraid services based on presence
trigger:
  - platform: state
    entity_id: person.home_owner
    from: "home"
    to: "not_home"
  - platform: state
    entity_id: person.home_owner
    from: "not_home"
    to: "home"
condition: []
action:
  - if:
      - condition: state
        entity_id: person.home_owner
        state: "home"
    then:
      - service: unraid.start_container
        data:
          container: "plex"
      - service: unraid.start_container
        data:
          container: "homebridge"
    else:
      - service: unraid.stop_container
        data:
          container: "plex"
      - service: unraid.stop_container
        data:
          container: "homebridge"
mode: single
```

### Monitor UPS and Safely Shut Down

Monitor UPS status and safely shut down when battery is low:

```yaml
alias: UPS Safe Shutdown
description: Safely shut down Unraid when UPS battery is low
trigger:
  - platform: numeric_state
    entity_id: sensor.unraid_tower_ups_battery
    below: 15
condition:
  - condition: state
    entity_id: binary_sensor.power_outage
    state: "on"
action:
  - service: notify.all_devices
    data:
      title: "UPS Battery Low"
      message: "UPS battery at {{ states('sensor.unraid_tower_ups_battery') }}%. Preparing for safe shutdown."
  - service: unraid.execute_command
    data:
      command: "/sbin/powerdown -u"
  - service: notify.all_devices
    data:
      title: "Unraid Shutdown Initiated"
      message: "Unraid server is shutting down safely."
mode: single
```

These examples demonstrate just a few of the many ways you can leverage the Unraid integration in your Home Assistant setup. Feel free to adapt and combine these examples to suit your specific needs.
