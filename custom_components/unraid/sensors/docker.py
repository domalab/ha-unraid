"""Docker-related sensors for Unraid."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, field

from homeassistant.components.sensor import ( # type: ignore
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory # type: ignore

from .base import UnraidSensorBase, UnraidDiagnosticMixin
from .const import DOMAIN
from ..entity_naming import EntityNaming

# _LOGGER = logging.getLogger(__name__)

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""
    value_fn: Callable[[dict[str, Any]], Any] = field(default=lambda _: None)
    available_fn: Callable[[dict[str, Any]], bool] = field(default=lambda _: True)

# Simplified sensor types - only basic container stats
DOCKER_SENSOR_TYPES = (
    UnraidSensorEntityDescription(
        key="containers_running",
        name="Running Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: len([c for c in data.get("docker_containers", []) if c.get("state") == "running"])
    ),
    UnraidSensorEntityDescription(
        key="containers_paused",
        name="Paused Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: len([c for c in data.get("docker_containers", []) if c.get("state") == "paused"])
    ),
    UnraidSensorEntityDescription(
        key="total_containers",
        name="Total Containers",
        icon="mdi:docker",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: len(data.get("docker_containers", []))
    ),
)

class UnraidDockerSensor(UnraidSensorBase, UnraidDiagnosticMixin):
    """Docker summary statistics sensor."""

    def __init__(self, coordinator, description: UnraidSensorEntityDescription) -> None:
        """Initialize the sensor."""
        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )

        super().__init__(coordinator, description)
        UnraidDiagnosticMixin.__init__(self)
        self._attr_has_entity_name = True

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
            and "docker_containers" in self.coordinator.data
        )

class UnraidDockerContainerSensor(UnraidSensorBase, UnraidDiagnosticMixin):
    """Docker container state sensor."""

    def __init__(self, coordinator, container_name: str) -> None:
        """Initialize the sensor."""
        self.container_name = container_name

        naming = EntityNaming(
            domain=DOMAIN,
            hostname=coordinator.hostname,
            component="docker"
        )

        description = UnraidSensorEntityDescription(
            key=f"docker_{container_name.lower()}",
            name=naming.get_entity_name(container_name, "docker"),
            icon="mdi:docker",
            value_fn=self._get_container_state,
            available_fn=self._is_container_available,
        )

        super().__init__(coordinator, description)
        UnraidDiagnosticMixin.__init__(self)
        self._attr_has_entity_name = True

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_docker")},
            "name": f"Unraid Docker ({naming.clean_hostname()})",
            "manufacturer": "Docker",
            "model": "Container Engine",
            "via_device": (DOMAIN, coordinator.entry.entry_id),
        }

    def _get_container_state(self, data: dict) -> str:
        """Get container state."""
        for container in data.get("docker_containers", []):
            if container.get("name") == self.container_name:
                return container.get("state", "unknown")
        return "unknown"

    def _is_container_available(self, data: dict) -> bool:
        """Check if container is available."""
        containers = data.get("docker_containers", [])
        return any(c.get("name") == self.container_name for c in containers)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return basic container attributes."""
        for container in self.coordinator.data.get("docker_containers", []):
            if container.get("name") == self.container_name:
                return {
                    "state": container.get("state", "unknown"),
                    "status": container.get("status", "unknown"),
                    "image": container.get("image", "unknown"),
                }
        return {}

    @property
    def icon(self) -> str:
        """Return dynamic icon based on container state."""
        state = self._get_container_state(self.coordinator.data)
        return {
            "running": "mdi:docker",
            "paused": "mdi:pause-circle",
            "exited": "mdi:docker-off",
            "dead": "mdi:alert-circle",
            "restarting": "mdi:restart",
        }.get(state.lower(), "mdi:docker-off")

class UnraidDockerSensors:
    """Helper class to create all Docker sensors."""

    def __init__(self, coordinator) -> None:
        """Initialize Docker sensors."""
        self.entities = []

        # Add summary sensors
        for description in DOCKER_SENSOR_TYPES:
            self.entities.append(UnraidDockerSensor(coordinator, description))

        # Add basic container state sensors
        for container in coordinator.data.get("docker_containers", []):
            if container_name := container.get("name"):
                self.entities.append(
                    UnraidDockerContainerSensor(
                        coordinator=coordinator,
                        container_name=container_name
                    )
                )

# Compatibility classes for tests
from .test_base import UnraidTestSensor

class UnraidDockerContainerCountSensor(UnraidTestSensor):
    """Sensor for Unraid Docker container count - compatibility for tests."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"unraid_docker_container_count"
        self._attr_name = "Docker Containers"
        self._attr_icon = "mdi:docker"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[int]:
        """Return the number of Docker containers."""
        if not self.coordinator.data or "docker_info" not in self.coordinator.data:
            return None

        docker_info = self.coordinator.data.get("docker_info", {})
        return docker_info.get("container_count", None)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes about Docker containers."""
        attrs = {}

        if not self.coordinator.data or "docker_info" not in self.coordinator.data:
            return attrs

        docker_info = self.coordinator.data.get("docker_info", {})
        containers = docker_info.get("docker_containers", [])

        # Count running and stopped containers
        running_count = 0
        stopped_count = 0

        for container in containers:
            state = container.get("state", "").lower()
            if state == "running":
                running_count += 1
            elif state in ["exited", "stopped"]:
                stopped_count += 1

        attrs["running_containers"] = running_count
        attrs["stopped_containers"] = stopped_count

        return attrs


class UnraidDockerStatusSensor(UnraidTestSensor):
    """Sensor for Unraid Docker service status - compatibility for tests."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"unraid_docker_status"
        self._attr_name = "Docker Status"
        self._attr_icon = "mdi:docker"

    @property
    def native_value(self) -> str:
        """Return the Docker service status."""
        if not self.coordinator.data or "docker_info" not in self.coordinator.data:
            return "not_detected"

        docker_info = self.coordinator.data.get("docker_info", {})
        if not docker_info:
            return "not_detected"

        docker_running = docker_info.get("docker_running", False)

        if docker_running:
            return "running"
        else:
            return "stopped"
