"""System-related sensors for Unraid."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, EntityCategory # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .base import UnraidSensorBase
from .const import (
    UnraidSensorEntityDescription,
    CPU_TEMP_PATTERNS,
    MOTHERBOARD_TEMP_PATTERNS,
)
from ..utils import (
    format_bytes,
    get_temp_input,
    parse_temperature,
    find_temperature_inputs,
    is_valid_temp_range
)


_LOGGER = logging.getLogger(__name__)

class UnraidCPUUsageSensor(UnraidSensorBase):
    """CPU usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""


        description = UnraidSensorEntityDescription(
            key="cpu_usage",
            name="CPU Usage",
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
        """Return additional state attributes with user-friendly formatting."""
        data = self.coordinator.data.get("system_stats", {})



        attributes = {
            "last_update": dt_util.now().isoformat(),
        }

        # Add CPU information with user-friendly formatting
        if core_count := data.get("cpu_cores", 0):
            attributes["processor_cores"] = f"{core_count} cores"

        if arch := data.get("cpu_arch"):
            if arch != "unknown":
                attributes["processor_architecture"] = arch.upper()

        if model := data.get("cpu_model"):
            if model != "unknown":
                attributes["processor_model"] = model

        if threads := data.get("cpu_threads_per_core", 0):
            if threads > 0:
                attributes["threads_per_core"] = f"{threads} threads"

        if sockets := data.get("cpu_sockets", 0):
            if sockets > 0:
                attributes["physical_sockets"] = f"{sockets} socket{'s' if sockets > 1 else ''}"

        # Format frequencies with proper units
        if max_freq := data.get("cpu_max_freq", 0):
            if max_freq > 0:
                if max_freq >= 1000:
                    attributes["maximum_frequency"] = f"{max_freq / 1000:.2f} GHz"
                else:
                    attributes["maximum_frequency"] = f"{max_freq} MHz"

        if min_freq := data.get("cpu_min_freq", 0):
            if min_freq > 0:
                if min_freq >= 1000:
                    attributes["minimum_frequency"] = f"{min_freq / 1000:.2f} GHz"
                else:
                    attributes["minimum_frequency"] = f"{min_freq} MHz"

        # Add temperature info with status indicators if available
        if cpu_temp := data.get("cpu_temp"):
            attributes["temperature"] = f"{cpu_temp}°C"

            # Add temperature status with user-friendly descriptions
            if data.get("cpu_temp_critical", False):
                attributes["temperature_status"] = "Critical - Immediate attention required"
            elif data.get("cpu_temp_warning", False):
                attributes["temperature_status"] = "Warning - Monitor closely"
            else:
                attributes["temperature_status"] = "Normal"

        return attributes

class UnraidRAMUsageSensor(UnraidSensorBase):
    """RAM usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""


        description = UnraidSensorEntityDescription(
            key="ram_usage",
            name="RAM Usage",
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


        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="cpu_temperature",
                name="CPU Temperature",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:thermometer",
                suggested_display_precision=1,
                value_fn=self._get_temperature
            ),
        )
        self._last_valid_temp: Optional[float] = None
        self._last_update: Optional[datetime] = None
        self._detected_source: Optional[str] = None

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get CPU temperature with comprehensive detection."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            if not sensors_data:
                return self._last_valid_temp

            # Step 1: Try static patterns first
            for device_name, device_data in sensors_data.items():
                if not isinstance(device_data, dict):
                    continue

                # Check CPU_TEMP_PATTERNS
                for sensor_name, temp_key in CPU_TEMP_PATTERNS:
                    if sensor_name in device_data:
                        sensor_data = device_data[sensor_name]
                        if isinstance(sensor_data, dict):
                            reading = sensor_data.get(temp_key)
                        else:
                            reading = sensor_data

                        if reading is not None:
                            if temp := parse_temperature(str(reading)):
                                if is_valid_temp_range(temp, is_cpu=True):
                                    self._last_valid_temp = round(temp, 1)
                                    self._last_update = dt_util.utcnow()
                                    self._detected_source = f"{device_name}/{sensor_name}"
                                    return self._last_valid_temp

                # Try dynamic core patterns
                for label, values in device_data.items():
                    if temp_key := get_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := parse_temperature(str(reading)):
                                    if is_valid_temp_range(temp, is_cpu=True):
                                        self._last_valid_temp = round(temp, 1)
                                        self._last_update = dt_util.utcnow()
                                        self._detected_source = f"{device_name}/{label}"
                                        return self._last_valid_temp

            # Step 2: Dynamic detection fallback
            temps = find_temperature_inputs(sensors_data)
            cpu_temps = temps.get('cpu', set())

            if cpu_temps:
                # Filter valid temps and sort by value (highest usually most relevant for CPU)
                valid_temps = sorted(
                    [t for t in cpu_temps if t.is_valid],
                    key=lambda x: x.value,
                    reverse=True
                )

                if valid_temps:
                    temp = valid_temps[0].value
                    self._last_valid_temp = round(temp, 1)
                    self._last_update = dt_util.utcnow()
                    self._detected_source = f"{valid_temps[0].chip}/{valid_temps[0].label}"
                    return self._last_valid_temp

            return self._last_valid_temp

        except Exception as err:
            _LOGGER.debug("Error getting CPU temperature: %s", err)
            return self._last_valid_temp

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {  # Initialize a new dict instead of using super()
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "sensor_source": self._detected_source,
        }
        return attrs

class UnraidMotherboardTempSensor(UnraidSensorBase):
    """Representation of Unraid motherboard temperature sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""


        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="motherboard_temperature",
                name="Motherboard Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                value_fn=self._get_temperature
            ),
        )
        self._last_valid_temp: Optional[float] = None
        self._last_update: Optional[datetime] = None
        self._detected_source: Optional[str] = None

    def _get_temperature(self, data: dict) -> Optional[float]:
        """Get motherboard temperature with comprehensive detection."""
        try:
            temp_data = data["system_stats"].get("temperature_data", {})
            sensors_data = temp_data.get("sensors", {})

            if not sensors_data:
                return self._last_valid_temp

            # Step 1: Try static patterns first
            for device_name, device_data in sensors_data.items():
                if not isinstance(device_data, dict):
                    continue

                # Check static MOTHERBOARD_TEMP_PATTERNS
                for sensor_name, temp_key in MOTHERBOARD_TEMP_PATTERNS:
                    if sensor_name not in device_data:
                        continue

                    sensor_data = device_data[sensor_name]
                    if isinstance(sensor_data, dict):
                        reading = sensor_data.get(temp_key)
                    else:
                        reading = sensor_data

                    if reading is not None:
                        if temp := parse_temperature(str(reading)):
                            if is_valid_temp_range(temp, is_cpu=False):
                                self._last_valid_temp = round(temp, 1)
                                self._last_update = dt_util.utcnow()
                                self._detected_source = f"{device_name}/{sensor_name}"
                                return self._last_valid_temp

                # Try dynamic patterns
                for label, values in device_data.items():
                    if temp_key := get_temp_input(label):
                        if isinstance(values, dict):
                            reading = values.get(temp_key)
                            if reading is not None:
                                if temp := parse_temperature(str(reading)):
                                    if is_valid_temp_range(temp, is_cpu=False):
                                        self._last_valid_temp = round(temp, 1)
                                        self._last_update = dt_util.utcnow()
                                        self._detected_source = f"{device_name}/{label}"
                                        return self._last_valid_temp

            # Step 2: Dynamic detection fallback
            temps = find_temperature_inputs(sensors_data)
            mb_temps = temps.get('mb', set())

            if mb_temps:
                # Filter valid temps and use median for stability
                valid_temps = [t for t in mb_temps if t.is_valid]

                if valid_temps:
                    # Take median value as it's more stable for motherboard temps
                    sorted_temps = sorted(valid_temps, key=lambda x: x.value)
                    median_idx = len(sorted_temps) // 2
                    temp = sorted_temps[median_idx].value
                    self._last_valid_temp = round(temp, 1)
                    self._last_update = dt_util.utcnow()
                    self._detected_source = f"{sorted_temps[median_idx].chip}/{sorted_temps[median_idx].label}"
                    return self._last_valid_temp

            return self._last_valid_temp

        except Exception as err:
            _LOGGER.debug("Error getting motherboard temperature: %s", err)
            return self._last_valid_temp

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {  # Directly create attributes dictionary
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "sensor_source": self._detected_source,
        }
        return attrs

