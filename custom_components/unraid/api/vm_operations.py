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

    async def check_libvirt_running(self) -> bool:
        """Check if libvirt is running using multiple methods.

        Returns:
            bool: True if libvirt service is running, False otherwise.
        """
        try:
            # Method 1: Traditional rc.d script check
            service_check = await self.execute_command("/etc/rc.d/rc.libvirt status")
            if service_check.exit_status == 0 and "is currently running" in service_check.stdout:
                _LOGGER.debug("Libvirt validated through rc.d script")
                return True

            # Method 2: Process check
            process_check = await self.execute_command("pgrep -f libvirtd")
            if process_check.exit_status == 0:
                # Method 3: Socket file check
                sock_check = await self.execute_command("[ -S /var/run/libvirt/libvirt-sock ]")
                if sock_check.exit_status == 0:
                    _LOGGER.debug("Libvirt validated through process and socket checks")
                    return True

            _LOGGER.debug(
                "Libvirt service checks failed - rc.d: %s, process: %s",
                service_check.exit_status,
                process_check.exit_status
            )
            return False
        except Exception as err:
            _LOGGER.debug("Error checking libvirt status: %s", str(err))
            return False

    async def get_vms(self) -> List[Dict[str, Any]]:
        """Fetch information about virtual machines using a batched command."""
        try:
            _LOGGER.debug("Checking VM service status")

            # Use new service check method
            if not await self.check_libvirt_running():
                _LOGGER.debug("VM system is disabled or not installed")
                return []

            # Collect VM information in a single command
            try:
                # Use a more robust command that properly handles VM names with spaces and special characters
                # We use a unique delimiter (§§§) that's unlikely to appear in VM names or XML data
                cmd = (
                    "if [ -x /etc/rc.d/rc.libvirt ] && /etc/rc.d/rc.libvirt status | grep -q 'is currently running'; then "
                    "  virsh list --all --name | while IFS= read -r vm; do "
                    "    if [ -n \"$vm\" ] && [ \"$vm\" != \" \" ]; then "
                    "      state=$(virsh domstate \"$vm\" 2>/dev/null || echo 'unknown'); "
                    "      info=$(virsh dominfo \"$vm\" 2>/dev/null); "
                    "      cpus=$(echo \"$info\" | grep 'CPU(s)' | awk '{print $2}' | head -1); "
                    "      mem=$(echo \"$info\" | grep 'Max memory' | sed 's/Max memory://g' | xargs | head -1); "
                    "      xml=$(virsh dumpxml \"$vm\" 2>/dev/null | grep -A5 \"<os>\" | tr '\\n' ' '); "
                    "      echo \"$vm§§§$state§§§$cpus§§§$mem§§§$xml\"; "
                    "    fi; "
                    "  done; "
                    "else "
                    "  echo 'libvirt_not_running'; "
                    "fi"
                )

                result = await self.execute_command(cmd)

                if result.exit_status != 0 or result.stdout.strip() == 'libvirt_not_running':
                    _LOGGER.debug("No VMs found or libvirt not running")
                    return []

                vms = []
                for line in result.stdout.splitlines():
                    if not line.strip() or '§§§' not in line:
                        continue

                    try:
                        # Split on our unique delimiter
                        parts = line.split('§§§')
                        if len(parts) >= 5:
                            vm_name = parts[0].strip()
                            status = VMState.parse(parts[1].strip())
                            cpus = parts[2].strip() or '0'
                            memory = parts[3].strip() or '0'
                            xml_data = parts[4].strip()

                            # Skip empty VM names (shouldn't happen but be safe)
                            if not vm_name:
                                _LOGGER.debug("Skipping VM with empty name")
                                continue

                            _LOGGER.debug("Processing VM: '%s' with status: '%s'", vm_name, status)

                            # Determine OS type from XML data
                            os_type = 'unknown'
                            xml_lower = xml_data.lower()
                            if 'windows' in xml_lower or 'win' in xml_lower:
                                os_type = 'windows'
                            elif 'linux' in xml_lower:
                                os_type = 'linux'
                            else:
                                # Fallback to name-based detection
                                name_lower = vm_name.lower()
                                name_clean = name_lower.replace('-', ' ').replace('_', ' ')
                                if any(term in name_clean for term in ['windows', 'win']):
                                    os_type = 'windows'
                                elif any(term in name_clean for term in [
                                    'ubuntu', 'linux', 'debian', 'centos',
                                    'fedora', 'rhel', 'suse', 'arch'
                                ]):
                                    os_type = 'linux'

                            vms.append({
                                "name": vm_name,
                                "status": status,
                                "os_type": os_type,
                                "cpus": cpus,
                                "memory": memory
                            })
                    except Exception as vm_err:
                        _LOGGER.debug("Error processing VM line '%s': %s", line, str(vm_err))
                        continue

                _LOGGER.debug("Successfully processed %d VMs", len(vms))
                return vms

            except Exception as virsh_err:
                _LOGGER.debug("Error running batched VM command: %s", str(virsh_err))
                # Fallback to original implementation
                return await self._get_vms_original()

        except Exception as err:
            _LOGGER.debug("VM system appears to be disabled: %s", str(err))
            return []

    async def _get_vms_original(self) -> List[Dict[str, Any]]:
        """Original implementation of VM information collection as fallback."""
        try:
            result = await self.execute_command("virsh list --all --name")
            if result.exit_status != 0:
                _LOGGER.debug("No VMs found")
                return []

            vms = []
            for line in result.stdout.splitlines():
                vm_name = line.strip()
                if not vm_name:
                    continue

                try:
                    _LOGGER.debug("Processing VM (fallback): '%s'", vm_name)
                    status = await self.get_vm_status(vm_name)
                    os_type = await self.get_vm_os_info(vm_name)

                    vms.append({
                        "name": vm_name,
                        "status": status,
                        "os_type": os_type,
                        "cpus": "0",  # Add default values for consistency
                        "memory": "0"
                    })
                except Exception as vm_err:
                    _LOGGER.debug("Error processing VM '%s': %s", vm_name, str(vm_err))
                    continue

            _LOGGER.debug("Successfully processed %d VMs (fallback)", len(vms))
            return vms
        except Exception as err:
            _LOGGER.debug("Error in original VM method: %s", str(err))
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
            # Use shlex.quote to properly escape VM names with special characters
            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh domstate {escaped_name}')
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

            # Use shlex.quote to properly escape VM names with special characters
            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh start {escaped_name}')
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

            # Use shlex.quote to properly escape VM names with special characters
            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh shutdown {escaped_name}')
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

    async def pause_vm(self, vm_name: str) -> bool:
        """Pause a virtual machine."""
        try:
            _LOGGER.debug("Pausing VM: %s", vm_name)

            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "paused":
                _LOGGER.info("VM '%s' is already paused", vm_name)
                return True

            if current_state.lower() != "running":
                _LOGGER.error("Cannot pause VM '%s' because it is not running (current state: %s)", vm_name, current_state)
                return False

            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh suspend {escaped_name}')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to pause VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to pause
            for _ in range(15):
                await asyncio.sleep(1)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "paused":
                    _LOGGER.info("Successfully paused VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not pause in time", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error pausing VM '%s': %s", vm_name, str(err))
            return False

    async def resume_vm(self, vm_name: str) -> bool:
        """Resume a paused virtual machine."""
        try:
            _LOGGER.debug("Resuming VM: %s", vm_name)

            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "running":
                _LOGGER.info("VM '%s' is already running", vm_name)
                return True

            if current_state.lower() != "paused":
                _LOGGER.error("Cannot resume VM '%s' because it is not paused (current state: %s)", vm_name, current_state)
                return False

            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh resume {escaped_name}')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to resume VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to resume
            for _ in range(15):
                await asyncio.sleep(1)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "running":
                    _LOGGER.info("Successfully resumed VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not resume in time", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error resuming VM '%s': %s", vm_name, str(err))
            return False

    async def restart_vm(self, vm_name: str) -> bool:
        """Restart a virtual machine."""
        try:
            _LOGGER.debug("Restarting VM: %s", vm_name)

            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() != "running":
                _LOGGER.error("Cannot restart VM '%s' because it is not running (current state: %s)", vm_name, current_state)
                return False

            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh reboot {escaped_name}')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to restart VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to restart (it should remain in running state)
            for _ in range(30):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "running":
                    _LOGGER.info("Successfully restarted VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not restart properly", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error restarting VM '%s': %s", vm_name, str(err))
            return False

    async def hibernate_vm(self, vm_name: str) -> bool:
        """Hibernate a virtual machine (suspend to disk)."""
        try:
            _LOGGER.debug("Hibernating VM: %s", vm_name)

            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == VMState.SUSPENDED.value:
                _LOGGER.info("VM '%s' is already suspended", vm_name)
                return True

            if current_state.lower() != "running":
                _LOGGER.error("Cannot hibernate VM '%s' because it is not running (current state: %s)", vm_name, current_state)
                return False

            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh dompmsuspend {escaped_name} disk')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to hibernate VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to hibernate
            for _ in range(30):
                await asyncio.sleep(2)
                status = await self.get_vm_status(vm_name)
                if status.lower() == VMState.SUSPENDED.value:
                    _LOGGER.info("Successfully hibernated VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not hibernate in time", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error hibernating VM '%s': %s", vm_name, str(err))
            return False

    async def force_stop_vm(self, vm_name: str) -> bool:
        """Force stop a virtual machine."""
        try:
            _LOGGER.debug("Force stopping VM: %s", vm_name)

            # Check current state first
            current_state = await self.get_vm_status(vm_name)
            if current_state.lower() == "shut off":
                _LOGGER.info("VM '%s' is already shut off", vm_name)
                return True

            escaped_name = shlex.quote(vm_name)
            result = await self.execute_command(f'virsh destroy {escaped_name}')
            success = result.exit_status == 0

            if not success:
                _LOGGER.error("Failed to force stop VM '%s': %s", vm_name, result.stderr)
                return False

            # Wait for VM to stop
            for _ in range(15):
                await asyncio.sleep(1)
                status = await self.get_vm_status(vm_name)
                if status.lower() == "shut off":
                    _LOGGER.info("Successfully force stopped VM '%s'", vm_name)
                    return True

            _LOGGER.error("VM '%s' did not shut off in time after force stop", vm_name)
            return False

        except Exception as err:
            _LOGGER.error("Error force stopping VM '%s': %s", vm_name, str(err))
            return False
