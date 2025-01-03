"""System-related sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Any, Optional
from datetime import timedelta

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidSensorBase
from .const import (
    CPU_TEMP_PATTERNS,
    DOMAIN, 
    MOTHERBOARD_TEMP_PATTERNS,
    VALID_CPU_TEMP_RANGE,
    VALID_MB_TEMP_RANGE, 
    UnraidSensorEntityDescription,
)
from ..helpers import (
    format_bytes,
    get_acpi_temp_input,
    get_auxtin_temp_input,
    get_core_temp_input,
    get_ec_temp_input,
    get_peci_temp_input,
    get_system_temp_input,
    get_tccd_temp_input,
)
from ..naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

class UnraidCPUUsageSensor(UnraidSensorBase):
    """CPU usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="cpu"
        )

        description = UnraidSensorEntityDescription(
            key="cpu_usage",
            name=f"{naming.get_entity_name('cpu', 'cpu')} Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:cpu-64-bit",
            suggested_display_precision=1,
            value_fn=lambda data: data.get("system_stats", {}).get("cpu_usage"),
            available_fn=lambda data: (
                "system_stats" in data 
                and data.get("system_stats", {}).get("cpu_usage") is not None
            ),
        )
        super().__init__(coordinator, description)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self.coordinator.data.get("system_stats", {})
        
        attributes = {
            "last_update": dt_util.now().isoformat(),
            "core_count": data.get("cpu_cores", 0),
            "architecture": data.get("cpu_arch", "unknown"),
            "model": data.get("cpu_model", "unknown"),
            "threads_per_core": data.get("cpu_threads_per_core", 0),
            "physical_sockets": data.get("cpu_sockets", 0),
            "max_frequency": f"{data.get('cpu_max_freq', 0)} MHz",
            "min_frequency": f"{data.get('cpu_min_freq', 0)} MHz",
        }

        # Add temperature info if available
        if "cpu_temp" in data:
            attributes.update({
                "temperature": f"{data['cpu_temp']}°C",
                "temperature_warning": data.get("cpu_temp_warning", False),
                "temperature_critical": data.get("cpu_temp_critical", False),
            })
        
        # Only include non-zero/unknown values
        return {k: v for k, v in attributes.items() 
                if v not in (0, "unknown", "0 MHz")}

