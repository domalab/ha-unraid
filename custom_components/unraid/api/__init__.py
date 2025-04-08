"""Unraid API package."""
from .disk_operations import DiskOperationsMixin
from .docker_operations import DockerOperationsMixin
from .vm_operations import VMOperationsMixin
from .system_operations import SystemOperationsMixin
from .network_operations import NetworkOperationsMixin, NetworkRateSmoothingMixin
from .ups_operations import UPSOperationsMixin
from .userscript_operations import UserScriptOperationsMixin
from .smart_operations import SmartDataManager
from .disk_state import DiskStateManager, DiskState
from .disk_utils import is_valid_disk_name
from .disk_mapping import get_unraid_disk_mapping, get_disk_info
from .connection_manager import ConnectionManager, SSHConnection, ConnectionState, ConnectionMetrics

__all__ = [
    "DiskOperationsMixin",
    "DockerOperationsMixin",
    "VMOperationsMixin",
    "SystemOperationsMixin",
    "NetworkOperationsMixin",
    "NetworkRateSmoothingMixin",
    "UPSOperationsMixin",
    "UserScriptOperationsMixin",
    "SmartDataManager",
    "DiskStateManager",
    "DiskState",
    "is_valid_disk_name",
    "get_unraid_disk_mapping",
    "get_disk_info",
    "ConnectionManager",
    "SSHConnection",
    "ConnectionState",
    "ConnectionMetrics",
]
