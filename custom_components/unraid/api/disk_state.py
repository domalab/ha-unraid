async def _get_device_path(self, device: str) -> str | None:
    """Get actual device path from mount point."""
    try:
        # Check cache first
        if device in self._device_paths_cache:
            return self._device_paths_cache[device]
        
        # Handle cache devices specifically
        if device.startswith("cache"):
            # Try to get the actual mount point
            mount_cmd = f"findmnt -n -o SOURCE /mnt/{device}"
            result = await self._instance.execute_command(mount_cmd)
            
            if result.exit_status == 0 and (device_path := result.stdout.strip()):
                # For btrfs cache pools, we need to get the actual devices
                if "btrfs" in device_path.lower():
                    pool_cmd = f"btrfs filesystem show /mnt/{device}"
                    pool_result = await self._instance.execute_command(pool_cmd)
                    if pool_result.exit_status == 0:
                        # Extract the first device from the pool
                        for line in pool_result.stdout.splitlines():
                            if "/dev/" in line:
                                device_path = line.split()[-1]
                                break
                
                self._device_paths_cache[device] = device_path
                return device_path
            
            # Fallback for traditional cache setup
            if device == "cache":
                nvme_result = await self._instance.execute_command("ls /dev/nvme0n1 2>/dev/null")
                if nvme_result.exit_status == 0:
                    self._device_paths_cache[device] = "/dev/nvme0n1"
                    return "/dev/nvme0n1"
            
            return None
        
        # For other devices, use standard mount point detection
        mount_cmd = f"findmnt -n -o SOURCE /mnt/{device}"
        result = await self._instance.execute_command(mount_cmd)
        if result.exit_status == 0 and (device_path := result.stdout.strip()):
            self._device_paths_cache[device] = device_path
            return device_path
        return None
    except Exception as err:
        _LOGGER.error("Error getting device path for %s: %s", device, err)
        return None 