"""VM operations for Unraid."""
from __future__ import annotations

import logging
import shlex
from typing import Dict, List, Any
from enum import Enum

import asyncio

_LOGGER = logging.getLogger(__name__)

class VMState(Enum):
    """VM states matching Unraid/libvirt states."""
    RUNNING = 'running'
    STOPPED = 'shut off'
    PAUSED = 'paused'
    IDLE = 'idle'
    IN_SHUTDOWN = 'in shutdown'
    CRASHED = 'crashed'
    SUSPENDED = 'pmsuspended'

    @classmethod
    def is_running(cls, state: str) -> bool:
        """Check if the state represents a running VM."""
        return state.lower() == cls.RUNNING.value

    @classmethod
    def parse(cls, state: str) -> str:
        """Parse the VM state string."""
        state = state.lower().strip()
        try:
            return next(s.value for s in cls if s.value == state)
        except StopIteration:
            return state

class VMOperationsMixin:
    """Mixin for VM-related operations."""

    async def get_vms(self) -> List[Dict[str, Any]]:
        """Fetch information about virtual machines."""
        try:
            _LOGGER.debug("Checking VM service status")
            # First check if VM system is enabled via libvirt
            service_check = await self.execute_command("/etc/rc.d/rc.libvirt status")
            
            # If service check fails or service isn't running, VMs are disabled
            if service_check.exit_status != 0:
                _LOGGER.debug("VM system is disabled or not installed")
                return []
                
            if "is currently running" not in service_check.stdout:
                _LOGGER.debug("VM service is not running")
                return []

            # Only proceed with VM checks if service is running and enabled
            try:
                result = await self.execute_command("virsh list --all --name")
                if result.exit_status != 0:
                    _LOGGER.debug("No VMs found")
                    return []

                vms = []
                for line in result.stdout.splitlines():
                    if not line.strip():
                        continue

                    try:
                        vm_name = line.strip()
                        status = await self.get_vm_status(vm_name)
                        os_type = await self.get_vm_os_info(vm_name)

                        vms.append({
                            "name": vm_name,
                            "status": status,
                            "os_type": os_type
                        })

                    except Exception as vm_err:
                        _LOGGER.debug("Error processing VM '%s': %s", line.strip(), str(vm_err))
                        continue

                return vms

            except Exception as virsh_err:
                _LOGGER.debug("Error running virsh command: %s", str(virsh_err))
                return []

        except Exception as err:
            _LOGGER.debug("VM system appears to be disabled: %s", str(err))
            return []

    async def get_vm_os_info(self, vm_name: str) -> str:
        """Get the OS type of a VM."""
        try:
            # Try to get OS info from multiple sources
            escaped_name = shlex.quote(vm_name)
            xml_result = await self.execute_command(
                f'virsh dumpxml {escaped_name} | grep -A5 "<os>"'
            )

            if xml_result.exit_status == 0:
                xml_output = xml_result.stdout.lower()
                if 'windows' in xml_output or 'win' in xml_output:
                    return 'windows'
                if 'linux' in xml_output:
                    return 'linux'

            # Check VM name patterns
            name_lower = vm_name.lower()
            name_clean = name_lower.replace('-', ' ').replace('_', ' ')

            # Check for Windows indicators
            if any(term in name_clean for term in ['windows', 'win']):
                return 'windows'

            # Check for Linux indicators
            if any(term in name_clean for term in [
                'ubuntu', 'linux', 'debian', 'centos', 
                'fedora', 'rhel', 'suse', 'arch'
            ]):
                return 'linux'

            return 'unknown'

        except Exception as err:
            _LOGGER.debug(
                "Error getting OS info for VM '%s': %s", 
                vm_name,
                str(err)
            )
            return 'unknown'

    async def get_vm_status(self, vm_name: str) -> str:
        """Get detailed status of a specific virtual machine."""
        try:
            result = await self.execute_command(f'virsh domstate "{vm_name}"')
            if result.exit_status != 0:
                _LOGGER.error("Failed to get VM status for '%s': %s", vm_name, result.stderr)
                return VMState.CRASHED.value
            return VMState.parse(result.stdout.strip())
        except Exception as err:
            _LOGGER.error("Error getting VM status for '%s': %s", vm_name, str(err))
            return VMState.CRASHED.value

    async def start_vm(self, vm_name: str) -> bool:
        """Start a virtual machine."""
        try:
            _LOGGER.debug("Starting VM: %s", vm_name)
            
            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "running":
                _LOGGER.info("VM '%s' is already running", vm_name)
                return True

            result = await self.execute_command(f'virsh start "{vm_name}"')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to start VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to start
            for _ in range(15):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "running":
                    _LOGGER.info("Successfully started VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not reach running state in time", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error starting VM '%s': %s", vm_name, str(err))
            return False

    async def stop_vm(self, vm_name: str) -> bool:
        """Stop a virtual machine using ACPI shutdown."""
        try:
            _LOGGER.debug("Stopping VM: %s", vm_name)
            
            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "shut off":
                _LOGGER.info("VM '%s' is already shut off", vm_name)
                return True

            result = await self.execute_command(f'virsh shutdown "{vm_name}"')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to stop VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to stop
            for _ in range(30):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "shut off":
                    _LOGGER.info("Successfully stopped VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not shut off in time", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error stopping VM '%s': %s", vm_name, str(err))
            return False