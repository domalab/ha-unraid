"""Disk validation logic for Unraid."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

def is_valid_disk_name(disk_name: str) -> bool:
    """Validate disk name format."""
    if not disk_name:
        return False
        
    # Array disks (disk1, disk2, etc)
    if disk_name.startswith("disk") and disk_name[4:].isdigit():
        return True
        
    # Cache disks (cache, cache2, cacheNVME, etc)
    if disk_name.startswith("cache"):
        return True
        
    # Known system paths to exclude
    invalid_names = {
        "user", "user0", "rootshare", "addons", 
        "remotes", "system", "flash", "boot",
        "disks"
    }
    
    if disk_name.lower() in invalid_names:
        return False
        
    # Any other mounted disk that isn't in invalid_names is considered valid
    # This allows for custom pool names
    return True