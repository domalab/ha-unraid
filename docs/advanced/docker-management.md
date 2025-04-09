---
layout: default
title: Docker Management
---

# Docker Container Management

This guide explains how to manage Docker containers on your Unraid server through Home Assistant.

## Available Controls

The Unraid integration provides the following Docker container controls:

- View container status
- Start/Stop containers
- Execute commands within containers
- Monitor container states

## Entity Types

Each Docker container appears as a switch entity in Home Assistant:

```
switch.unraid_docker_[container_name]
```

Example entities:

- `switch.unraid_docker_plex`
- `switch.unraid_docker_homeassistant`
- `switch.unraid_docker_nginx`

## Basic Controls

### Start Container

```yaml
# Using switch entity
service: switch.turn_on
target:
  entity_id: switch.unraid_docker_plex

# Using service call
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "docker start plex"
```

### Stop Container

```yaml
# Using switch entity
service: switch.turn_off
target:
  entity_id: switch.unraid_docker_plex

# Using service call
service: unraid.execute_command
data:
  entry_id: "1234abcd5678efgh"
  command: "docker stop plex"
```

## Advanced Container Management

### Execute Commands in Container

```yaml
service: unraid.execute_in_container
data:
  entry_id: "1234abcd5678efgh"
  container: "plex"
  command: "ls -l /config"
  detached: false
```

### Example Use Cases

#### 1. Restart Container on Issues

```yaml
alias: "Restart Plex When Frozen"
description: "Restart Plex container if it becomes unresponsive"
trigger:
  - platform: state
    entity_id: binary_sensor.plex_available
    to: "off"
    for:
      minutes: 2
action:
  - service: switch.turn_off
    target:
      entity_id: switch.unraid_docker_plex
  - delay:
      seconds: 30
  - service: switch.turn_on
    target:
      entity_id: switch.unraid_docker_plex
```

#### 2. Schedule Container Updates

```yaml
alias: "Update Docker Containers"
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: time
    weekday:
      - mon
action:
  - service: unraid.execute_command
    data:
      entry_id: "1234abcd5678efgh"
      command: "docker container ls -q | xargs -r docker update"
```

#### 3. Container Maintenance

```yaml
alias: "Docker Maintenance"
trigger:
  - platform: time
    at: "04:00:00"
action:
  - service: unraid.execute_command
    data:
      entry_id: "1234abcd5678efgh"
      command: "docker system prune -f"
```

## Monitoring Containers

### Container Status Sensor

Monitor container status through the switch entity's state:

- `on` = Container is running
- `off` = Container is stopped

### Container Logs

```yaml
service: unraid.execute_in_container
data:
  entry_id: "1234abcd5678efgh"
  container: "plex"
  command: "tail -n 100 /config/Plex Media Server/Logs/Plex Media Server.log"
```

## Best Practices

1. **Graceful Shutdown**
   - Allow sufficient time for containers to stop
   - Use appropriate stop signals
   - Monitor shutdown completion

2. **Resource Management**
   - Monitor container resource usage
   - Schedule maintenance during off-peak hours
   - Clean up unused containers/images

3. **Error Handling**
   - Implement retry logic
   - Add notification on failures
   - Log important events

4. **Security**
   - Use specific commands instead of shell access
   - Limit command execution privileges
   - Monitor container security logs
