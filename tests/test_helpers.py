# tests/test_helpers.py
"""Tests for the Unraid helper functions."""

import pytest

from custom_components.unraid.utils import (
    get_network_speed_unit,
    format_bytes,
    parse_temperature,
    is_valid_temp_range,
)
from custom_components.unraid.helpers import (
    get_cpu_info,
    get_memory_info,
    get_disk_number,
)

# Tests for get_network_speed_unit
@pytest.mark.parametrize(
    "bytes_per_sec, expected_value, expected_unit",
    [
        (0, 0.0, "bit/s"),
        (1, 8.0, "bit/s"),          # 1 byte/s = 8 bit/s
        (125, 1.0, "kbit/s"),       # 1000 bit/s = 1 kbit/s
        (1250, 10.0, "kbit/s"),
        (125000, 1.0, "Mbit/s"),    # 1,000,000 bit/s = 1 Mbit/s
        (1250000, 10.0, "Mbit/s"),
        (125000000, 1.0, "Gbit/s"), # 1,000,000,000 bit/s = 1 Gbit/s
        (15625000, 125.0, "Mbit/s"), # Example value
        (1.25, 10.0, "bit/s"),       # Fractional bytes
    ]
)
def test_get_network_speed_unit(bytes_per_sec, expected_value, expected_unit):
    """Test the get_network_speed_unit function with various inputs."""
    value, unit = get_network_speed_unit(bytes_per_sec)
    assert value == expected_value
    assert unit == expected_unit

def test_get_network_speed_unit_negative():
    """Test get_network_speed_unit with negative input."""
    value, unit = get_network_speed_unit(-100)
    assert value == 0.0
    assert unit == "bit/s"

