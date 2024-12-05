"""Binary sensors for Unraid."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Dict
import logging

from homeassistant.components.binary_sensor import ( # type: ignore
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import EntityCategory # type: ignore
from homeassistant.core import HomeAssistant, callback # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback # type: ignore
from homeassistant.helpers.typing import StateType # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore

from .const import DOMAIN, SpinDownDelay
from .coordinator import UnraidDataUpdateCoordinator
from .helpers import format_bytes, get_unraid_disk_mapping

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Unraid binary sensor entity."""

    # Add inherited fields that need to be explicitly declared
    key: str
    name: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None

    # Custom fields
    value_fn: Callable[[dict[str, Any]], bool | None] = field(default=lambda x: None)
    has_warning_threshold: bool = False
    warning_threshold: float | None = None

SENSOR_DESCRIPTIONS: tuple[UnraidBinarySensorEntityDescription, ...] = (
    UnraidBinarySensorEntityDescription(
        key="ssh_connectivity",
        name="Server Connection",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats") is not None,
        icon="mdi:server-network",
    ),
    UnraidBinarySensorEntityDescription(
        key="docker_service",
        name="Docker Service",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("docker_containers")),
        icon="mdi:docker",
    ),
    UnraidBinarySensorEntityDescription(
        key="vm_service",
        name="VM Service",  # Base class will add Unraid prefix
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("vms")),
        icon="mdi:desktop-tower",
    ),
)

class UnraidBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Base entity for Unraid binary sensors."""

    entity_description: UnraidBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        description: UnraidBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor.
        
        Args:
            coordinator: The data update coordinator
            description: Entity description containing key and name
        """
        super().__init__(coordinator)
        self.entity_description = description
        hostname = coordinator.hostname.capitalize()
        # Clean the key of any existing hostname instances
        clean_key = description.key
        hostname_variations = [hostname.lower(), hostname.capitalize(), hostname.upper()]
        for variation in hostname_variations:
            clean_key = clean_key.replace(f"{variation}_", "")
        # Validate the cleaned key
        if not clean_key:
            _LOGGER.error("Invalid empty key after cleaning hostname")
            clean_key = description.key
        # Construct unique_id with guaranteed single hostname instance
        self._attr_unique_id = f"unraid_server_{hostname}_{clean_key}"
        # Keep the name simple and human-readable
        self._attr_name = f"{hostname} {description.name}"
        # Consistent device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"Unraid Server ({hostname})",
            "manufacturer": "Lime Technology",
            "model": "Unraid Server",
        }
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.entity_description.key == "ssh_connectivity":
            return True
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except KeyError as err:
            _LOGGER.debug(
                "Missing key in data for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except TypeError as err:
            _LOGGER.debug(
                "Type error processing sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None
        except AttributeError as err:
            _LOGGER.debug(
                "Attribute error for sensor %s: %s",
                self.entity_description.key,
                err
            )
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

class UnraidDiskHealthSensor(UnraidBinarySensorEntity):
    """Binary sensor for individual disk health."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        disk_name: str,
    ) -> None:
        """Initialize the disk health sensor."""
        # Handle naming for different disk types
        if disk_name == "cache":
            pretty_name = "Cache"
        else:
            # Add validation to ensure we have a valid disk number
            try:
                disk_num = ''.join(filter(str.isdigit, disk_name))
                if not disk_num:
                    raise ValueError(f"Invalid disk name format: {disk_name}")
                pretty_name = f"Disk {disk_num}"
            except ValueError as err:
                _LOGGER.error("Error parsing disk name %s: %s", disk_name, err)
                pretty_name = disk_name.title()

        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key=f"disk_health_{disk_name}",
                name=f"{pretty_name} Health",
                device_class=BinarySensorDeviceClass.PROBLEM,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:harddisk" if not disk_name == "cache" else "mdi:harddisk",
                has_warning_threshold=True,
            ),
        )
        self._disk_name = disk_name
        # Safer disk number extraction
        self._disk_num = None
        if disk_name.startswith("disk"):
            try:
                self._disk_num = int(''.join(filter(str.isdigit, disk_name)))
            except ValueError:
                _LOGGER.debug("Could not extract disk number from %s", disk_name)

        self._last_smart_check = None
        self._smart_status = None
        self._last_problem_state = None
        self._spin_down_delay = self._get_spin_down_delay()
        self._last_temperature = None
        self._problem_attributes: Dict[str, Any] = {}

        # Get device mapping
        try:
            if disk_name == "cache":
                # Get cache device info from system stats
                cache_info = coordinator.data.get("system_stats", {}).get("cache_usage", {})
                if cache_info and "device" in cache_info:
                    self._device = cache_info["device"]
                else:
                    # Fallback to disk data
                    for disk in coordinator.data.get("system_stats", {}).get("individual_disks", []):
                        if disk.get("name") == "cache":
                            self._device = disk.get("device")
                            break
                    if not self._device:
                        self._device = "nvme0n1p1"  # Final fallback for cache device
            else:
                disk_mapping = get_unraid_disk_mapping(self.coordinator.data.get("system_stats", {}))
                self._device = disk_mapping.get(disk_name)

        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug(
                "Error getting device mapping for %s: %s",
                disk_name,
                err
            )
            self._device = None

        _LOGGER.debug(
            "Initialized disk health sensor for %s (device: %s)", 
            disk_name,
            self._device or "unknown"
        )

    def _get_spin_down_delay(self) -> SpinDownDelay:
        """Get spin down delay for this disk."""
        try:
            disk_cfg = self.coordinator.data.get("disk_config", {})
            # Get global setting (default to NEVER/0 if not specified)
            global_delay = int(disk_cfg.get("spindownDelay", "0"))
            # Check for disk-specific setting if this is an array disk
            if self._disk_num is not None:
                disk_delay = disk_cfg.get(f"diskSpindownDelay.{self._disk_num}")
                if disk_delay and disk_delay != "-1":  # -1 means use global setting
                    global_delay = int(disk_delay)
            # Convert to SpinDownDelay enum
            return SpinDownDelay(global_delay)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Error getting spin down delay for %s: %s. Using default Never.",
                self._disk_name,
                err
            )
            return SpinDownDelay.NEVER

    def _analyze_smart_status(self, disk_data: Dict[str, Any]) -> bool:
        """Analyze SMART status and attributes for actual problems."""
        self._problem_attributes = {}

        # First check disk status
        disk_status = disk_data.get("status", "unknown").lower()
        if disk_status == "standby":
            # Use cached state for standby disks
            return self._last_problem_state if self._last_problem_state is not None else False

        has_problem = False
        is_nvme = disk_data.get("transport") == "nvme"

        # Check basic SMART status
        smart_status = disk_data.get("health", "healthy")  # Default to healthy
        if smart_status not in ["PASSED", "Standby", "healthy", "OK", "GOOD", "DISK_OK"]:
            if smart_status.lower() != "unknown":  # Don't treat Unknown as a problem
                self._problem_attributes["smart_status"] = smart_status
                has_problem = True

        # Check critical attributes if available
        if not is_nvme:  # Traditional SMART attributes for non-NVMe
            if reallocated := int(disk_data.get("reallocated_sectors", 0)):
                self._problem_attributes["reallocated_sectors"] = reallocated
                has_problem = True

            if pending := int(disk_data.get("pending_sectors", 0)):
                self._problem_attributes["pending_sectors"] = pending
                has_problem = True

            if uncorrectable := int(disk_data.get("offline_uncorrectable", 0)):
                self._problem_attributes["offline_uncorrectable"] = uncorrectable
                has_problem = True
        else:
            # NVMe specific checks
            if media_errors := int(disk_data.get("media_errors", 0)):
                self._problem_attributes["media_errors"] = media_errors
                has_problem = True

        # Temperature check - handle both string and integer values
        try:
            temp = disk_data.get("temperature")
            if isinstance(temp, str) and '°C' in temp:
                temp = int(temp.rstrip('°C'))
            elif isinstance(temp, (int, float)):
                temp = int(temp)

            # NVMe drives typically have higher temperature thresholds
            temp_threshold = 70 if is_nvme else 55
            if temp > temp_threshold:
                self._problem_attributes["temperature"] = f"{temp}°C"
                has_problem = True

        except (ValueError, TypeError, AttributeError):
            pass

        # Only consider UDMA errors if they're increasing (for non-NVMe)
        if not is_nvme:
            current_udma = int(disk_data.get("udma_crc_errors", 0))
            previous_udma = int(disk_data.get("udma_crc_errors_prev", 0))
            if current_udma > previous_udma:
                self._problem_attributes["udma_crc_errors"] = (
                    f"{current_udma} (increased from {previous_udma})"
                )
                has_problem = True

        # Store state for standby usage
        self._last_problem_state = has_problem
        return has_problem

    @property
    def is_on(self) -> bool | None:
        """Return true if there's a problem with the disk."""
        try:
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Update spin down delay if changed
                    new_delay = SpinDownDelay(disk.get("spin_down_delay", SpinDownDelay.MINUTES_30))
                    if new_delay != self._spin_down_delay:
                        self._spin_down_delay = new_delay
                        _LOGGER.debug(
                            "Updated spin down delay for %s to %s",
                            self._disk_name,
                            self._spin_down_delay.to_human_readable()
                        )

                    # If disk is in standby, return cached state
                    if disk.get("status") == "standby":
                        return self._last_problem_state if self._last_problem_state is not None else False

                    current_time = datetime.now(timezone.utc)
                    should_check_smart = (
                        self._smart_status is None  # First check
                        or self._spin_down_delay == SpinDownDelay.NEVER  # Never spin down
                        or (
                            self._last_smart_check is not None
                            and (
                                current_time - self._last_smart_check
                            ).total_seconds() >= self._spin_down_delay.to_seconds()
                        )
                    )

                    if should_check_smart:
                        self._smart_status = disk.get("health")
                        self._last_smart_check = current_time
                        return self._analyze_smart_status(disk)

                    # Use cached status
                    result = self._smart_status != "PASSED"
                    self._last_problem_state = result
                    return result

            return None
        except (KeyError, AttributeError, TypeError, ValueError) as err:
            _LOGGER.debug("Error checking disk health: %s", err)
            return self._last_problem_state if self._last_problem_state is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return additional state attributes."""
        try:
            # Get disk info from mapping
            for disk in self.coordinator.data["system_stats"]["individual_disks"]:
                if disk["name"] == self._disk_name:
                    # Disk information
                    attrs = {
                        "mount_point": disk["mount_point"],
                        "device": self._device or disk.get("device", "unknown"),
                    }

                    # Handle temperature
                    temp = disk.get("temperature")
                    if temp is not None:
                        if isinstance(temp, str) and '°C' in temp:
                            attrs["temperature"] = temp
                        else:
                            attrs["temperature"] = f"{temp}°C"
                    else:
                        attrs["temperature"] = "0°C"

                    # Usage information
                    attrs.update({
                        "current_usage": f"{disk['percentage']:.1f}%",
                        "total_size": format_bytes(disk["total"]),
                        "used_space": format_bytes(disk["used"]),
                        "free_space": format_bytes(disk["free"]),
                    })

                    # Status information
                    attrs.update({
                        "smart_status": disk.get("health", "healthy"),  # Default to healthy
                        "disk_status": disk.get("status", "unknown"),
                        "spin_down_delay": self._spin_down_delay.to_human_readable(),
                    })

                    # Add problem details if any exist
                    if self._problem_attributes:
                        attrs["problem_details"] = self._problem_attributes

                    return attrs
            return {}
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Missing key in disk data: %s", err)
            return {}

class UnraidUPSBinarySensor(UnraidBinarySensorEntity):
    """Binary sensor for UPS status."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
    ) -> None:
        """Initialize the UPS binary sensor."""
        super().__init__(
            coordinator,
            UnraidBinarySensorEntityDescription(
                key="ups_status",
                name="UPS Status",  # Base class will add Unraid prefix
                device_class=BinarySensorDeviceClass.POWER,  # Changed to POWER device class
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:battery-medium",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        ups_info = self.coordinator.data.get("system_stats", {}).get("ups_info")
        return self.coordinator.last_update_success and bool(ups_info)

    @property
    def is_on(self) -> bool | None:
        """Return true if the UPS is online."""
        try:
            status = self.coordinator.data["system_stats"].get("ups_info", {}).get("STATUS")
            if status is None:
                return None
            return status.upper() in ["ONLINE", "ON LINE"]
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting UPS status: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            ups_info = self.coordinator.data["system_stats"].get("ups_info", {})

            # Format numeric values with units
            attrs = {
                "model": ups_info.get("MODEL", "Unknown"),
                "status": ups_info.get("STATUS", "Unknown"),
            }
            # Add percentage values
            if "BCHARGE" in ups_info:
                attrs["battery_charge"] = f"{ups_info['BCHARGE']}%"
            if "LOADPCT" in ups_info:
                attrs["load_percentage"] = f"{ups_info['LOADPCT']}%"
            # Add time values
            if "TIMELEFT" in ups_info:
                attrs["runtime_left"] = f"{ups_info['TIMELEFT']} minutes"
            # Add power/voltage values
            if "NOMPOWER" in ups_info:
                attrs["nominal_power"] = f"{ups_info['NOMPOWER']}W"
            if "LINEV" in ups_info:
                attrs["line_voltage"] = f"{ups_info['LINEV']}V"
            if "BATTV" in ups_info:
                attrs["battery_voltage"] = f"{ups_info['BATTV']}V"

            return attrs
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting UPS attributes: %s", err)
            return {}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensors."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[UnraidBinarySensorEntity] = []
    processed_disks = set()  # Track processed disks

    # Add base sensors first
    for description in SENSOR_DESCRIPTIONS:
        entities.append(UnraidBinarySensorEntity(coordinator, description))

    # Add UPS sensor if UPS info is available
    if coordinator.data.get("system_stats", {}).get("ups_info"):
        entities.append(UnraidUPSBinarySensor(coordinator))

    # Filter out tmpfs and special mounts
    ignored_mounts = {
        "disks", "remotes", "addons", "rootshare", 
        "user/0", "dev/shm"
    }

    # Process disk health sensors
    disk_data = coordinator.data.get("system_stats", {}).get("individual_disks", [])
    valid_disks = [
        disk for disk in disk_data
        if (
            disk.get("name")
            and not any(mount in disk.get("mount_point", "") for mount in ignored_mounts)
            and disk.get("filesystem") != "tmpfs"
        )
    ]

    for disk in valid_disks:
        disk_name = disk.get("name")

        # Skip if invalid or already processed
        if not disk_name or disk_name in processed_disks:
            continue

        if disk_name.startswith("disk") or disk_name == "cache":
            _LOGGER.debug(
                "Adding health sensor for disk: %s", 
                disk_name
            )
            try:
                entities.append(
                    UnraidDiskHealthSensor(
                        coordinator=coordinator,
                        disk_name=disk_name
                    )
                )
                processed_disks.add(disk_name)
            except ValueError as err:
                _LOGGER.warning("Skipping invalid disk %s: %s", disk_name, err)
                continue

    async_add_entities(entities)
