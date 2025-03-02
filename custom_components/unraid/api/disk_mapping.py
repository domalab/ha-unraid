from typing import Dict

def get_unraid_disk_mapping(data: dict) -> Dict[str, str]:
    """Map Unraid disks to their device paths and serial numbers."""
    mapping = {}

    try:
        # Get disk information from system stats
        for disk in data.get("system_stats", {}).get("individual_disks", []):
            name = disk.get("name", "")
            device = disk.get("device", "")
            serial = disk.get("serial", "")
            filesystem = disk.get("filesystem", "")
            is_cache = disk.get("is_cache", False)

            # Skip if missing essential info
            if not name or not device:
                continue

            # Map array disk (disk1, disk2, etc)
            if name.startswith("disk"):
                mapping[name] = {
                    "device": device,
                    "serial": serial,
                    "filesystem": filesystem
                }

            # Map cache disk(s)
            elif name.startswith("cache"):
                # For btrfs cache pools, we need to handle multiple devices
                if filesystem == "btrfs":
                    pool_info = data.get("system_stats", {}).get("cache_usage", {}).get("pool_status", {})
                    devices = pool_info.get("devices", [])
                    if devices:
                        device = devices[0]  # Use first device as primary
                
                mapping[name] = {
                    "device": device,
                    "serial": serial,
                    "filesystem": filesystem,
                    "is_cache": True
                }

            # Map other pool devices
            elif "/" in device and is_valid_disk_name(name):
                mapping[name] = {
                    "device": device,
                    "serial": serial,
                    "filesystem": filesystem
                }

        return mapping

    except (KeyError, TypeError, AttributeError) as err:
        _LOGGER.error("Error mapping disks: %s", err)
        return {} 