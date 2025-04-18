"""Sensor priority management for Unraid integration."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

class SensorPriority(Enum):
    """Priority levels for sensors determining update frequency."""
    CRITICAL = 1  # System state, connection status, array status
    HIGH = 2      # CPU, memory, network activity (frequently changing)
    MEDIUM = 3    # Disk activity, VM status (moderately changing)
    LOW = 4       # Stable metrics, disk data with rare changes

class SensorCategory(Enum):
    """Categories of sensors for grouping in the prioritization system."""
    SYSTEM = "system"         # System-wide metrics (CPU, memory, etc.)
    ARRAY = "array"           # Array status and configuration
    DISK = "disk"             # Individual disk metrics
    NETWORK = "network"       # Network interface metrics
    DOCKER = "docker"         # Docker container metrics
    VM = "vm"                 # Virtual machine metrics
    UPS = "ups"               # UPS metrics
    OTHER = "other"           # Misc metrics


class SensorMetrics:
    """Metrics to track sensor volatility and importance."""

    def __init__(self, sensor_id: str) -> None:
        """Initialize sensor metrics."""
        self.sensor_id = sensor_id
        self.last_updated = datetime.now()
        self.last_changed = datetime.now()
        self.update_count = 0
        self.change_count = 0
        self.last_values: List[Any] = []
        self.max_values_history = 5

    def record_update(self, value: Any, changed: bool) -> None:
        """Record a sensor update."""
        now = datetime.now()
        self.update_count += 1
        self.last_updated = now

        # Store value history
        if len(self.last_values) >= self.max_values_history:
            self.last_values.pop(0)
        self.last_values.append(value)

        if changed:
            self.change_count += 1
            self.last_changed = now

    @property
    def change_frequency(self) -> float:
        """Calculate how frequently the value changes (0.0-1.0)."""
        if self.update_count == 0:
            return 0.0
        return self.change_count / self.update_count

    @property
    def time_since_last_change(self) -> float:
        """Get seconds since the last value change."""
        return (datetime.now() - self.last_changed).total_seconds()

    @property
    def volatility_score(self) -> float:
        """Calculate volatility score based on change history."""
        # Higher means more volatile (0.0-1.0)
        if self.update_count < 3:
            return 0.5  # Default mid-range until we have data

        # Factors: change frequency, time since last change
        time_factor = min(1.0, 3600 / max(1, self.time_since_last_change))
        return 0.7 * self.change_frequency + 0.3 * time_factor


class SensorPriorityManager:
    """Manages sensor priorities and update scheduling."""

    def __init__(self) -> None:
        """Initialize the sensor priority manager."""
        self._sensor_metrics: Dict[str, SensorMetrics] = {}
        self._sensor_priorities: Dict[str, SensorPriority] = {}
        self._sensor_categories: Dict[str, SensorCategory] = {}
        self._default_priorities: Dict[SensorCategory, SensorPriority] = {
            SensorCategory.SYSTEM: SensorPriority.HIGH,
            SensorCategory.ARRAY: SensorPriority.CRITICAL,
            SensorCategory.DISK: SensorPriority.MEDIUM,
            SensorCategory.NETWORK: SensorPriority.HIGH,
            SensorCategory.DOCKER: SensorPriority.MEDIUM,
            SensorCategory.VM: SensorPriority.MEDIUM,
            SensorCategory.UPS: SensorPriority.HIGH,
            SensorCategory.OTHER: SensorPriority.MEDIUM
        }

        # Pre-define critical sensors that always update at full frequency
        self._critical_sensors = {
            "array_status", "array_protection", "system_state",
            "connection_status", "parity_status"
        }

        # Update intervals based on priority (in seconds)
        self._update_intervals = {
            SensorPriority.CRITICAL: 60,     # Always update with core interval
            SensorPriority.HIGH: 120,        # 2 minutes
            SensorPriority.MEDIUM: 300,      # 5 minutes
            SensorPriority.LOW: 900          # 15 minutes
        }

        # Last update timestamps by sensor
        self._last_updates: Dict[str, datetime] = {}

        # Initialize categorization patterns
        self._category_patterns = self._initialize_category_patterns()

        _LOGGER.debug("SensorPriorityManager initialized")

    def _initialize_category_patterns(self) -> Dict[SensorCategory, List[str]]:
        """Initialize patterns for automatic sensor categorization."""
        return {
            SensorCategory.SYSTEM: [
                "cpu", "memory", "load", "uptime", "system", "version"
            ],
            SensorCategory.ARRAY: [
                "array", "parity", "protection", "cache", "recon"
            ],
            SensorCategory.DISK: [
                "disk", "smart", "temperature", "usage", "size", "free"
            ],
            SensorCategory.NETWORK: [
                "network", "interface", "throughput", "rx_", "tx_", "speed", "eth", "bandwidth"
            ],
            SensorCategory.DOCKER: [
                "docker", "container"
            ],
            SensorCategory.VM: [
                "vm", "virtual", "machine", "libvirt"
            ],
            SensorCategory.UPS: [
                "ups", "battery", "runtime", "apc"
            ]
        }

    def register_sensor(
        self,
        sensor_id: str,
        category: Optional[SensorCategory] = None,
        priority: Optional[SensorPriority] = None
    ) -> None:
        """Register a sensor with the priority manager."""
        # Create metrics if not existing
        if sensor_id not in self._sensor_metrics:
            self._sensor_metrics[sensor_id] = SensorMetrics(sensor_id)

        # Determine category if not provided
        if category is None:
            category = self._categorize_sensor(sensor_id)
        self._sensor_categories[sensor_id] = category

        # Set priority (explicit, from category default, or MEDIUM)
        if priority is not None:
            self._sensor_priorities[sensor_id] = priority
        elif sensor_id in self._critical_sensors:
            self._sensor_priorities[sensor_id] = SensorPriority.CRITICAL
        else:
            self._sensor_priorities[sensor_id] = self._default_priorities.get(
                category, SensorPriority.MEDIUM
            )

        _LOGGER.debug(
            "Registered sensor %s: category=%s, priority=%s",
            sensor_id,
            category.name if category else "UNKNOWN",
            self._sensor_priorities[sensor_id].name
        )

    def _categorize_sensor(self, sensor_id: str) -> SensorCategory:
        """Auto-categorize a sensor based on its ID."""
        sensor_id_lower = sensor_id.lower()

        # Check against patterns
        for category, patterns in self._category_patterns.items():
            for pattern in patterns:
                if pattern in sensor_id_lower:
                    return category

        # Default category
        return SensorCategory.OTHER

    def record_update(self, sensor_id: str, value: Any) -> None:
        """Record a sensor update with new value."""
        # Register if not already registered
        if sensor_id not in self._sensor_metrics:
            self.register_sensor(sensor_id)

        # Check if value has changed
        has_changed = True
        metrics = self._sensor_metrics[sensor_id]
        if metrics.last_values and metrics.last_values[-1] == value:
            has_changed = False

        # Record the update
        metrics.record_update(value, has_changed)

        # Update last update timestamp
        self._last_updates[sensor_id] = datetime.now()

        # Periodically adjust priority based on volatility
        if metrics.update_count > 0 and metrics.update_count % 10 == 0:
            self._adjust_priority(sensor_id)

    def _adjust_priority(self, sensor_id: str) -> None:
        """Dynamically adjust sensor priority based on volatility."""
        # Skip critical sensors - they're always critical
        if sensor_id in self._critical_sensors:
            return

        metrics = self._sensor_metrics[sensor_id]
        current_priority = self._sensor_priorities[sensor_id]

        # Need enough data to make a decision
        if metrics.update_count < 5:
            return

        volatility = metrics.volatility_score

        # Determine ideal priority based on volatility
        if volatility > 0.7:
            ideal_priority = SensorPriority.HIGH
        elif volatility > 0.3:
            ideal_priority = SensorPriority.MEDIUM
        else:
            ideal_priority = SensorPriority.LOW

        # Only change if it's different
        if ideal_priority != current_priority:
            _LOGGER.debug(
                "Adjusting sensor %s priority: %s -> %s (volatility=%.2f)",
                sensor_id,
                current_priority.name,
                ideal_priority.name,
                volatility
            )
            self._sensor_priorities[sensor_id] = ideal_priority

    def should_update(self, sensor_id: str, current_time: Optional[datetime] = None) -> bool:
        """Determine if a sensor should be updated based on its priority."""
        # Register if not already registered
        if sensor_id not in self._sensor_metrics:
            self.register_sensor(sensor_id)
            return True  # Always update on first registration

        # Critical sensors always update
        if sensor_id in self._critical_sensors:
            return True

        if current_time is None:
            current_time = datetime.now()

        # Get last update time and priority
        last_update = self._last_updates.get(sensor_id, datetime.min)
        priority = self._sensor_priorities.get(sensor_id, SensorPriority.MEDIUM)

        # Calculate time since last update
        time_since_update = (current_time - last_update).total_seconds()

        # Check if enough time has passed based on priority
        return time_since_update >= self._update_intervals[priority]

    def get_update_due_sensors(self, all_sensors: List[str]) -> List[str]:
        """Get a list of sensors that are due for an update."""
        current_time = datetime.now()
        return [
            sensor_id for sensor_id in all_sensors
            if self.should_update(sensor_id, current_time)
        ]

    def get_sensors_by_priority(self) -> Dict[SensorPriority, List[str]]:
        """Get sensors grouped by priority."""
        result = {priority: [] for priority in SensorPriority}

        for sensor_id, priority in self._sensor_priorities.items():
            result[priority].append(sensor_id)

        return result

    def get_sensor_stats(self) -> Dict[str, Any]:
        """Get statistics about sensor priorities and updates."""
        priority_counts = {priority.name: 0 for priority in SensorPriority}
        category_counts = {category.name: 0 for category in SensorCategory}

        # Count by priority and category
        for sensor_id, priority in self._sensor_priorities.items():
            priority_counts[priority.name] += 1

            category = self._sensor_categories.get(sensor_id)
            if category:
                category_counts[category.name] += 1

        # Get volatility metrics
        high_volatility_count = sum(
            1 for m in self._sensor_metrics.values()
            if m.volatility_score > 0.7
        )

        return {
            "total_sensors": len(self._sensor_metrics),
            "by_priority": priority_counts,
            "by_category": category_counts,
            "high_volatility_count": high_volatility_count,
            "update_intervals": {
                p.name: self._update_intervals[p] for p in SensorPriority
            }
        }

    def set_update_interval(self, priority: SensorPriority, interval_seconds: int) -> None:
        """Set the update interval for a priority level."""
        # Validate interval (minimum 60 seconds)
        interval_seconds = max(60, interval_seconds)

        _LOGGER.debug(
            "Setting update interval for %s priority to %d seconds",
            priority.name,
            interval_seconds
        )

        self._update_intervals[priority] = interval_seconds