class UnraidFanSensor(UnraidSensorBase):
    """Fan speed sensor for Unraid."""

    def __init__(self, coordinator, fan_id: str, fan_data: dict) -> None:
        """Initialize the fan sensor."""


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
                name=f"{display_name.replace('NCT67 ', '')}",  # Clean display name
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


        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="docker_vdisk",
                name="Docker vDisk Usage",
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


        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="log_filesystem",
                name="Log Filesystem Usage",
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
        # Entity naming not used in this class
        # EntityNaming(
        #     domain=DOMAIN,
        #     hostname=coordinator.hostname,
        #     component="boot"
        # )

        super().__init__(
            coordinator,
            UnraidSensorEntityDescription(
                key="boot_usage",
                name="Flash Device Usage",
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
        # Entity naming not used in this class
        # EntityNaming(
        #     domain=DOMAIN,
        #     hostname=coordinator.hostname,
        #     component="uptime"
        # )

        description = UnraidSensorEntityDescription(
            key="uptime",
            name="Uptime Status",
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


class UnraidIntelGPUSensor(UnraidSensorBase):
    """Intel GPU usage sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="intel_gpu_usage",
            name="Intel GPU Usage",
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:expansion-card",
            suggested_display_precision=1,
            value_fn=self._get_gpu_usage,
            available_fn=lambda data: (
                "system_stats" in data
                and data.get("system_stats", {}).get("intel_gpu") is not None
            ),
        )
        super().__init__(coordinator, description)

    def _get_gpu_usage(self, data: dict) -> float | None:
        """Get Intel GPU usage percentage."""
        try:
            gpu_data = data.get("system_stats", {}).get("intel_gpu", {})
            if not gpu_data:
                return None

            # Get GPU usage percentage
            usage = gpu_data.get("usage_percentage")
            if usage is not None:
                return round(float(usage), 1)

            return None
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error getting Intel GPU usage: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            gpu_data = self.coordinator.data.get("system_stats", {}).get("intel_gpu", {})
            if not gpu_data:
                return {}

            attrs = {
                "GPU Model": gpu_data.get("model", "Unknown Intel GPU"),
                "Last Updated": dt_util.now().isoformat(),
            }

            # Add power consumption if available
            if power := gpu_data.get("power_watts"):
                attrs["Power Draw"] = f"{power} W"

            # Add frequency information if available
            if freq := gpu_data.get("frequency_mhz"):
                attrs["GPU Frequency"] = f"{freq} MHz"

            # Add memory bandwidth if available
            if read_bw := gpu_data.get("memory_bandwidth_read"):
                attrs["Memory Read Bandwidth"] = f"{read_bw} MB/s"

            if write_bw := gpu_data.get("memory_bandwidth_write"):
                attrs["Memory Write Bandwidth"] = f"{write_bw} MB/s"

            # Add engine utilization breakdown if available
            engines = gpu_data.get("engines", {})
            if engines:
                for engine_name, engine_usage in engines.items():
                    if engine_usage is not None:
                        # Clean up engine names for better readability
                        clean_name = engine_name.replace("/", " ").replace("0", "").strip()
                        if clean_name.endswith(" "):
                            clean_name = clean_name[:-1]
                        attrs[f"{clean_name} Engine"] = f"{engine_usage}%"

            return attrs

        except Exception as err:
            _LOGGER.debug("Error getting Intel GPU attributes: %s", err)
            return {
                "GPU Model": "Unknown Intel GPU",
                "Last Updated": dt_util.now().isoformat(),
            }


class UnraidArrayStatusSensor(UnraidSensorBase):
    """Array status sensor for Unraid."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        description = UnraidSensorEntityDescription(
            key="array_status",
            name="Array Status",
            icon="mdi:harddisk-plus",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=["started", "stopped", "starting", "stopping", "unknown"],
            value_fn=self._get_array_status,
        )
        super().__init__(coordinator, description)

    def _get_array_status(self, data: dict) -> str:
        """Get array status."""
        try:
            # Try to get array_state first (from batched command)
            array_data = data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = data.get("system_stats", {}).get("array_status", {})

            # Get state from the data
            if isinstance(array_data, dict):
                state = array_data.get("state", "unknown").lower()
            elif isinstance(array_data, str):
                state = array_data.lower()
            else:
                state = "unknown"

            # Normalize state values
            if state == "started":
                return "started"
            elif state == "stopped":
                return "stopped"
            elif "start" in state:
                return "starting"
            elif "stop" in state:
                return "stopping"
            else:
                return "unknown"
        except Exception as err:
            _LOGGER.debug("Error getting array status: %s", err)
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        try:
            # Try to get array_state first (from batched command)
            array_data = self.coordinator.data.get("system_stats", {}).get("array_state", {})
            if not array_data:
                # Fall back to array_status if available
                array_data = self.coordinator.data.get("system_stats", {}).get("array_status", {})

            # If array_data is a string, just return the raw state
            if isinstance(array_data, str):
                return {
                    "raw_state": array_data,
                    "last_update": dt_util.now().isoformat(),
                }

            # Otherwise, extract all the attributes
            return {
                "raw_state": array_data.get("state", "unknown"),
                "synced": array_data.get("synced", False),
                "sync_action": array_data.get("sync_action"),
                "sync_progress": array_data.get("sync_progress", 0),
                "sync_errors": array_data.get("sync_errors", 0),
                "num_disks": array_data.get("num_disks", 0),
                "num_disabled": array_data.get("num_disabled", 0),
                "num_invalid": array_data.get("num_invalid", 0),
                "num_missing": array_data.get("num_missing", 0),
                "last_update": dt_util.now().isoformat(),
            }
        except Exception as err:
            _LOGGER.debug("Error getting array attributes: %s", err)
            return {}

class UnraidSystemSensors:
    """Helper class to create all system sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize system sensors."""
        self.entities = [
            UnraidCPUUsageSensor(coordinator),
            UnraidRAMUsageSensor(coordinator),
            # Array Status sensor moved to binary sensors
            UnraidUptimeSensor(coordinator),
            UnraidCPUTempSensor(coordinator),
            UnraidMotherboardTempSensor(coordinator),
            UnraidDockerVDiskSensor(coordinator),
            UnraidLogFileSystemSensor(coordinator),
            UnraidBootUsageSensor(coordinator),
        ]

        # Add Intel GPU sensor if Intel GPU is detected
        intel_gpu_data = (
            coordinator.data.get("system_stats", {})
            .get("intel_gpu")
        )
        if intel_gpu_data:
            self.entities.append(UnraidIntelGPUSensor(coordinator))
            _LOGGER.debug(
                "Added Intel GPU sensor: %s",
                intel_gpu_data.get("model", "Unknown Intel GPU")
            )

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
