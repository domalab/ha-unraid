"""Unit tests for data parsing in the Unraid integration."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.unraid.api.ssh_client import UnraidSSHClient
from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
)


class TestDataParsing:
    """Test parsing of various data types from the Unraid system."""

    def test_parse_cpu_usage(self):
        """Test parsing of CPU usage information."""
        # Sample output from `cat /proc/stat`
        cpu_stat_output = """
        cpu  2255847 2488 499234 22808628 11756 0 14822 0 0 0
        cpu0 560937 782 128282 5702188 2818 0 7305 0 0 0
        cpu1 567768 565 124308 5702499 2935 0 2189 0 0 0
        cpu2 557372 575 123413 5701976 2996 0 2563 0 0 0
        cpu3 569769 564 123230 5701963 3004 0 2763 0 0 0
        intr 59306616 11 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=cpu_stat_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse CPU usage
        cpu_usage = processor._parse_cpu_usage(cpu_stat_output)
        
        # Verify the CPU usage is correctly parsed
        assert isinstance(cpu_usage, float)
        assert cpu_usage >= 0.0 and cpu_usage <= 100.0
    
    def test_parse_memory_info(self):
        """Test parsing of memory information."""
        # Sample output from `cat /proc/meminfo`
        meminfo_output = """
        MemTotal:       16384000 kB
        MemFree:         1547908 kB
        MemAvailable:    8273456 kB
        Buffers:          872512 kB
        Cached:          6343352 kB
        SwapCached:            0 kB
        Active:          8273456 kB
        Inactive:        5502824 kB
        Active(anon):    6560416 kB
        Inactive(anon):   147400 kB
        Active(file):    1713040 kB
        Inactive(file):  5355424 kB
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=meminfo_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse memory info
        memory_info = processor._parse_memory_info(meminfo_output)
        
        # Verify the memory info is correctly parsed
        assert 'total' in memory_info
        assert 'free' in memory_info
        assert 'available' in memory_info
        assert 'used' in memory_info
        assert 'cached' in memory_info
        assert memory_info['total'] == 16384000
        assert memory_info['free'] == 1547908
        assert memory_info['available'] == 8273456
        assert memory_info['used'] == memory_info['total'] - memory_info['free']
        assert memory_info['cached'] == 6343352

    def test_parse_disk_info(self):
        """Test parsing of disk information."""
        # Sample output from `df -h`
        df_output = """
        Filesystem      Size  Used Avail Use% Mounted on
        /dev/sda3       100G   20G   80G  20% /
        /dev/sdb1       2.0T  1.2T  800G  60% /mnt/disk1
        /dev/sdc1       4.0T  2.5T  1.5T  63% /mnt/disk2
        /dev/sdd1       8.0T  6.0T  2.0T  75% /mnt/disk3
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=df_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse disk info
        disk_info = processor._parse_disk_info(df_output)
        
        # Verify the disk info is correctly parsed
        assert len(disk_info) == 4
        assert '/dev/sda3' in disk_info
        assert disk_info['/dev/sda3']['size'] == '100G'
        assert disk_info['/dev/sda3']['used'] == '20G'
        assert disk_info['/dev/sda3']['avail'] == '80G'
        assert disk_info['/dev/sda3']['use_percentage'] == '20%'
        assert disk_info['/dev/sda3']['mounted_on'] == '/'
        
        assert '/dev/sdd1' in disk_info
        assert disk_info['/dev/sdd1']['size'] == '8.0T'
        assert disk_info['/dev/sdd1']['used'] == '6.0T'
        assert disk_info['/dev/sdd1']['avail'] == '2.0T'
        assert disk_info['/dev/sdd1']['use_percentage'] == '75%'
        assert disk_info['/dev/sdd1']['mounted_on'] == '/mnt/disk3'

    def test_parse_temperature(self):
        """Test parsing of temperature information."""
        # Sample output from temperature commands
        temp_output = """
        Adapter: ISA adapter
        Package id 0:  +45.0°C  (high = +80.0°C, crit = +100.0°C)
        Core 0:        +42.0°C  (high = +80.0°C, crit = +100.0°C)
        Core 1:        +40.0°C  (high = +80.0°C, crit = +100.0°C)
        Core 2:        +43.0°C  (high = +80.0°C, crit = +100.0°C)
        Core 3:        +41.0°C  (high = +80.0°C, crit = +100.0°C)
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=temp_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Sample temperature line
        temp_line = "Package id 0:  +45.0°C  (high = +80.0°C, crit = +100.0°C)"
        
        # Parse temperature
        temperature = processor._extract_temperature(temp_line)
        
        # Verify the temperature is correctly parsed
        assert temperature == 45.0
    
    def test_parse_docker_info(self):
        """Test parsing of Docker container information."""
        # Sample output from `docker ps`
        docker_ps_output = """
        CONTAINER ID   IMAGE                             COMMAND                  CREATED       STATUS       PORTS                                        NAMES
        abc123def456   linuxserver/plex                  "/init"                  2 weeks ago   Up 2 weeks   32400/tcp                                     plex
        789ghi101112   linuxserver/heimdall              "/init"                  2 weeks ago   Up 2 weeks   80/tcp, 443/tcp                              heimdall
        jkl131415mno   ghcr.io/linuxserver/radarr        "/init"                  2 weeks ago   Up 2 weeks   7878/tcp                                     radarr
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=docker_ps_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse Docker info
        docker_info = processor._parse_docker_containers(docker_ps_output)
        
        # Verify the Docker info is correctly parsed
        assert len(docker_info) == 3
        
        # Check the first container
        assert docker_info[0]['container_id'] == 'abc123def456'
        assert docker_info[0]['image'] == 'linuxserver/plex'
        assert docker_info[0]['command'] == '"/init"'
        assert docker_info[0]['status'] == 'Up 2 weeks'
        assert docker_info[0]['ports'] == '32400/tcp'
        assert docker_info[0]['name'] == 'plex'
        
        # Check the last container
        assert docker_info[2]['container_id'] == 'jkl131415mno'
        assert docker_info[2]['image'] == 'ghcr.io/linuxserver/radarr'
        assert docker_info[2]['command'] == '"/init"'
        assert docker_info[2]['status'] == 'Up 2 weeks'
        assert docker_info[2]['ports'] == '7878/tcp'
        assert docker_info[2]['name'] == 'radarr'
    
    def test_parse_vm_info(self):
        """Test parsing of VM information."""
        # Sample output from `virsh list --all`
        virsh_output = """
        Id   Name          State
        --------------------------------
        1    Windows10     running
        -    Ubuntu20.04   shut off
        -    Debian10      shut off
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=virsh_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse VM info
        vm_info = processor._parse_vm_info(virsh_output)
        
        # Verify the VM info is correctly parsed
        assert len(vm_info) == 3
        
        # Check each VM
        assert vm_info[0]['id'] == '1'
        assert vm_info[0]['name'] == 'Windows10'
        assert vm_info[0]['state'] == 'running'
        
        assert vm_info[1]['id'] == '-'
        assert vm_info[1]['name'] == 'Ubuntu20.04'
        assert vm_info[1]['state'] == 'shut off'
        
        assert vm_info[2]['id'] == '-'
        assert vm_info[2]['name'] == 'Debian10'
        assert vm_info[2]['state'] == 'shut off'
    
    def test_parse_ups_info(self):
        """Test parsing of UPS information."""
        # Sample output from `upsc ups@localhost`
        upsc_output = """
        battery.charge: 100
        battery.charge.low: 10
        battery.charge.warning: 50
        battery.runtime: 1800
        battery.type: PbAc
        device.mfr: CyberPower
        device.model: CP1500PFCLCD
        device.serial: CPS1234567890
        device.type: ups
        driver.name: usbhid-ups
        driver.parameter.pollfreq: 30
        driver.parameter.pollinterval: 2
        driver.version: 2.7.4
        driver.version.data: CyberPower HID 0.4
        driver.version.internal: 0.41
        input.voltage: 120.0
        input.voltage.nominal: 120
        output.voltage: 120.0
        ups.beeper.status: enabled
        ups.delay.shutdown: 20
        ups.load: 40
        ups.mfr: CyberPower
        ups.model: CP1500PFCLCD
        ups.serial: CPS1234567890
        ups.status: OL
        ups.test.result: No test initiated
        ups.timer.shutdown: -1
        ups.timer.start: -1
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=upsc_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse UPS info
        ups_info = processor._parse_ups_info(upsc_output)
        
        # Verify the UPS info is correctly parsed
        assert ups_info['battery.charge'] == '100'
        assert ups_info['battery.runtime'] == '1800'
        assert ups_info['device.mfr'] == 'CyberPower'
        assert ups_info['device.model'] == 'CP1500PFCLCD'
        assert ups_info['input.voltage'] == '120.0'
        assert ups_info['output.voltage'] == '120.0'
        assert ups_info['ups.load'] == '40'
        assert ups_info['ups.status'] == 'OL'
    
    def test_parse_gpu_info(self):
        """Test parsing of GPU information."""
        # Sample output from `nvidia-smi --query-gpu=...`
        nvidia_smi_output = """
        index, name, temperature.gpu, utilization.gpu [%], utilization.memory [%], memory.total [MiB], memory.free [MiB], memory.used [MiB]
        0, NVIDIA GeForce RTX 3080, 45, 5, 3, 10240, 9800, 440
        """
        
        # Create a mock client that returns this output
        mock_client = AsyncMock()
        mock_client.run_command.return_value = MagicMock(stdout=nvidia_smi_output.strip())
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse GPU info
        gpu_info = processor._parse_gpu_info(nvidia_smi_output)
        
        # Verify the GPU info is correctly parsed
        assert len(gpu_info) == 1
        assert gpu_info[0]['index'] == '0'
        assert gpu_info[0]['name'] == 'NVIDIA GeForce RTX 3080'
        assert gpu_info[0]['temperature.gpu'] == '45'
        assert gpu_info[0]['utilization.gpu [%]'] == '5'
        assert gpu_info[0]['utilization.memory [%]'] == '3'
        assert gpu_info[0]['memory.total [MiB]'] == '10240'
        assert gpu_info[0]['memory.free [MiB]'] == '9800'
        assert gpu_info[0]['memory.used [MiB]'] == '440'
    
    def test_parse_zfs_info(self):
        """Test parsing of ZFS pool information."""
        # Sample output from `zpool list`
        zpool_list_output = """
        NAME        SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP  HEALTH  ALTROOT
        tank        9.94T  5.67T  4.27T        -         -     1%    57%  1.00x  ONLINE  -
        backup      4.97T  3.82T  1.15T        -         -     2%    76%  1.00x  ONLINE  -
        """
        
        # Sample output from `zpool status`
        zpool_status_output = """
        pool: tank
        state: ONLINE
        scan: scrub repaired 0B in 0 days 05:30:25 with 0 errors on Sun Apr 10 05:30:25 2022
        
        NAME        STATE     READ WRITE CKSUM
        tank        ONLINE       0     0     0
          mirror-0  ONLINE       0     0     0
            sda     ONLINE       0     0     0
            sdb     ONLINE       0     0     0
          mirror-1  ONLINE       0     0     0
            sdc     ONLINE       0     0     0
            sdd     ONLINE       0     0     0
        """
        
        # Create a mock client that returns these outputs
        mock_client = AsyncMock()
        mock_client.run_command.side_effect = [
            MagicMock(stdout=zpool_list_output.strip()),
            MagicMock(stdout=zpool_status_output.strip())
        ]
        
        # Create a data processor and parse the output
        from custom_components.unraid.api.data_processor import DataProcessor
        processor = DataProcessor(mock_client)
        
        # Parse ZFS pool list
        zfs_pools = processor._parse_zfs_pools(zpool_list_output)
        
        # Verify the ZFS pool info is correctly parsed
        assert len(zfs_pools) == 2
        
        # Check the first pool
        assert zfs_pools[0]['name'] == 'tank'
        assert zfs_pools[0]['size'] == '9.94T'
        assert zfs_pools[0]['alloc'] == '5.67T'
        assert zfs_pools[0]['free'] == '4.27T'
        assert zfs_pools[0]['frag'] == '1%'
        assert zfs_pools[0]['cap'] == '57%'
        assert zfs_pools[0]['health'] == 'ONLINE'
        
        # Check the second pool
        assert zfs_pools[1]['name'] == 'backup'
        assert zfs_pools[1]['size'] == '4.97T'
        assert zfs_pools[1]['alloc'] == '3.82T'
        assert zfs_pools[1]['free'] == '1.15T'
        assert zfs_pools[1]['frag'] == '2%'
        assert zfs_pools[1]['cap'] == '76%'
        assert zfs_pools[1]['health'] == 'ONLINE'
        
        # Parse ZFS pool status
        zfs_status = processor._parse_zfs_status(zpool_status_output)
        
        # Verify the ZFS status is correctly parsed
        assert zfs_status['pool'] == 'tank'
        assert zfs_status['state'] == 'ONLINE'
        assert 'scan' in zfs_status
        assert len(zfs_status['devices']) > 0
        assert zfs_status['devices'][0]['name'] == 'tank'
        assert zfs_status['devices'][0]['state'] == 'ONLINE'
        assert zfs_status['devices'][1]['name'] == 'mirror-0'
        assert zfs_status['devices'][1]['state'] == 'ONLINE' 