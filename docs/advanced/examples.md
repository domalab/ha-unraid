# Example Automations

This page provides practical examples and automation ideas for using the Unraid Integration in Home Assistant. These examples can be adapted to suit your particular needs and environment.

## Basic Automations

### Notification When Server Goes Offline

Get notified when your Unraid server becomes unavailable:

```yaml
automation:
  - alias: "Unraid Server Offline Notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.unraid_server_connectivity
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Unraid Server Offline"
          message: "Your Unraid server has gone offline. Please check the connection."
```

### Low Disk Space Warning

Get a notification when disk space gets low:

```yaml
automation:
  - alias: "Unraid Disk Space Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_array_usage
        above: 85
    action:
      - service: notify.mobile_app
        data:
          title: "Unraid Disk Space Warning"
          message: "Your Unraid array is over 85% full. Consider freeing up some space."
```

### High Temperature Alert

Get alerted when CPU temperature gets too high:

```yaml
automation:
  - alias: "Unraid CPU Temperature Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_cpu_temperature
        above: 75
    action:
      - service: notify.mobile_app
        data:
          title: "Unraid CPU Temperature Alert"
          message: "CPU temperature is above 75°C. Check cooling system!"
```

## Scheduled Tasks

### Weekly Backup Automation

Automatically run a backup script every Sunday at 2 AM:

```yaml
automation:
  - alias: "Weekly Unraid Backup"
    trigger:
      - platform: time
        at: "02:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: unraid.execute_user_script
        data:
          entry_id: !input unraid_entry_id
          script_name: "backup.sh"
```

### Nightly Array Parity Check

Schedule a weekly parity check during off-hours:

```yaml
automation:
  - alias: "Weekly Parity Check"
    trigger:
      - platform: time
        at: "01:00:00"
    condition:
      - condition: time
        weekday:
          - mon
    action:
      - service: unraid.execute_command
        data:
          entry_id: !input unraid_entry_id
          command: "/usr/local/sbin/parity_check_start"
```

### Restart Problem Containers

Automatically restart containers that have crashed:

```yaml
automation:
  - alias: "Restart Crashed Container"
    trigger:
      - platform: state
        entity_id: switch.unraid_docker_important_service
        from: "on"
        to: "off"
        for:
          minutes: 5
    action:
      - service: unraid.docker_restart
        data:
          entry_id: !input unraid_entry_id
          container: "important-service"
      - service: notify.mobile_app
        data:
          title: "Container Restarted"
          message: "The important-service container was detected as stopped and has been restarted."
```

## Energy Management

### UPS Low Battery Shutdown

Safely shut down the Unraid server when UPS battery is low:

```yaml
automation:
  - alias: "UPS Low Battery Shutdown"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_ups_battery
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "UPS Battery Critical"
          message: "Initiating safe shutdown of Unraid server due to low UPS battery."
      - service: unraid.system_shutdown
        data:
          entry_id: !input unraid_entry_id
```

### Power-Hungry Container Management

Turn off power-intensive containers during peak electricity hours:

```yaml
automation:
  - alias: "Manage Power-Hungry Containers"
    trigger:
      - platform: time
        at: "17:00:00"  # Peak electricity hours start
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.unraid_docker_folding_at_home
      - service: notify.mobile_app
        data:
          title: "Power Management"
          message: "Power-intensive containers have been paused during peak electricity hours."
  
  - alias: "Restart Power-Hungry Containers"
    trigger:
      - platform: time
        at: "00:00:00"  # Off-peak hours
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unraid_docker_folding_at_home
```

## System Maintenance

### Reboot Server at Maintenance Window

Schedule a regular maintenance reboot:

```yaml
automation:
  - alias: "Unraid Maintenance Reboot"
    trigger:
      - platform: time
        at: "04:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: unraid.system_reboot
        data:
          entry_id: !input unraid_entry_id
      - service: notify.mobile_app
        data:
          title: "Scheduled Maintenance"
          message: "Unraid server is being rebooted for scheduled maintenance."
```

### Stop Docker Before Shutdown

Stop all Docker containers before shutting down:

```yaml
automation:
  - alias: "Stop Docker Before Shutdown"
    trigger:
      - platform: event
        event_type: system_shutdown_requested
    action:
      - service: unraid.execute_command
        data:
          entry_id: !input unraid_entry_id
          command: "/usr/local/emhttp/plugins/dynamix.docker.manager/scripts/docker stop"
      - service: notify.mobile_app
        data:
          title: "Docker Services Stopped"
          message: "All Docker containers have been safely stopped before shutdown."
```

## Media Management

### Start Media Server When Needed

Automatically start Plex or other media servers when home:

```yaml
automation:
  - alias: "Start Media Server When Home"
    trigger:
      - platform: state
        entity_id: person.family
        from: "not_home"
        to: "home"
    condition:
      - condition: state
        entity_id: switch.unraid_docker_plex
        state: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unraid_docker_plex
```

### Transcode Management

Pause CPU-intensive activities when transcoding starts:

```yaml
automation:
  - alias: "Manage Server Load During Transcoding"
    trigger:
      - platform: state
        entity_id: sensor.plex_transcoding_count
        from: "0"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.unraid_docker_cpu_intensive_service
      - service: notify.mobile_app
        data:
          title: "Transcoding Optimizations"
          message: "CPU-intensive tasks paused to prioritize media transcoding."
```

## Advanced Automations

### Conditional Maintenance Based on System Load

Only perform maintenance tasks when system load is low:

```yaml
automation:
  - alias: "Smart Maintenance Tasks"
    trigger:
      - platform: time
        at: "03:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.unraid_cpu_usage
        below: 15
      - condition: numeric_state
        entity_id: sensor.unraid_ram_usage
        below: 70
    action:
      - service: unraid.execute_user_script
        data:
          entry_id: !input unraid_entry_id
          script_name: "maintenance.sh"
```

### Dynamic Container Management

Manage containers based on network presence and time of day:

```yaml
automation:
  - alias: "Smart Container Management"
    trigger:
      - platform: state
        entity_id: person.family
        from: "home"
        to: "not_home"
      - platform: time
        at: "01:00:00"
    action:
      - service: unraid.execute_command
        data:
          entry_id: !input unraid_entry_id
          command: "/usr/local/bin/container_prioritizer.sh"
```

## Using These Examples

To use these examples in your Home Assistant instance:

1. Replace `!input unraid_entry_id` with your actual Unraid integration entry ID
2. Adjust entity IDs to match your specific entities
3. Modify conditions and triggers to suit your schedule and preferences
4. Test the automations thoroughly before relying on them

For more information on finding your entry ID, see the [Troubleshooting](../user-guide/troubleshooting.md#finding-your-entry-id) page. 