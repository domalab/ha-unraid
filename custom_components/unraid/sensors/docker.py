"""Docker-related sensors for Unraid."""
from __future__ import annotations

import logging
from typing import Any, Callable
from dataclasses import dataclass, field
from typing import Final

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory # type: ignore

from .base import UnraidSensorBase, UnraidDiagnosticMixin
from .const import DOMAIN
from ..naming import EntityNaming

_LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""
    value_fn: Callable[[dict[str, Any]], Any] = field(default=lambda x: None)
    available_fn: Callable[[dict[str, Any]], bool] = field(default=lambda x: True)

DOCKER_SENSOR_TYPES: Final[tuple[UnraidSensorEntityDescription, ...]] = (
    UnraidSensorEntityDescription(
        key="containers_running",
        name="Running Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("docker_stats", {}).get("summary", {}).get("containers_running", 0)
    ),
    UnraidSensorEntityDescription(
        key="containers_paused",
        name="Paused Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("docker_stats", {}).get("summary", {}).get("containers_paused", 0)
    ),
    UnraidSensorEntityDescription(
        key="total_containers",
        name="Total Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("docker_stats", {}).get("summary", {}).get("total_containers", 0)
    ),
    UnraidSensorEntityDescription(
        key="total_cpu_percentage",
        name="Docker CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("docker_stats", {}).get("summary", {}).get("total_cpu_percentage", 0)
    ),
    UnraidSensorEntityDescription(
        key="total_memory_percentage",
        name="Docker Memory Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("docker_stats", {}).get("summary", {}).get("total_memory_percentage", 0)
    ),
)

class DockerMetricsMixin:
    """Mixin for Docker metrics calculations."""

    def _format_size(self, size_bytes: float) -> str:
        """Format size to appropriate unit."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def _validate_percentage(
        self,
        value: float | None,
        min_value: float = 0.0,
        max_value: float = 100.0
    ) -> float | None:
        """Validate percentage value."""
        if value is None:
            return None
        try:
            value = float(value)
            if min_value <= value <= max_value:
                return round(value, 2)
            _LOGGER.debug(
                "Percentage value %s outside valid range [%s, %s]",
                value,
                min_value,
                max_value
            )
            return None
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error validating percentage: %s", err)
            return None

class UnraidDockerSensor(UnraidSensorBase, UnraidDiagnosticMixin):
    """Docker summary statistics sensor."""

    def __init__(self, coordinator, description: UnraidSensorEntityDescription) -> None:
        """Initialize the sensor."""
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )

        super().__init__(coordinator, description)
        UnraidDiagnosticMixin.__init__(self)
        self._attr_has_entity_name = True

        # Update device info to create Docker parent device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_docker")},
            "name": f"Unraid Docker ({naming.clean_hostname()})",
            "manufacturer": "Docker",
            "model": "Container Engine",
            "via_device": (DOMAIN, coordinator.entry.entry_id),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and bool(self.coordinator.docker_insights)
            and "docker_stats" in self.coordinator.data
        )

class UnraidDockerContainerSensor(UnraidSensorBase, DockerMetricsMixin, UnraidDiagnosticMixin):
    """Docker container sensor with comprehensive metrics."""

    def __init__(self, coordinator, container_name: str) -> None:
        """Initialize the sensor."""
        self.container_name = container_name
        
        # Initialize entity naming
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )
        
        # Create single sensor description for container
        description = UnraidSensorEntityDescription(
            key=f"docker_{container_name.lower()}",
            name=naming.get_entity_name(container_name, "docker"),
            icon="mdi:docker",
            value_fn=self._get_container_state,
            available_fn=self._is_container_available,
        )

        super().__init__(coordinator, description)
        DockerMetricsMixin.__init__(self)
        UnraidDiagnosticMixin.__init__(self)
        self._attr_has_entity_name = True
        
        # Link container sensors to the Docker service with consistent naming
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_docker")},
            "name": f"Unraid Docker ({naming.clean_hostname()})",
            "manufacturer": "Docker",
            "model": "Container Engine",
            "via_device": (DOMAIN, coordinator.entry.entry_id),
        }

    def _get_container_state(self, data: dict) -> str:
        """Get container state."""
        try:
            container = (
                data.get("docker_stats", {})
                .get("containers", {})
                .get(self.container_name, {})
            )
            return container.get("state", "unknown")
        except (KeyError, TypeError, AttributeError):
            return "unknown"

    def _is_container_available(self, data: dict) -> bool:
        """Check if container is available."""
        return (
            self.coordinator.docker_insights
            and "docker_stats" in data
            and self.container_name in data["docker_stats"].get("containers", {})
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional container attributes."""
        try:
            container = (
                self.coordinator.data.get("docker_stats", {})
                .get("containers", {})
                .get(self.container_name, {})
            )

            if not isinstance(container, dict):
                return {}

            attrs = {
                "state": container.get("state", "unknown"),
                "status": container.get("status", "unknown"),
                "health": container.get("health", "unknown"),
                "image": container.get("image", "unknown"),
                "version": container.get("version", "latest"),
            }

            # Add metrics for running containers
            if container.get("state") == "running":
                metrics = {
                    "cpu_percentage": self._validate_percentage(
                        container.get("cpu_percentage")
                    ),
                    "cpu_cores_percentage": self._validate_percentage(
                        container.get("cpu_1core_percentage")
                    ),
                    "memory_usage": (
                        f"{container.get('memory_usage', 0):.1f} MB"
                        if "memory_usage" in container else None
                    ),
                    "memory_percentage": self._validate_percentage(
                        container.get("memory_percentage")
                    ),
                    "network_speed_up": (
                        f"{container.get('network_speed_up', 0):.1f} KB/s"
                        if "network_speed_up" in container else None
                    ),
                    "network_speed_down": (
                        f"{container.get('network_speed_down', 0):.1f} KB/s"
                        if "network_speed_down" in container else None
                    ),
                    "network_total_up": (
                        f"{container.get('network_total_up', 0):.1f} MB"
                        if "network_total_up" in container else None
                    ),
                    "network_total_down": (
                        f"{container.get('network_total_down', 0):.1f} MB"
                        if "network_total_down" in container else None
                    ),
                }

                # Only add metrics that have values
                attrs.update({
                    k: v for k, v in metrics.items()
                    if v is not None
                })

                # Add timestamps if available
                if uptime := container.get("uptime"):
                    attrs["uptime"] = uptime
                if created := container.get("created"):
                    attrs["created"] = created

            return attrs

        except (AttributeError, KeyError, TypeError) as err:
            _LOGGER.debug(
                "Error getting attributes for container %s: %s",
                self.container_name,
                err
            )
            return {}

    @property
    def icon(self) -> str:
        """Return dynamic icon based on container state."""
        try:
            container = (
                self.coordinator.data.get("docker_stats", {})
                .get("containers", {})
                .get(self.container_name, {})
            )

            state = container.get("state", "unknown").lower()
            return {
                "running": "mdi:docker",
                "paused": "mdi:pause-circle",
                "exited": "mdi:docker-off",
                "dead": "mdi:alert-circle",
                "restarting": "mdi:restart",
            }.get(state, "mdi:docker-off")

        except (KeyError, TypeError, AttributeError):
            return "mdi:docker-off"

