---
layout: default
title: User Scripts
---

# Working with Unraid User Scripts

This guide explains how to work with user scripts in the Unraid integration for Home Assistant.

## Overview

User scripts in Unraid are custom scripts stored in `/boot/config/plugins/user.scripts/scripts` that can be executed through Home Assistant for automation purposes.

## Script Location

User scripts must be located in the correct directory on your Unraid server:

```
/boot/config/plugins/user.scripts/scripts
```

## Creating User Scripts

### Basic Script Structure

```bash
#!/bin/bash
# Description: Example backup script
# Author: Your Name
# Date: 2024-01-01

# Set error handling
set -e

# Log function
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> /var/log/user_scripts.log
}

# Main script logic
log_message "Starting script execution"

# Your commands here

log_message "Script execution completed"
```

### Example Scripts

#### 1. Backup Script

```bash
#!/bin/bash
# backup_appdata.sh - Backup Docker application data

# Set variables
BACKUP_DIR="/mnt/user/backups/appdata"
DATE=$(date +%Y%m%d)
LOG_FILE="/var/log/backup.log"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Log start
echo "[$(date)] Starting appdata backup" >> "$LOG_FILE"

# Stop Docker containers
docker stop $(docker ps -q)

# Create backup
tar -czf "$BACKUP_DIR/appdata_$DATE.tar.gz" /mnt/user/appdata/

# Start Docker containers
docker start $(docker ps -a -q)

# Log completion
echo "[$(date)] Backup completed" >> "$LOG_FILE"
```

#### 2. Maintenance Script

```bash
#!/bin/bash
# maintenance.sh - System maintenance tasks

# Log file
LOG_FILE="/var/log/maintenance.log"

# Log function
log_message() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# Clean Docker
log_message "Cleaning unused Docker images"
docker system prune -f

# Clear system cache
log_message "Clearing system cache"
sync; echo 3 > /proc/sys/vm/drop_caches

# Check disk health
log_message "Checking disk health"
for disk in /dev/sd*; do
    if [[ -b "$disk" && ! "$disk" =~ [0-9]$ ]]; then
        smartctl -H "$disk" >> "$LOG_FILE" 2>&1
    fi
done

log_message "Maintenance completed"
```

## Using Scripts in Home Assistant

### Service Calls

#### Execute a Script

```yaml
service: unraid.execute_user_script
data:
  entry_id: "1234abcd5678efgh"
  script_name: "backup_appdata.sh"
  background: false
```

#### Execute in Background

```yaml
service: unraid.execute_user_script
data:
  entry_id: "1234abcd5678efgh"
  script_name: "organize_media.sh"
  background: true
```

#### Stop a Running Script

```yaml
service: unraid.stop_user_script
data:
  entry_id: "1234abcd5678efgh"
  script_name: "backup_appdata.sh"
```

### Automation Examples

#### Scheduled Backup

```yaml
alias: "Weekly Appdata Backup"
description: "Run weekly backup of Docker appdata"
trigger:
  - platform: time
    at: "02:00:00"
condition:
  - condition: time
    weekday:
      - sat
action:
  - service: unraid.execute_user_script
    data:
      entry_id: "1234abcd5678efgh"
      script_name: "backup_appdata.sh"
      background: true
  - service: notify.notify
    data:
      title: "Unraid Backup"
      message: "Weekly backup started"
```

## Best Practices

### 1. Script Writing

- Always include shebang line (`#!/bin/bash`)
- Add descriptive comments
- Use meaningful variable names
- Implement error handling
- Include logging
- Make scripts idempotent

### 2. Permissions

```bash
# Make script executable
chmod +x /boot/config/plugins/user.scripts/scripts/script_name.sh

# Set appropriate ownership
chown root:root /boot/config/plugins/user.scripts/scripts/script_name.sh
```

### 3. Logging

- Use consistent log format
- Include timestamps
- Log both success and errors
- Set up log rotation

### 4. Error Handling

```bash
# Basic error handling
set -e  # Exit on error
trap 'echo "Error on line $LINENO"' ERR

# Advanced error handling
handle_error() {
    local line_no=$1
    local error_code=$2
    echo "Error on line ${line_no}: Exit code ${error_code}"
    # Cleanup code here
}
trap 'handle_error ${LINENO} $?' ERR
```

### 5. Testing

- Test scripts manually first
- Start with small test cases
- Verify all paths exist
- Check permissions
- Test error conditions

## Debugging Scripts

### Enable Debug Mode

Add to your scripts:

```bash
# Enable debug output
set -x

# Your script commands here

# Disable debug output
set +x
```

### Check Logs

```bash
# View script logs
tail -f /var/log/user_scripts.log

# View Home Assistant logs
tail -f /config/home-assistant.log
```

## Security Considerations

1. **Script Permissions**
   - Use minimal required permissions
   - Avoid running as root when possible
   - Secure sensitive data

2. **Input Validation**
   - Validate all parameters
   - Sanitize file paths
   - Check return codes

3. **Resource Usage**
   - Monitor script duration
   - Check disk space before operations
   - Consider CPU and memory usage

## Troubleshooting

Common issues and solutions:

1. **Script Won't Execute**
   - Check permissions
   - Verify script exists
   - Check path is correct
   - Validate script syntax

2. **Script Hangs**
   - Use background execution
   - Add timeout mechanisms
   - Check for infinite loops
   - Verify resource availability

3. **Script Fails**
   - Check logs for errors
   - Verify dependencies
   - Test commands manually
   - Check disk space

Remember to always test your scripts thoroughly before implementing them in automations.