# Tests for format_bytes
@pytest.mark.parametrize(
    "bytes_value, expected_output",
    [
        (0, "0 B"),
        (1, "1.00 B"),
        (1023, "1023.00 B"),
        (1024, "1.00 KB"),
        (1536, "1.50 KB"),
        (1024 * 1024, "1.00 MB"),
        (1024 * 1024 * 1.5, "1.50 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
        (1024 * 1024 * 1024 * 2000, "2000.00 GB"), # Test large GB
        (1024 ** 4, "1.00 TB"),
        (1024 ** 5, "1.00 PB"),
        (1024 ** 6, "1024.00 PB"), # Max unit is PB
    ]
)
def test_format_bytes(bytes_value, expected_output):
    """Test the format_bytes function with various inputs."""
    assert format_bytes(bytes_value) == expected_output

def test_format_bytes_negative():
    """Test format_bytes with negative input."""
    assert format_bytes(-1024) == "0 B"

# Tests for get_cpu_info
def test_get_cpu_info_full_data():
    """Test get_cpu_info with complete data."""
    stats = {
        "cpu_usage": 75.5,
        "cpu_cores": 8,
        "cpu_model": "Intel Core i7",
        "cpu_frequency": 3.2
    }
    expected = {
        "usage": 75.5,
        "cores": 8,
        "model": "Intel Core i7",
        "frequency": 3.2
    }
    assert get_cpu_info(stats) == expected

def test_get_cpu_info_partial_data():
    """Test get_cpu_info with missing data."""
    stats = {
        "cpu_usage": 50.0,
        "cpu_cores": 4
    }
    expected = {
        "usage": 50.0,
        "cores": 4,
        "model": "Unknown",
        "frequency": 0.0
    }
    assert get_cpu_info(stats) == expected

def test_get_cpu_info_empty_data():
    """Test get_cpu_info with empty input."""
    stats = {}
    expected = {
        "usage": 0.0,
        "cores": 0,
        "model": "Unknown",
        "frequency": 0.0
    }
    assert get_cpu_info(stats) == expected

# Tests for get_memory_info
def test_get_memory_info_full_data():
    """Test get_memory_info with complete data."""
    stats = {
        "memory_usage": {
            "total": 16 * 1024 * 1024, # 16 GB in KB
            "used": 8 * 1024 * 1024,
            "free": 8 * 1024 * 1024,
            "percentage": 50.0
        }
    }
    expected = {
        "total": 16777216,
        "used": 8388608,
        "free": 8388608,
        "percentage": 50.0
    }
    assert get_memory_info(stats) == expected

def test_get_memory_info_partial_data():
    """Test get_memory_info with missing memory_usage sub-keys."""
    stats = {
        "memory_usage": {
            "total": 16 * 1024 * 1024,
            "used": 4 * 1024 * 1024
        }
    }
    expected = {
        "total": 16777216,
        "used": 4194304,
        "free": 0, # Defaults to 0 if missing
        "percentage": 0.0 # Defaults to 0.0 if missing
    }
    assert get_memory_info(stats) == expected

def test_get_memory_info_missing_memory_usage():
    """Test get_memory_info when memory_usage key is missing."""
    stats = {}
    expected = {
        "total": 0,
        "used": 0,
        "free": 0,
        "percentage": 0.0
    }
    assert get_memory_info(stats) == expected

def test_get_memory_info_empty_memory_usage():
    """Test get_memory_info with an empty memory_usage dictionary."""
    stats = {"memory_usage": {}}
    expected = {
        "total": 0,
        "used": 0,
        "free": 0,
        "percentage": 0.0
    }
    assert get_memory_info(stats) == expected

# Tests for get_disk_number
@pytest.mark.parametrize(
    "disk_name, expected_number",
    [
        ("disk1", 1),
        ("disk10", 10),
        ("disk99", 99),
        ("Disk5", None), # Incorrect case
        ("disk", None), # No number
        ("mydisk1", None), # Doesn't start with disk
        ("cache", None), # Not an array disk
        ("parity", None), # Not an array disk
        ("", None), # Empty string
        (None, None), # None input
    ]
)
def test_get_disk_number(disk_name, expected_number):
    """Test the get_disk_number function."""
    assert get_disk_number(disk_name) == expected_number

# Tests for parse_temperature
@pytest.mark.parametrize(
    "value, expected_temp",
    [
        ("35.5 °C", 35.5),
        ("+42 C", 42.0),
        (" -10.0 ", -10.0),
        ("55", 55.0),
        ("invalid", None),
        ("", None),
        (None, None),
        ("160", None), # Outside valid range [-50, 150]
        ("-60", None), # Outside valid range [-50, 150]
        ("35.5C", 35.5),
        ("abc 40 def", None),
    ]
)
def test_parse_temperature(value, expected_temp):
    """Test the parse_temperature function."""
    assert parse_temperature(value) == expected_temp

# Tests for is_valid_temp_range
@pytest.mark.parametrize(
    "temp, is_cpu, expected_valid",
    [
        # CPU Temps (Range: -10 to 120 based on consts, assuming defaults)
        (50.0, True, True),
        (0.0, True, True),
        (110.0, True, True), # Assuming VALID_CPU_TEMP_RANGE allows up to 120
        (-5.0, True, True), # Assuming VALID_CPU_TEMP_RANGE allows down to -10
        (125.0, True, False), # Above typical CPU max
        (-20.0, True, False), # Below typical CPU min
        # MB Temps (Range: -10 to 100 based on consts, assuming defaults)
        (40.0, False, True),
        (0.0, False, True),
        (95.0, False, True), # Assuming VALID_MB_TEMP_RANGE allows up to 100
        (-5.0, False, True), # Assuming VALID_MB_TEMP_RANGE allows down to -10
        (105.0, False, False), # Above typical MB max
        (-15.0, False, False), # Below typical MB min
        # Edge cases
        (None, True, False),
        ("abc", False, False),
    ]
)
def test_is_valid_temp_range(temp, is_cpu, expected_valid):
    """Test the is_valid_temp_range function."""
    # Note: This test assumes default ranges. Actual ranges are defined in helpers.py
    # We might need to mock VALID_CPU_TEMP_RANGE and VALID_MB_TEMP_RANGE for precise testing
    # For now, we test based on reasonable assumptions.
    assert is_valid_temp_range(temp, is_cpu) == expected_valid

# Tests for is_solid_state_drive
def test_is_solid_state_drive():
    """Test is_solid_state_drive function for detecting SSDs and NVMes."""
    from custom_components.unraid.helpers import is_solid_state_drive

    # Test with NVMe device
    nvme_disk = {
        "name": "nvme0n1",
        "device": "nvme0n1",
        "smart_data": {}
    }
    assert is_solid_state_drive(nvme_disk) is True

    # Test with cache device
    cache_disk = {
        "name": "cache",
        "device": "sda",
        "smart_data": {}
    }
    assert is_solid_state_drive(cache_disk) is True

    # Test with SSD rotation rate (0)
    ssd_disk = {
        "name": "disk1",
        "device": "sdb",
        "smart_data": {
            "rotation_rate": 0
        }
    }
    assert is_solid_state_drive(ssd_disk) is True

    # Test with HDD rotation rate (7200)
    hdd_disk = {
        "name": "disk2",
        "device": "sdc",
        "smart_data": {
            "rotation_rate": 7200
        }
    }
    assert is_solid_state_drive(hdd_disk) is False

    # Test with missing smart_data
    no_smart_disk = {
        "name": "disk3",
        "device": "sdd"
    }
    assert is_solid_state_drive(no_smart_disk) is False

    # Test with None input
    assert is_solid_state_drive(None) is False

    # Test with empty dict
    assert is_solid_state_drive({}) is False