class UnraidRAMUsageSensor(UnraidSensorBase):
    """RAM usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="ram"
        )

        description = UnraidSensorEntityDescription(
            key="ram_usage",
            name=f"{naming.get_entity_name('ram', 'ram')} Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:memory",
            suggested_display_precision=1,
            value_fn=lambda data: round(
                data.get("system_stats", {})
                .get("memory_usage", {})
                .get("percentage", 0), 1
            ),
        )
        super().__init__(coordinator, description)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        memory = self.coordinator.data.get("system_stats", {}).get("memory_usage", {})
        return {
            "total": memory.get("total", "unknown"),
            "used": memory.get("used", "unknown"),
            "free": memory.get("free", "unknown"),
            "cached": memory.get("cached", "unknown"),
            "buffers": memory.get("buffers", "unknown"),
            "last_update": dt_util.now().isoformat(),
        }

class UnraidCPUTempSensor(UnraidSensorBase):
    """CPU temperature sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="cpu"
        )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="cpu_temperature",
                name=f"{naming.get_entity_name('cpu', 'cpu')} Temperature",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:thermometer",
                suggested_display_precision=1,
                value_fn=self._get_temperature
            ),
        )

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get CPU temperature from data with dynamic core detection."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            for device_name, device_data in sensors_data.items():
                if not isinstance(device_data, dict):
                    continue

                # First check static patterns
                for sensor_name, temp_key in CPU_TEMP_PATTERNS:
                    if sensor_name in device_data:
                        sensor_data = device_data[sensor_name]
                        if isinstance(sensor_data, dict):
                            reading = sensor_data.get(temp_key)
                        else:
                            reading = sensor_data

                        if reading is not None:
                            if temp := self._parse_temperature(str(reading)):
                                if VALID_CPU_TEMP_RANGE[0] <= temp <= VALID_CPU_TEMP_RANGE[1]:
                                    return round(temp, 1)

                # Then try dynamic patterns
                for label, values in device_data.items():
                    # Try CPU cores
                    if temp_key := get_core_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_CPU_TEMP_RANGE[0] <= temp <= VALID_CPU_TEMP_RANGE[1]:
                                        return round(temp, 1)

                    # Try AMD CCDs
                    if temp_key := get_tccd_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_CPU_TEMP_RANGE[0] <= temp <= VALID_CPU_TEMP_RANGE[1]:
                                        return round(temp, 1)

                    # Try PECI agents
                    if temp_key := get_peci_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_CPU_TEMP_RANGE[0] <= temp <= VALID_CPU_TEMP_RANGE[1]:
                                        return round(temp, 1)

            return None
            
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.debug("Error getting CPU temperature: %s", err)
            return None

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Parse temperature value from string."""
        try:
            # Remove common temperature markers and convert to float
            cleaned = value.replace('°C', '').replace(' C', '').replace('+', '').strip()
            temp = float(cleaned)
            return temp
        except (ValueError, TypeError):
            return None

class UnraidMotherboardTempSensor(UnraidSensorBase):
    """Representation of Unraid motherboard temperature sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="motherboard"
        )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="motherboard_temperature",
                name=f"{naming.get_entity_name('motherboard', 'motherboard')} Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                value_fn=self._get_temperature
            ),
        )

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get motherboard temperature from data with dynamic pattern matching."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            # Check each temperature source in priority order
            for device_name, device_data in sensors_data.items():
                if not isinstance(device_data, dict):
                    continue

                # 1. First check static patterns from MOTHERBOARD_TEMP_PATTERNS
                for sensor_name, temp_key in MOTHERBOARD_TEMP_PATTERNS:
                    if sensor_name not in device_data:
                        continue

                    sensor_data = device_data[sensor_name]
                    # Handle both nested dict and direct value cases
                    if isinstance(sensor_data, dict):
                        reading = sensor_data.get(temp_key)
                    else:
                        reading = sensor_data

                    if reading is not None:
                        if temp := self._parse_temperature(str(reading)):
                            if VALID_MB_TEMP_RANGE[0] <= temp <= VALID_MB_TEMP_RANGE[1]:
                                return round(temp, 1)

                # 2. Try dynamic patterns for each sensor label
                for label, values in device_data.items():
                    # Try ACPI temperatures
                    if temp_key := get_acpi_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_MB_TEMP_RANGE[0] <= temp <= VALID_MB_TEMP_RANGE[1]:
                                        return round(temp, 1)

                    # Try System N temperatures
                    if temp_key := get_system_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_MB_TEMP_RANGE[0] <= temp <= VALID_MB_TEMP_RANGE[1]:
                                        return round(temp, 1)

                    # Try EC_TEMP[N] sensors
                    if temp_key := get_ec_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_MB_TEMP_RANGE[0] <= temp <= VALID_MB_TEMP_RANGE[1]:
                                        return round(temp, 1)

                    # Try AUXTIN[N] sensors
                    if temp_key := get_auxtin_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := self._parse_temperature(str(reading)):
                                    if VALID_MB_TEMP_RANGE[0] <= temp <= VALID_MB_TEMP_RANGE[1]:
                                        return round(temp, 1)

            # If no valid temperature found
            _LOGGER.debug("No valid motherboard temperature found in sensors data")
            return None

        except (KeyError, TypeError, ValueError, AttributeError) as err:
            _LOGGER.debug("Error getting motherboard temperature: %s", err)
            return None

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Parse temperature value from string."""
        try:
            # Remove common temperature markers and convert to float
            cleaned = value.replace('°C', '').replace(' C', '').replace('+', '').strip()
            temp = float(cleaned)
            return temp
        except (ValueError, TypeError):
            return None

class UnraidFanSensor(UnraidSensorBase):
    """Fan speed sensor for Unraid."""

    def __init__(self, coordinator, fan_id: str, fan_data: dict) -> None:
        """Initialize the fan sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="fan"
        )
        
        # Get clean fan label
        display_name = fan_data["label"]
        
        _LOGGER.debug(
            "Initializing fan sensor - ID: %s, Label: %s",
            fan_id,
            display_name
        )
        
        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key=f"fan_{fan_id}",
                name=f"{naming.get_entity_name(display_name, 'fan')}",  # Simplified name
                native_unit_of_measurement="rpm",
                device_class=None,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:fan",
                suggested_display_precision=0,
                value_fn=lambda data: (
                    data.get("system_stats", {})
                    .get("temperature_data", {})
                    .get("fans", {})
                    .get(fan_id, {})
                    .get("rpm")
                )
            ),
        )
        self._fan_id = fan_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            fan_data = (
                self.coordinator.data.get("system_stats", {})
                .get("temperature_data", {})
                .get("fans", {})
                .get(self._fan_id, {})
            )
            
            return {
                "device": fan_data.get("device"),
                "label": fan_data.get("label"),
                "last_update": dt_util.now().isoformat()
            }
        except Exception as err:
            _LOGGER.debug("Error getting fan attributes: %s", err)
            return {}

