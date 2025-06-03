"""Enhanced USB flash drive detection for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

@dataclass
class USBDeviceInfo:
    """Information about a detected USB device."""
    device_path: str
    is_usb: bool
    is_boot_drive: bool
    transport_type: str
    device_type: str = "unknown"  # "usb_flash_drive", "usb_storage_drive", "sata", etc.
    mount_point: Optional[str] = None
    filesystem: Optional[str] = None
    size: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    detection_method: str = "unknown"
    confidence: float = 0.0  # 0.0 to 1.0
    supports_smart: bool = False  # Whether device supports SMART monitoring


class USBFlashDriveDetector:
    """Enhanced USB flash drive detection with multiple methods and caching."""

    def __init__(self, instance: Any):
        """Initialize the USB detector."""
        self._instance = instance
        self._cache: Dict[str, USBDeviceInfo] = {}
        self._cache_timeout = timedelta(minutes=10)  # Cache USB detection for 10 minutes
        self._last_update: Dict[str, datetime] = {}

    async def detect_usb_device(self, device_path: str, force_refresh: bool = False) -> USBDeviceInfo:
        """
        Detect if a device is a USB flash drive using multiple methods.
        
        Args:
            device_path: Device path to check (e.g., '/dev/sda')
            force_refresh: Force refresh of cached data
            
        Returns:
            USBDeviceInfo with detection results
        """
        # Check cache first
        if not force_refresh and device_path in self._cache:
            last_update = self._last_update.get(device_path)
            if last_update and (datetime.now() - last_update) < self._cache_timeout:
                _LOGGER.debug("Using cached USB detection for %s", device_path)
                return self._cache[device_path]

        _LOGGER.debug("Starting USB detection for device %s", device_path)
        
        # Initialize device info
        device_info = USBDeviceInfo(
            device_path=device_path,
            is_usb=False,
            is_boot_drive=False,
            transport_type="unknown",
            device_type="unknown",
            supports_smart=False
        )

        # Method 1: Transport type detection (primary method)
        transport_result = await self._detect_transport_type(device_path)
        if transport_result:
            device_info.is_usb = transport_result["is_usb"]
            device_info.transport_type = transport_result["transport"]
            device_info.detection_method = "transport_detection"
            device_info.confidence = 0.9 if transport_result["is_usb"] else 0.8

            # Set initial device type based on transport
            if transport_result["is_usb"]:
                device_info.device_type = "usb_device"  # Will be refined later
            else:
                device_info.device_type = transport_result.get("device_type", "unknown")

        # Method 2: Boot drive detection (if USB confirmed)
        if device_info.is_usb:
            boot_result = await self._detect_boot_drive(device_path)
            if boot_result:
                device_info.is_boot_drive = boot_result["is_boot"]
                device_info.mount_point = boot_result.get("mount_point")
                device_info.filesystem = boot_result.get("filesystem")
                if device_info.is_boot_drive:
                    device_info.confidence = 1.0

        # Method 3: Device characteristics (enhanced for USB vs SSD distinction)
        char_result = await self._detect_device_characteristics(device_path)
        if char_result:
            device_info.size = char_result.get("size")
            device_info.model = char_result.get("model")
            device_info.vendor = char_result.get("vendor")

            # Refine device type classification for USB devices
            if device_info.is_usb:
                is_flash_drive = char_result.get("likely_usb", True)

                if not is_flash_drive:
                    # This is a USB-connected storage device (SSD/HDD) - should support SMART
                    device_info.device_type = "usb_storage_drive"
                    device_info.supports_smart = True
                    device_info.detection_method = "usb_storage_device"
                    device_info.confidence = max(device_info.confidence, 0.8)
                    _LOGGER.debug(
                        "Device %s classified as USB-connected storage device - will monitor SMART",
                        device_path
                    )
                else:
                    # This is a USB flash drive - typically boot drives
                    device_info.device_type = "usb_flash_drive"
                    device_info.supports_smart = False
                    device_info.detection_method = "usb_flash_drive"
                    device_info.confidence = max(device_info.confidence, 0.9)
                    _LOGGER.debug(
                        "Device %s classified as USB flash drive - will skip SMART monitoring",
                        device_path
                    )
            else:
                # Apply characteristics-based detection only for non-USB transport devices
                # This helps catch edge cases but should not override transport detection
                is_flash_drive = char_result.get("likely_usb", False)
                if is_flash_drive and device_info.transport_type == "unknown":
                    # Only flag as USB if transport is unknown and characteristics suggest it
                    device_info.is_usb = True
                    device_info.device_type = "usb_flash_drive"
                    device_info.supports_smart = False
                    device_info.transport_type = "usb"
                    device_info.detection_method = "characteristics_fallback"
                    device_info.confidence = 0.7
                    _LOGGER.debug(
                        "Device %s detected as USB flash drive via characteristics fallback",
                        device_path
                    )
                else:
                    # Regular non-USB device
                    device_info.device_type = "sata" if "sata" in device_info.transport_type else device_info.transport_type
                    device_info.supports_smart = True

        # Cache the result
        self._cache[device_path] = device_info
        self._last_update[device_path] = datetime.now()

        _LOGGER.debug(
            "USB detection complete for %s: is_usb=%s, device_type=%s, is_boot=%s, supports_smart=%s, confidence=%.2f, method=%s",
            device_path, device_info.is_usb, device_info.device_type, device_info.is_boot_drive,
            device_info.supports_smart, device_info.confidence, device_info.detection_method
        )

        return device_info

    async def _detect_transport_type(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Detect device transport type using lsblk."""
        try:
            # Primary method: lsblk with transport info
            cmd = f"lsblk -o NAME,TRAN,TYPE {device_path} 2>/dev/null"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 2:
                        transport = parts[1].lower() if parts[1] != '-' else 'unknown'
                        device_type = parts[2].lower() if len(parts) > 2 else 'unknown'
                        
                        is_usb = 'usb' in transport
                        _LOGGER.debug("Transport detection for %s: transport=%s, type=%s, is_usb=%s", 
                                    device_path, transport, device_type, is_usb)
                        
                        return {
                            "is_usb": is_usb,
                            "transport": transport,
                            "device_type": device_type
                        }

        except Exception as err:
            _LOGGER.debug("Transport detection failed for %s: %s", device_path, err)

        # Fallback method: Check USB subsystem
        try:
            # Extract device name (e.g., 'sda' from '/dev/sda')
            device_name = device_path.split('/')[-1]
            cmd = f"ls -la /sys/block/{device_name} 2>/dev/null | grep -i usb"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0:
                _LOGGER.debug("USB subsystem detection confirmed USB for %s", device_path)
                return {
                    "is_usb": True,
                    "transport": "usb",
                    "device_type": "disk"
                }

        except Exception as err:
            _LOGGER.debug("USB subsystem detection failed for %s: %s", device_path, err)

        return None

    async def _detect_boot_drive(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Detect if USB device is the Unraid boot drive."""
        try:
            # Check mount points for /boot
            cmd = "mount | grep -E '/boot|UNRAID' | head -5"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    # Parse mount line: /dev/sdb1 on /boot type vfat (rw,...)
                    parts = line.split()
                    if len(parts) >= 3:
                        mounted_device = parts[0]
                        mount_point = parts[2]
                        filesystem = parts[4] if len(parts) > 4 else 'unknown'
                        
                        # Check if this mount relates to our device
                        if device_path in mounted_device or mounted_device.startswith(device_path):
                            is_boot = '/boot' in mount_point or 'UNRAID' in line.upper()
                            
                            _LOGGER.debug("Boot drive check for %s: mounted_device=%s, mount_point=%s, is_boot=%s",
                                        device_path, mounted_device, mount_point, is_boot)
                            
                            return {
                                "is_boot": is_boot,
                                "mount_point": mount_point,
                                "filesystem": filesystem,
                                "mounted_device": mounted_device
                            }

        except Exception as err:
            _LOGGER.debug("Boot drive detection failed for %s: %s", device_path, err)

        # Fallback: Check for UNRAID label
        try:
            cmd = f"blkid {device_path}* 2>/dev/null | grep -i unraid"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0:
                _LOGGER.debug("UNRAID label detected on %s", device_path)
                return {
                    "is_boot": True,
                    "mount_point": "/boot",
                    "filesystem": "vfat"
                }

        except Exception as err:
            _LOGGER.debug("UNRAID label check failed for %s: %s", device_path, err)

        return None

    async def _detect_device_characteristics(self, device_path: str) -> Optional[Dict[str, Any]]:
        """Detect device characteristics that might indicate USB flash drive."""
        try:
            # Get device information
            cmd = f"lsblk -o NAME,SIZE,MODEL,VENDOR,FSTYPE {device_path} 2>/dev/null"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    parts = line.split(None, 4)  # Split into max 5 parts
                    if len(parts) >= 2:
                        size = parts[1] if len(parts) > 1 else 'unknown'
                        model = parts[2] if len(parts) > 2 else 'unknown'
                        vendor = parts[3] if len(parts) > 3 else 'unknown'
                        fstype = parts[4] if len(parts) > 4 else 'unknown'
                        
                        # Heuristics for USB flash drive detection
                        likely_usb = self._analyze_device_characteristics(size, model, vendor, fstype)
                        
                        _LOGGER.debug("Device characteristics for %s: size=%s, model=%s, vendor=%s, likely_usb=%s",
                                    device_path, size, model, vendor, likely_usb)
                        
                        return {
                            "size": size,
                            "model": model,
                            "vendor": vendor,
                            "filesystem": fstype,
                            "likely_usb": likely_usb
                        }

        except Exception as err:
            _LOGGER.debug("Device characteristics detection failed for %s: %s", device_path, err)

        return None

    def _analyze_device_characteristics(self, size: str, model: str, vendor: str, fstype: str) -> bool:
        """Analyze device characteristics to determine if likely USB flash drive (not SSD)."""
        text_to_check = f"{size} {model} {vendor} {fstype}".lower()

        # Indicators that suggest this is a USB flash drive (not an SSD)
        flash_drive_indicators = [
            # Common USB flash drive model names
            r'(?i)(ultra fit|cruzer|datatraveler|flash drive|usb stick|thumb drive)',
            # Small sizes typical of flash drives (but not SSDs)
            r'\b(1|2|4|8|16|32)G\b',  # Smaller sizes more likely flash drives
            # Flash drive specific vendors/models
            r'(?i)(sandisk.*ultra|kingston.*datatraveler|cruzer)',
        ]

        # Indicators that suggest this is NOT a flash drive (likely SSD or HDD)
        not_flash_drive_indicators = [
            # SSD model patterns
            r'(?i)(ssd|solid state|wds\d+|samsung.*evo|crucial.*mx|intel.*ssd)',
            # Large sizes typical of SSDs/HDDs
            r'\b(120|128|240|256|480|500|512|960|1000|1024|2000|2048)G\b',
            # Professional/enterprise indicators
            r'(?i)(enterprise|pro|plus|evo|nvme|m\.2)',
            # ZFS or other advanced filesystems
            r'(?i)(zfs|btrfs|ext4|xfs)',
        ]

        # Check for NOT flash drive indicators first (higher priority)
        for pattern in not_flash_drive_indicators:
            if re.search(pattern, text_to_check):
                return False

        # Then check for flash drive indicators
        for pattern in flash_drive_indicators:
            if re.search(pattern, text_to_check):
                return True

        # Default: if USB transport but no clear indicators, assume flash drive
        # This is conservative - better to skip SMART on uncertain devices
        return True

    async def get_all_usb_devices(self) -> List[USBDeviceInfo]:
        """Get information about all USB devices in the system."""
        usb_devices = []
        
        try:
            # Get all block devices
            cmd = "lsblk -o NAME,TRAN,TYPE -n | grep -E '^[a-z]+' | grep -v loop"
            result = await self._instance.execute_command(cmd)
            
            if result.exit_status == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        device_name = parts[0]
                        transport = parts[1].lower()
                        
                        if 'usb' in transport:
                            device_path = f"/dev/{device_name}"
                            device_info = await self.detect_usb_device(device_path)
                            usb_devices.append(device_info)

        except Exception as err:
            _LOGGER.debug("Failed to get all USB devices: %s", err)

        return usb_devices

    def clear_cache(self) -> None:
        """Clear the detection cache."""
        self._cache.clear()
        self._last_update.clear()
        _LOGGER.debug("USB detection cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for debugging."""
        return {
            "cached_devices": len(self._cache),
            "cache_timeout_minutes": self._cache_timeout.total_seconds() / 60,
            "devices": {
                path: {
                    "is_usb": info.is_usb,
                    "device_type": info.device_type,
                    "is_boot": info.is_boot_drive,
                    "supports_smart": info.supports_smart,
                    "confidence": info.confidence,
                    "method": info.detection_method,
                    "age_seconds": (datetime.now() - self._last_update.get(path, datetime.now())).total_seconds()
                }
                for path, info in self._cache.items()
            }
        }
