from typing import List, Dict, Any

async def get_individual_disk_usage(self) -> List[Dict[str, Any]]:
    """Get usage information for individual disks."""
    try:
        disks = []
        # Get usage for mounted disks with more specific path patterns
        # Include all possible cache configurations
        usage_result = await self.execute_command(
            "df -B1 /mnt/disk[0-9]* /mnt/cache* /mnt/pool* 2>/dev/null | "
            "awk 'NR>1 {print $6,$2,$3,$4,$1}'"  # Added $1 to get filesystem source
        )

        if usage_result.exit_status == 0:
            for line in usage_result.stdout.splitlines():
                try:
                    mount_point, total, used, free, device = line.split()
                    disk_name = mount_point.replace('/mnt/', '')
                    
                    # Skip invalid or system disks while allowing custom pools
                    if not is_valid_disk_name(disk_name):
                        _LOGGER.debug("Skipping invalid disk name: %s", disk_name)
                        continue
                    
                    # Get current disk state
                    state = await self._state_manager.get_disk_state(disk_name)
                    
                    # Determine if this is a cache device
                    is_cache = disk_name.startswith("cache")
                    filesystem_type = "btrfs" if "btrfs" in device else "xfs"
                    
                    disk_info = {
                        "name": disk_name,
                        "mount_point": mount_point,
                        "total": int(total),
                        "used": int(used),
                        "free": int(free),
                        "percentage": round((int(used) / int(total) * 100), 1) if int(total) > 0 else 0,
                        "state": state.value,
                        "smart_data": {},  # Will be populated by update_disk_status
                        "smart_status": "Unknown",
                        "temperature": None,
                        "device": device,
                        "is_cache": is_cache,
                        "filesystem": filesystem_type
                    }
                    
                    # Update disk status with SMART data if disk is active
                    if state == DiskState.ACTIVE:
                        disk_info = await self.update_disk_status(disk_info)
                        
                    disks.append(disk_info)

                except (ValueError, IndexError) as err:
                    _LOGGER.debug("Error parsing disk usage line '%s': %s", line, err)
                    continue

            return disks

        return []

    except Exception as err:
        _LOGGER.error("Error getting disk usage: %s", err)
        return [] 