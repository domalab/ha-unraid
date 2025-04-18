"""Tests for the DiskOperationsMixin class."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.unraid.api.disk_operations import DiskOperationsMixin
from custom_components.unraid.api.network_operations import NetworkOperationsMixin


@pytest.fixture
def mock_disk_operations():
    """Return a mocked DiskOperationsMixin instance."""
    disk_ops = DiskOperationsMixin()
    network_ops = MagicMock(spec=NetworkOperationsMixin)
    network_ops.run_command = AsyncMock()
    disk_ops._network_ops = network_ops
    return disk_ops


@pytest.mark.asyncio
async def test_get_disks_status(mock_disk_operations):
    """Test the get_disks_status method."""
    # Arrange
    mock_network_ops = mock_disk_operations._network_ops
    
    # Sample disk data from 'ls -la /dev/disk/by-id/' command
    disk_by_id_response = """
total 0
drwxr-xr-x 2 root root 240 Jan 1 12:00 .
drwxr-xr-x 6 root root 120 Jan 1 12:00 ..
lrwxrwxrwx 1 root root   9 Jan 1 12:00 ata-WDC_WD100EMAZ-00WJTA0_1234 -> ../../sda
lrwxrwxrwx 1 root root  10 Jan 1 12:00 ata-WDC_WD100EMAZ-00WJTA0_1234-part1 -> ../../sda1
lrwxrwxrwx 1 root root   9 Jan 1 12:00 ata-WDC_WD80EMAZ-00WJTA0_5678 -> ../../sdb
"""
    
    # Sample disk temperature data
    disk_temps_response = """
/dev/sda: 35 C
/dev/sdb: 36 C
"""
    
    # Sample df command output
    df_output = """
Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1     10485760   5242880   5242880  50% /mnt/disk1
/dev/sdb1      8388608   4194304   4194304  50% /mnt/disk2
"""

    # Sample disk space output from 'df -h' command
    disk_space_response = """
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        10G  5.0G  5.0G  50% /mnt/disk1
/dev/sdb1       8.0G  4.0G  4.0G  50% /mnt/disk2
"""
    
    # Sample lsblk data
    lsblk_response = """
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINT
sda      8:0    0   10G  0 disk 
└─sda1   8:1    0   10G  0 part /mnt/disk1
sdb      8:16   0    8G  0 disk 
└─sdb1   8:17   0    8G  0 part /mnt/disk2
"""
    
    # Setup mock responses
    mock_network_ops.run_command.side_effect = [
        disk_by_id_response,     # ls -la /dev/disk/by-id/
        disk_temps_response,     # smartctl commands
        df_output,               # df command
        disk_space_response,     # df -h command
        lsblk_response,          # lsblk command
    ]
    
    # Act
    result = await mock_disk_operations.get_disks_status()
    
    # Assert
    assert mock_network_ops.run_command.call_count >= 1
    assert len(result) > 0
    # Check that we have disk info for sda and sdb
    assert any(disk for disk in result if disk.get("device") == "sda")
    assert any(disk for disk in result if disk.get("device") == "sdb")


@pytest.mark.asyncio
async def test_get_smart_status(mock_disk_operations):
    """Test the get_smart_status method."""
    # Arrange
    mock_network_ops = mock_disk_operations._network_ops
    
    # Sample SMART data response
    smart_response = """
smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.15.0] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

SMART Attributes Data Structure revision number: 16
Vendor Specific SMART Attributes with Thresholds:
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  1 Raw_Read_Error_Rate     0x002f   100   100   051    Pre-fail  Always       -       0
  2 Throughput_Performance  0x0026   100   100   000    Old_age   Always       -       0
  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       0
  7 Seek_Error_Rate         0x002e   100   100   051    Old_age   Always       -       0
  9 Power_On_Hours          0x0032   100   100   000    Old_age   Always       -       5473
 10 Spin_Retry_Count        0x0032   100   100   051    Old_age   Always       -       0
"""
    
    mock_network_ops.run_command.return_value = smart_response
    
    # Act
    result = await mock_disk_operations.get_smart_status("/dev/sda")
    
    # Assert
    mock_network_ops.run_command.assert_called_once()
    assert result is not None
    assert "attributes" in result
    assert len(result["attributes"]) > 0
    assert result["attributes"][0]["id"] == 1
    assert result["attributes"][0]["name"] == "Raw_Read_Error_Rate"
    assert result["attributes"][0]["value"] == 100
