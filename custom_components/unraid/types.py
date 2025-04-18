"""Type definitions for Unraid integration."""
from __future__ import annotations

from typing import Dict, List, Any, Optional, TypedDict, Literal


class SystemStatsDict(TypedDict, total=False):
    """Type for system stats data."""
    cpu_usage: float
    memory_usage: Dict[str, Any]
    uptime: int
    temperature_data: Dict[str, Any]
    array_usage: Dict[str, Any]
    cache_usage: Dict[str, Any]
    individual_disks: List[Dict[str, Any]]
    network_stats: Dict[str, Dict[str, Any]]
    ups_info: Dict[str, Any]
    load_average: List[float]
    cpu_model: str
    cpu_cores: int
    cpu_frequency: float


class DiskInfoDict(TypedDict, total=False):
    """Type for disk information."""
    name: str
    mount_point: str
    total: int
    used: int
    free: int
    percentage: float
    state: str
    smart_status: str
    temperature: Optional[int]
    device: str
    filesystem: str


class NetworkStatsDict(TypedDict, total=False):
    """Type for network statistics."""
    rx_bytes: int
    tx_bytes: int
    rx_rate: float
    tx_rate: float
    connected: bool
    speed: str
    duplex: str


class DockerContainerDict(TypedDict, total=False):
    """Type for Docker container information."""
    id: str
    name: str
    state: str
    status: str
    image: str
    autostart: bool


class VMDict(TypedDict, total=False):
    """Type for VM information."""
    name: str
    state: str
    cpus: int
    memory: int
    autostart: bool


class UserScriptDict(TypedDict, total=False):
    """Type for user script information."""
    id: str
    name: str
    description: str


class UPSInfoDict(TypedDict, total=False):
    """Type for UPS information."""
    STATUS: str
    BCHARGE: str
    LOADPCT: str
    TIMELEFT: str
    NOMPOWER: str
    BATTV: str
    LINEV: str
    MODEL: str
    FIRMWARE: str
    SERIALNO: str


class ParityInfoDict(TypedDict, total=False):
    """Type for parity information."""
    status: str
    progress: int
    speed: str
    errors: int
    last_check: str
    next_check: str
    duration: str
    last_status: str
    last_speed: str


class UnraidDataDict(TypedDict, total=False):
    """Type for Unraid data."""
    system_stats: SystemStatsDict
    docker_containers: List[DockerContainerDict]
    vms: List[VMDict]
    user_scripts: List[UserScriptDict]
    parity_info: ParityInfoDict
    smart_data: Dict[str, Dict[str, Any]]
    disk_mappings: Dict[str, Any]


# Connection types
ConnectionStateType = Literal["connected", "connecting", "disconnected", "error"]


# Service action types
ServiceActionType = Literal["start", "stop", "restart", "pause", "unpause"]


# Entity state types
EntityStateType = Literal["on", "off", "unavailable", "unknown"]