class UnraidDockerVDiskSensor(UnraidSensorBase):
    """Docker vDisk usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="docker_vdisk",
                name=f"{naming.get_entity_name('vDisk', 'docker')} Usage",
                native_unit_of_measurement=PERCENTAGE,
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:docker",
                value_fn=lambda data: data.get("system_stats", {})
                                    .get("docker_vdisk", {})
                                    .get("percentage")
            ),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            docker_vdisk = (
                self.coordinator.data.get("system_stats", {})
                .get("docker_vdisk", {})
            )
            return {
                "total_size": format_bytes(docker_vdisk.get("total", 0)),
                "used_space": format_bytes(docker_vdisk.get("used", 0)),
                "free_space": format_bytes(docker_vdisk.get("free", 0)),
                "last_update": dt_util.now().isoformat(),
            }
        except (KeyError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting Docker vDisk attributes: %s", err)
            return {}

class UnraidLogFileSystemSensor(UnraidSensorBase):
    """Log filesystem usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="log"
        )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="log_filesystem",
                name=f"{naming.get_entity_name('Log Filesystem')} Usage",
                native_unit_of_measurement=PERCENTAGE,
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:file-document",
                value_fn=lambda data: data.get("system_stats", {})
                                    .get("log_filesystem", {})
                                    .get("percentage")
            ),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            log_fs = (
                self.coordinator.data.get("system_stats", {})
                .get("log_filesystem", {})
            )
            return {
                "total_size": format_bytes(log_fs.get("total", 0)),
                "used_space": format_bytes(log_fs.get("used", 0)),
                "free_space": format_bytes(log_fs.get("free", 0)),
                "last_update": dt_util.now().isoformat(),
            }
        except (KeyError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting log filesystem attributes: %s", err)
            return {}

class UnraidBootUsageSensor(UnraidSensorBase):
    """Boot device usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="boot"
        )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="boot_usage",
                name=f"{naming.get_entity_name('Flash Device', 'boot')} Usage",
                native_unit_of_measurement=PERCENTAGE,
                device_class=SensorDeviceClass.POWER_FACTOR,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:usb-flash-drive",
                value_fn=lambda data: data.get("system_stats", {})
                                    .get("boot_usage", {})
                                    .get("percentage")
            ),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            boot_usage = (
                self.coordinator.data.get("system_stats", {})
                .get("boot_usage", {})
            )
            return {
                "total_size": format_bytes(boot_usage.get("total", 0)),
                "used_space": format_bytes(boot_usage.get("used", 0)),
                "free_space": format_bytes(boot_usage.get("free", 0)),
                "last_update": dt_util.now().isoformat(),
            }
        except (KeyError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting boot usage attributes: %s", err)
            return {}

class UnraidUptimeSensor(UnraidSensorBase):
    """Uptime sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="uptime"
        )

        description = UnraidSensorEntityDescription(
            key="uptime",
            name=f"{naming.get_entity_name('uptime', 'uptime')} Status",
            icon="mdi:clock-outline",
            value_fn=self._format_uptime,
            available_fn=lambda data: (
                "system_stats" in data 
                and data.get("system_stats", {}).get("uptime") is not None
            ),
        )
        super().__init__(coordinator, description)
        self._boot_time = None

    def _format_uptime(self, data: dict) -> str:
        """Format uptime string."""
        try:
            uptime_seconds = float(data.get("system_stats", {}).get("uptime", 0))
            days, remainder = divmod(int(uptime_seconds), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            self._boot_time = dt_util.now() - timedelta(seconds=uptime_seconds)
            return f"{days}d {hours}h {minutes}m"
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error formatting uptime: %s", err)
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "boot_time": self._boot_time.isoformat() if self._boot_time else None,
            "last_update": dt_util.now().isoformat(),
        }

class UnraidSystemSensors:
    """Helper class to create all system sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize system sensors."""
        self.entities = [
            UnraidCPUUsageSensor(coordinator),
            UnraidRAMUsageSensor(coordinator),
            UnraidUptimeSensor(coordinator),
            UnraidCPUTempSensor(coordinator),
            UnraidMotherboardTempSensor(coordinator),
            UnraidDockerVDiskSensor(coordinator),
            UnraidLogFileSystemSensor(coordinator),
            UnraidBootUsageSensor(coordinator),
        ]

        # Add fan sensors if available
        fan_data = (
            coordinator.data.get("system_stats", {})
            .get("temperature_data", {})
            .get("fans", {})
        )
        
        if fan_data:
            for fan_id, fan_info in fan_data.items():
                self.entities.append(
                    UnraidFanSensor(coordinator, fan_id, fan_info)
                )
                _LOGGER.debug(
                    "Added fan sensor: %s (%s)",
                    fan_id,
                    fan_info.get("label", "unknown")
                )
