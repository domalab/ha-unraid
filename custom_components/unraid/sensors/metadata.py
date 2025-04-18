"""Sensor metadata for Unraid integration."""
from __future__ import annotations

from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPower,
    UnitOfTime,
    UnitOfEnergy,
    PERCENTAGE,
)

from .const import UnraidSensorEntityDescription
# from ..const import DOMAIN
# from ..entity_naming import EntityNaming

# _LOGGER = logging.getLogger(__name__)


@dataclass
class SensorMetadata:
    """Metadata for a sensor."""

    key: str
    name: str
    device_class: Optional[SensorDeviceClass] = None
    state_class: Optional[SensorStateClass] = None
    native_unit_of_measurement: Optional[str] = None
    icon: Optional[str] = None
    entity_category: Optional[str] = None
    suggested_unit_of_measurement: Optional[str] = None
    suggested_display_precision: Optional[int] = None
    translation_key: Optional[str] = None

    def create_description(
        self,
        value_fn: Callable[[dict[str, Any]], Any],
        available_fn: Optional[Callable[[dict[str, Any]], bool]] = None
    ) -> UnraidSensorEntityDescription:
        """Create a sensor entity description from this metadata."""
        return UnraidSensorEntityDescription(
            key=self.key,
            name=self.name,
            device_class=self.device_class,
            state_class=self.state_class,
            native_unit_of_measurement=self.native_unit_of_measurement,
            icon=self.icon,
            entity_category=self.entity_category,
            value_fn=value_fn,
            available_fn=available_fn or (lambda _: True),
            suggested_unit_of_measurement=self.suggested_unit_of_measurement,
            suggested_display_precision=self.suggested_display_precision,
            translation_key=self.translation_key,
        )


# System sensor metadata
SYSTEM_SENSORS: Dict[str, SensorMetadata] = {
    "cpu_usage": SensorMetadata(
        key="cpu_usage",
        name="CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        suggested_display_precision=1,
    ),
    "ram_usage": SensorMetadata(
        key="ram_usage",
        name="RAM Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        suggested_display_precision=1,
    ),
    "uptime": SensorMetadata(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:clock-outline",
    ),
    "cpu_temp": SensorMetadata(
        key="cpu_temp",
        name="CPU Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        suggested_display_precision=1,
    ),
    "motherboard_temp": SensorMetadata(
        key="motherboard_temp",
        name="Motherboard Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        suggested_display_precision=1,
    ),
    "docker_vdisk": SensorMetadata(
        key="docker_vdisk",
        name="Docker Storage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:docker",
        suggested_display_precision=1,
    ),
    "log_filesystem": SensorMetadata(
        key="log_filesystem",
        name="Log Storage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:file-document-outline",
        suggested_display_precision=1,
    ),
    "boot_usage": SensorMetadata(
        key="boot_usage",
        name="Boot Storage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
        suggested_display_precision=1,
    ),
    "fan": SensorMetadata(
        key="fan",
        name="Fan",
        native_unit_of_measurement="RPM",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        suggested_display_precision=0,
    ),
}

# Storage sensor metadata
STORAGE_SENSORS: Dict[str, SensorMetadata] = {
    "array": SensorMetadata(
        key="array",
        name="Array Usage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
        suggested_display_precision=1,
    ),
    "disk": SensorMetadata(
        key="disk",
        name="Disk Usage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
        suggested_display_precision=1,
    ),
    "pool": SensorMetadata(
        key="pool",
        name="Pool Usage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
        suggested_display_precision=1,
    ),
}

# Network sensor metadata
NETWORK_SENSORS: Dict[str, SensorMetadata] = {
    "network_inbound": SensorMetadata(
        key="network_inbound",
        name="Inbound",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-down",
        suggested_display_precision=2,
    ),
    "network_outbound": SensorMetadata(
        key="network_outbound",
        name="Outbound",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-up",
        suggested_display_precision=2,
    ),
}

# UPS sensor metadata
UPS_SENSORS: Dict[str, SensorMetadata] = {
    "ups_power": SensorMetadata(
        key="ups_current_consumption",
        name="Current Consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug",
        suggested_display_precision=1,
    ),
    "ups_energy": SensorMetadata(
        key="ups_energy_consumption",
        name="Energy Consumption",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        suggested_display_precision=3,
    ),
    "ups_load": SensorMetadata(
        key="ups_load_percentage",
        name="Load Percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        suggested_display_precision=1,
    ),
}

# All sensor metadata
ALL_SENSORS: Dict[str, SensorMetadata] = {
    **SYSTEM_SENSORS,
    **STORAGE_SENSORS,
    **NETWORK_SENSORS,
    **UPS_SENSORS,
}


def get_sensor_description(
    sensor_type: str,
    _: str,  # coordinator_hostname not used
    value_fn: Callable[[dict[str, Any]], Any],
    available_fn: Optional[Callable[[dict[str, Any]], bool]] = None,
    component: Optional[str] = None,
    custom_name: Optional[str] = None,
) -> UnraidSensorEntityDescription:
    """Get a sensor description for a sensor type."""
    if sensor_type not in ALL_SENSORS:
        raise ValueError(f"Unknown sensor type: {sensor_type}")

    metadata = ALL_SENSORS[sensor_type]

    # Determine component from sensor type if not provided
    if component is None:
        component = sensor_type.split('_')[0]

    # Entity naming not used in this function
    # EntityNaming(
    #     domain=DOMAIN,
    #     hostname=coordinator_hostname,
    #     component=component
    # )

    # Create description with custom name if provided
    description = metadata.create_description(value_fn, available_fn)

    # Override name if custom name is provided
    if custom_name:
        description.name = custom_name

    return description