class UnraidDockerSummaryMixin(UnraidDiagnosticMixin):
    """Mixin for Docker summary sensors."""

    def get_summary_entities(
        self,
        coordinator,
        metrics: list[tuple[str, str, Callable[[dict], Any]]]
    ) -> list[UnraidDockerSensor]:
        """Create summary sensor entities."""
        entities = []

        for key, name, value_fn in metrics:
            description = UnraidSensorEntityDescription(
                key=f"docker_{key}",
                name=f"Docker {name}",
                icon="mdi:docker",
                device_class=(
                    SensorDeviceClass.POWER_FACTOR
                    if "percentage" in key
                    else None
                ),
                state_class=(
                    SensorStateClass.MEASUREMENT
                    if "percentage" in key
                    else None
                ),
                native_unit_of_measurement=(
                    PERCENTAGE if "percentage" in key else None
                ),
                value_fn=value_fn,
            )
            entities.append(UnraidDockerSensor(coordinator, description))

        return entities

class UnraidDockerSensors(UnraidDockerSummaryMixin):
    """Helper class to create all Docker sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize Docker sensors."""
        super().__init__()
        self.entities = []

        # Add summary sensors from DOCKER_SENSOR_TYPES
        for description in DOCKER_SENSOR_TYPES:
            self.entities.append(UnraidDockerSensor(coordinator, description))

        # Add container sensors if Docker insights is enabled
        if coordinator.docker_insights:
            docker_stats = coordinator.data.get("docker_stats", {})
            containers = docker_stats.get("containers", {})

            for container_name in containers:
                self.entities.append(
                    UnraidDockerContainerSensor(
                        coordinator=coordinator,
                        container_name=container_name
                    )
                )