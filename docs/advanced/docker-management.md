# Docker Container Management

The Unraid Integration provides powerful capabilities for monitoring and controlling Docker containers running on your Unraid server. This guide explains how to effectively use these features.

## Available Features

The Docker management features include:

- **Status Monitoring**: Real-time status of Docker containers (running, stopped, paused)
- **Basic Controls**: Start and stop containers through switches
- **Advanced Controls**: Pause, resume, and restart containers through services
- **Command Execution**: Run commands inside containers
- **Health Monitoring**: Track container health status (where available)

## Container Switches

Each Docker container on your Unraid server will appear as a switch entity in Home Assistant. The entity ID will be in the format `switch.unraid_docker_[container_name]`, where `[container_name]` is the name of your Docker container with special characters replaced.

### Using Container Switches

Container switches provide basic on/off functionality:

- **Turn On**: Starts the container if it's stopped
- **Turn Off**: Stops the container if it's running

You can use these switches in the Home Assistant UI, automations, scripts, and scenes like any other switch entity.

```yaml
# Example: Turn on a Docker container
service: switch.turn_on
target:
  entity_id: switch.unraid_docker_plex
```

```yaml
# Example: Turn off a Docker container
service: switch.turn_off
target:
  entity_id: switch.unraid_docker_sonarr
```

## Advanced Container Controls

For more advanced control, the integration provides several services:

### Pause a Container

Pauses a running container (freezes the container's processes):

```yaml
service: unraid.docker_pause
data:
  entry_id: your_entry_id
  container: container_name
```

### Resume a Container

Resumes a paused container:

```yaml
service: unraid.docker_resume
data:
  entry_id: your_entry_id
  container: container_name
```

### Restart a Container

Restarts a container (graceful stop and start):

```yaml
service: unraid.docker_restart
data:
  entry_id: your_entry_id
  container: container_name
```

!!! note "Container Names"
    The `container` parameter should match the exact container name as shown in the Unraid Docker UI, not the Home Assistant entity name.

## Execute Commands in Containers

You can execute commands inside Docker containers using the `unraid.execute_in_container` service:

```yaml
service: unraid.execute_in_container
data:
  entry_id: your_entry_id
  container: container_name
  command: your_command_here
```

### Example: Run a Database Backup in a Container

```yaml
service: unraid.execute_in_container
data:
  entry_id: your_entry_id
  container: mariadb
  command: "mysqldump -u root -ppassword --all-databases > /backup/db_backup.sql"
```

### Example: Update Package Lists in a Container

```yaml
service: unraid.execute_in_container
data:
  entry_id: your_entry_id
  container: ubuntu-container
  command: "apt-get update"
```

## Best Practices

### Container Management

1. **Graceful Shutdown**: Always use the proper stop methods rather than force-stopping containers to prevent data corruption
2. **Status Verification**: Check container status before sending commands
3. **Health Monitoring**: Monitor container health and set up automation to restart unhealthy containers
4. **Resource Awareness**: Be mindful of starting resource-intensive containers simultaneously

### Container Naming

For best compatibility with Home Assistant:

1. Use simple, consistent naming for containers in Unraid
2. Avoid special characters in container names
3. Be aware that entity IDs in Home Assistant will convert spaces and special characters to underscores

## Automation Ideas

### Monitor and Restart Unhealthy Containers

```yaml
automation:
  - alias: "Restart Unhealthy Container"
    trigger:
      - platform: state
        entity_id: sensor.unraid_docker_nginx_health
        to: "unhealthy"
        for:
          minutes: 2
    action:
      - service: unraid.docker_restart
        data:
          entry_id: your_entry_id
          container: "nginx"
      - service: notify.mobile_app
        data:
          title: "Container Restarted"
          message: "NGINX container was unhealthy and has been restarted."
```

### Schedule Container Maintenance

```yaml
automation:
  - alias: "Weekly Container Maintenance"
    trigger:
      - platform: time
        at: "03:00:00"
    condition:
      - condition: time
        weekday:
          - mon
    action:
      - service: unraid.docker_restart
        data:
          entry_id: your_entry_id
          container: "database"
      - service: unraid.execute_in_container
        data:
          entry_id: your_entry_id
          container: "database"
          command: "/usr/local/bin/db_optimize.sh"
```

### Load Balancing

```yaml
automation:
  - alias: "Smart Container Load Balancing"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_cpu_usage
        above: 80
        for:
          minutes: 5
    action:
      - service: unraid.docker_pause
        data:
          entry_id: your_entry_id
          container: "non_critical_service"
      - service: notify.mobile_app
        data:
          title: "Load Balancing"
          message: "Paused non-critical services due to high CPU usage."
```

## Troubleshooting

### Container Controls Not Working

If you're having issues controlling Docker containers:

1. **Check Docker Service**: Ensure the Docker service is running on your Unraid server
2. **Verify Names**: Container names in service calls must match exactly with Unraid
3. **Check Permissions**: Make sure your Unraid user has permissions to control Docker
4. **Container State**: The container might be in a transitional state, check Unraid UI
5. **SSH Connection**: Verify the SSH connection between Home Assistant and Unraid is working

### Delayed Status Updates

If container status doesn't update promptly:

1. **Update Interval**: The status may not update until the next polling interval
2. **UI Refresh**: Try refreshing the Home Assistant UI
3. **Restart Integration**: In extreme cases, try reloading the integration

## Advanced Configuration

For advanced users, consider creating custom scripts on your Unraid server that can manage multiple containers or perform complex operations, then call these scripts from Home Assistant using the `unraid.execute_command` service. 