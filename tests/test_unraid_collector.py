"""Unit tests for the UnraidCollector class."""
import asyncio
import json
import os
from typing import Dict, Any
import pytest

from unraid_collector import UnraidCollector

# Path to sample data file for testing
SAMPLE_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "unraid_data_192.168.20.21_20250412_232528.json")


class MockConnection:
    """Mock connection for testing UnraidCollector without SSH connection."""

    def __init__(self, responses: Dict[str, str]):
        """Initialize with predefined responses to commands."""
        self.responses = responses
        self.closed = False

    async def run(self, command: str, timeout=None):
        """Mock run command."""
        # Create a mock result object with stdout
        class MockResult:
            def __init__(self, stdout, exit_status=0):
                self.stdout = stdout
                self.exit_status = exit_status
                self.stderr = ""

        # Return predefined response if available, otherwise return empty string
        return MockResult(self.responses.get(command, ""))

    def close(self):
        """Mock close."""
        self.closed = True

    async def wait_closed(self):
        """Mock wait closed."""
        self.closed = True


class TestUnraidCollector:
    """Test the UnraidCollector class."""

    @pytest.fixture
    def sample_data(self) -> Dict[str, Any]:
        """Load sample data from JSON file."""
        if not os.path.exists(SAMPLE_DATA_PATH):
            pytest.skip(f"Sample data file not found: {SAMPLE_DATA_PATH}")

        with open(SAMPLE_DATA_PATH, "r") as f:
            return json.load(f)

    @pytest.fixture
    def mock_collector(self, sample_data: Dict[str, Any]) -> UnraidCollector:
        """Create a collector with mocked connection and data."""
        collector = UnraidCollector("test-host", "test-user", "test-pass")
        collector.data = sample_data
        return collector

    def test_data_structure(self, sample_data: Dict[str, Any]):
        """Test that the collected data has the expected structure."""
        # Basic validation of required keys
        assert "collection_time" in sample_data
        assert "host" in sample_data
        assert "system_stats" in sample_data
        assert "disk_info" in sample_data
        assert "network_info" in sample_data
        assert "docker_info" in sample_data
        assert "vm_info" in sample_data
        assert "ups_info" in sample_data
        assert "parity_status" in sample_data
        assert "plugin_info" in sample_data
        assert "share_info" in sample_data
        assert "user_info" in sample_data
        assert "notifications" in sample_data
        assert "array_status" in sample_data

        # Test new data sections
        assert "emhttp_configs" in sample_data
        assert "gpu_info" in sample_data
        assert "zfs_info" in sample_data

    def test_system_stats(self, sample_data: Dict[str, Any]):
        """Test that system stats are collected and have expected keys."""
        system_stats = sample_data.get("system_stats", {})

        # Basic system stats validation
        assert "cpu_info_raw" in system_stats
        assert "cpu_cores" in system_stats
        assert "cpu_model" in system_stats
        assert "memory_info_raw" in system_stats
        assert "memory_usage" in system_stats
        assert "cpu_usage_raw" in system_stats
        assert "cpu_usage" in system_stats
        assert "uptime_raw" in system_stats

        # Memory usage validation
        memory_usage = system_stats.get("memory_usage", {})
        assert "total" in memory_usage
        assert "free" in memory_usage
        assert "used" in memory_usage
        assert "percentage" in memory_usage

        # Validate cpu_cores is an integer
        assert isinstance(system_stats.get("cpu_cores"), int)

        # Validate cpu_usage is a number
        assert isinstance(system_stats.get("cpu_usage"), (int, float))

    def test_disk_info(self, sample_data: Dict[str, Any]):
        """Test that disk info is collected and has expected keys."""
        disk_info = sample_data.get("disk_info", {})

        # Validate basic disk info - updated for new structure
        assert "disk_spin_status" in disk_info
        assert "smart_data" in disk_info

        # Validate smart_data is a dictionary
        smart_data = disk_info.get("smart_data", {})
        assert isinstance(smart_data, dict)

        # Check that we have at least some disks
        assert len(smart_data) > 0

        # Check structure of first disk data
        first_disk = next(iter(smart_data.values()))
        assert isinstance(first_disk, dict)
        assert "device" in first_disk or "model" in first_disk

    def test_network_info(self, sample_data: Dict[str, Any]):
        """Test that network info is collected and has expected keys."""
        network_info = sample_data.get("network_info", {})

        # Validate basic network info
        assert "interfaces" in network_info

        # Validate interfaces is a list in the sample data
        interfaces = network_info.get("interfaces", [])
        assert isinstance(interfaces, list)

        # Check that we have at least one interface
        assert len(interfaces) > 0

        # Check that the first interface is a string
        first_interface = interfaces[0]
        assert isinstance(first_interface, str)

        # Check for interface details
        assert "interface_details" in network_info or "interface_stats" in network_info

    def test_gpu_info(self, sample_data: Dict[str, Any]):
        """Test that GPU info is collected and has expected keys."""
        gpu_info = sample_data.get("gpu_info", {})

        # Validate basic GPU detection flags
        assert "has_nvidia" in gpu_info
        assert "has_amd" in gpu_info
        assert "has_intel" in gpu_info

        # Check for GPU drivers
        assert "gpu_drivers" in gpu_info

        # Validate type of has_* fields
        assert isinstance(gpu_info.get("has_nvidia"), bool)
        assert isinstance(gpu_info.get("has_amd"), bool)
        assert isinstance(gpu_info.get("has_intel"), bool)

        # Intel GPU-specific tests if Intel GPU is detected
        if gpu_info.get("has_intel", False):
            assert "i915_info" in gpu_info
            i915_info = gpu_info.get("i915_info", {})
            # Check for driver version
            assert "driver_version" in i915_info

    def test_zfs_info(self, sample_data: Dict[str, Any]):
        """Test that ZFS info is collected and has expected keys."""
        zfs_info = sample_data.get("zfs_info", {})

        # Validate basic ZFS info
        assert "zfs_available" in zfs_info

        # Validate type of zfs_available
        assert isinstance(zfs_info.get("zfs_available"), bool)

        # ZFS-specific tests if ZFS is available
        if zfs_info.get("zfs_available", False):
            assert "zfs_module" in zfs_info
            assert "zpool_status" in zfs_info
            assert "zpool_list" in zfs_info

    def test_emhttp_configs(self, sample_data: Dict[str, Any]):
        """Test that emhttp configs are collected and have expected keys."""
        emhttp_configs = sample_data.get("emhttp_configs", {})

        # Validate basic emhttp configs
        assert "emhttp_files_list" in emhttp_configs

        # Check for some common config files
        assert any(file_name in emhttp_configs for file_name in [
            "shares.ini",
            "network.ini",
            "users.ini"
        ])

    @pytest.mark.asyncio
    async def test_collect_gpu_info_mock(self):
        """Test the collect_gpu_info method with mock data."""
        # Mock responses
        mock_responses = {
            "which nvidia-smi >/dev/null 2>&1 && echo 'available' || echo 'not available'": "not available",
            "ls -la /sys/class/drm/*/device/vendor | grep 0x1002 >/dev/null 2>&1 && echo 'available' || echo 'not available'": "not available",
            "ls -la /sys/class/drm/*/device/vendor | grep 0x8086 >/dev/null 2>&1 && echo 'available' || echo 'not available'": "available",
            "cat /sys/module/i915/version 2>/dev/null || echo 'unknown'": "5.15.0-89-generic",
            "cat /sys/class/drm/card0/gt_cur_freq_mhz 2>/dev/null || echo 'unknown'": "300",
            "lsmod | grep -E 'nvidia|amdgpu|radeon|i915|nouveau' || echo 'No GPU drivers detected'": "i915 3436544 0\niosf_mbi 16384 2 i915,intel_rapl_common",
            "grep -i 'vfio\\|pci-stub\\|iommu' /proc/cmdline || echo 'No GPU passthrough'": "No GPU passthrough",
        }

        # Create collector with mock connection
        collector = UnraidCollector("test-host", "test-user", "test-pass")
        collector.conn = MockConnection(mock_responses)

        # Collect GPU info
        gpu_info = await collector.collect_gpu_info()

        # Validate GPU info
        assert gpu_info["has_nvidia"] is False
        assert gpu_info["has_amd"] is False
        assert gpu_info["has_intel"] is True
        assert "i915_info" in gpu_info
        assert "gpu_drivers" in gpu_info
        assert gpu_info["i915_info"]["driver_version"] == "5.15.0-89-generic"
        assert gpu_info["i915_info"]["current_freq_mhz"] == 300

    @pytest.mark.asyncio
    async def test_collect_zfs_info_mock(self):
        """Test the collect_zfs_info method with mock data."""
        # Mock responses for ZFS
        mock_responses = {
            "which zpool >/dev/null 2>&1 && echo 'available' || echo 'not available'": "available",
            "lsmod | grep zfs || echo 'ZFS module not loaded'": "zfs 5791744 1\nspl 126976 1 zfs",
            "zpool status 2>/dev/null || echo 'No ZFS pools'": "  pool: testpool\n state: ONLINE\nconfig:\n\n\tNAME        STATE     READ WRITE CKSUM\n\ttestpool    ONLINE       0     0     0\n\t  mirror-0  ONLINE       0     0     0\n\t    sda     ONLINE       0     0     0\n\t    sdb     ONLINE       0     0     0",
            "zpool list -H 2>/dev/null || echo 'No ZFS pools'": "testpool\t1000G\t500G\t500G\t-\t-\t-\t50%\t1.00x\tONLINE\t-",
        }

        # Create collector with mock connection
        collector = UnraidCollector("test-host", "test-user", "test-pass")
        collector.conn = MockConnection(mock_responses)

        # Collect ZFS info
        zfs_info = await collector.collect_zfs_info()

        # Validate ZFS info
        assert zfs_info["zfs_available"] is True
        assert "zfs_module" in zfs_info
        assert "zpool_status" in zfs_info
        assert "zpool_list" in zfs_info
        assert "testpool" in zfs_info["zpool_status"]