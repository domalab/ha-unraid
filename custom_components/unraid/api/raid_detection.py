"""RAID controller detection for Unraid."""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

@dataclass
class RAIDControllerInfo:
    """Information about detected RAID controller."""
    vendor: str
    model: str
    pci_id: str
    driver: str
    mode: str  # "raid", "it", "unknown"
    disk_count: int
    logical_drives: List[str]
    physical_drives: List[str]
    recommendation: str

class RAIDControllerDetector:
    """Detect and analyze RAID controllers."""
    
    # Known RAID controller patterns
    RAID_CONTROLLERS = {
        "lsi_megaraid": {
            "pci_patterns": [r"lsi.*megaraid", r"broadcom.*megaraid", r"avago.*megaraid"],
            "driver_patterns": ["megaraid_sas", "mpt3sas"],
            "detection_commands": {
                "lspci": "lspci -v | grep -i -A5 -B2 'raid\\|lsi\\|broadcom.*sas'",
                "megacli": "which megacli || which MegaCli || which storcli",
                "logical_drives": "ls /dev/sd* 2>/dev/null | wc -l"
            },
            "recommendation": "Consider flashing to IT mode for better Unraid compatibility"
        },
        "dell_perc": {
            "pci_patterns": [r"dell.*perc", r"lsi.*dell"],
            "driver_patterns": ["megaraid_sas", "mpt3sas"],
            "detection_commands": {
                "lspci": "lspci -v | grep -i -A5 -B2 'dell.*perc'",
                "perccli": "which perccli || which MegaCli",
                "logical_drives": "ls /dev/sd* 2>/dev/null | wc -l"
            },
            "recommendation": "Flash to HBA330 IT mode for optimal Unraid performance"
        },
        "hp_smart_array": {
            "pci_patterns": [r"hewlett.*smart", r"hp.*smart.*array"],
            "driver_patterns": ["hpsa", "cciss"],
            "detection_commands": {
                "lspci": "lspci -v | grep -i -A5 -B2 'hewlett.*smart'",
                "hpacucli": "which hpacucli || which hpssacli",
                "logical_drives": "ls /dev/sd* 2>/dev/null | wc -l"
            },
            "recommendation": "Consider HBA mode if available, or use individual disk connections"
        },
        "adaptec": {
            "pci_patterns": [r"adaptec", r"microsemi.*adaptec"],
            "driver_patterns": ["aacraid", "smartpqi"],
            "detection_commands": {
                "lspci": "lspci -v | grep -i -A5 -B2 'adaptec'",
                "arcconf": "which arcconf",
                "logical_drives": "ls /dev/sd* 2>/dev/null | wc -l"
            },
            "recommendation": "Check for HBA/JBOD mode in controller settings"
        }
    }

    def __init__(self, execute_command_func):
        """Initialize RAID controller detector."""
        self.execute_command = execute_command_func
        self._detected_controllers: List[RAIDControllerInfo] = []

    async def detect_raid_controllers(self) -> List[RAIDControllerInfo]:
        """Detect all RAID controllers in the system."""
        _LOGGER.debug("Starting RAID controller detection")
        controllers = []

        try:
            # Get PCI device information
            pci_result = await self.execute_command("lspci -v")
            if pci_result.exit_status != 0:
                _LOGGER.warning("Could not get PCI device information")
                return controllers

            pci_output = pci_result.stdout.lower()

            # Check each controller type
            for controller_type, config in self.RAID_CONTROLLERS.items():
                for pattern in config["pci_patterns"]:
                    if re.search(pattern, pci_output):
                        _LOGGER.info("Detected potential %s controller", controller_type)
                        controller_info = await self._analyze_controller(controller_type, config)
                        if controller_info:
                            controllers.append(controller_info)

            # Detect HBA controllers in IT mode (good for Unraid)
            hba_controllers = await self._detect_hba_controllers()
            controllers.extend(hba_controllers)

            self._detected_controllers = controllers
            return controllers

        except Exception as err:
            _LOGGER.error("Error detecting RAID controllers: %s", err)
            return controllers

    async def _analyze_controller(self, controller_type: str, config: Dict[str, Any]) -> Optional[RAIDControllerInfo]:
        """Analyze a specific RAID controller."""
        try:
            # Get detailed PCI information
            pci_cmd = config["detection_commands"]["lspci"]
            pci_result = await self.execute_command(pci_cmd)
            
            if pci_result.exit_status != 0:
                return None

            # Extract controller details
            pci_lines = pci_result.stdout.splitlines()
            vendor = "Unknown"
            model = "Unknown"
            pci_id = "Unknown"
            driver = "Unknown"

            for line in pci_lines:
                if ":" in line and any(keyword in line.lower() for keyword in ["raid", "sas", "scsi"]):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        pci_id = parts[0].strip()
                        model = parts[1].strip()
                        if "lsi" in model.lower() or "broadcom" in model.lower():
                            vendor = "LSI/Broadcom"
                        elif "dell" in model.lower():
                            vendor = "Dell"
                        elif "hp" in model.lower() or "hewlett" in model.lower():
                            vendor = "HP"
                        elif "adaptec" in model.lower():
                            vendor = "Adaptec"

            # Determine controller mode
            mode = await self._determine_controller_mode(controller_type, config)
            
            # Count logical and physical drives
            logical_drives = await self._count_logical_drives()
            physical_drives = await self._count_physical_drives()

            return RAIDControllerInfo(
                vendor=vendor,
                model=model,
                pci_id=pci_id,
                driver=driver,
                mode=mode,
                disk_count=len(physical_drives),
                logical_drives=logical_drives,
                physical_drives=physical_drives,
                recommendation=config["recommendation"]
            )

        except Exception as err:
            _LOGGER.debug("Error analyzing %s controller: %s", controller_type, err)
            return None

    async def _determine_controller_mode(self, controller_type: str, config: Dict[str, Any]) -> str:
        """Determine if controller is in RAID or IT/HBA mode."""
        try:
            # Check for RAID management tools
            mgmt_tools = ["megacli", "storcli", "perccli", "hpacucli", "arcconf"]
            tools_found = []
            
            for tool in mgmt_tools:
                result = await self.execute_command(f"which {tool}")
                if result.exit_status == 0:
                    tools_found.append(tool)

            # If management tools are present, likely in RAID mode
            if tools_found:
                _LOGGER.debug("RAID management tools found: %s", tools_found)
                return "raid"

            # Check driver modules
            driver_result = await self.execute_command("lsmod | grep -E 'mpt3sas|mpt2sas'")
            if driver_result.exit_status == 0 and "mpt" in driver_result.stdout:
                # MPT drivers usually indicate IT mode
                return "it"

            return "unknown"

        except Exception as err:
            _LOGGER.debug("Error determining controller mode: %s", err)
            return "unknown"

    async def _detect_hba_controllers(self) -> List[RAIDControllerInfo]:
        """Detect HBA controllers (good for Unraid)."""
        hba_controllers = []
        
        try:
            # Look for common HBA patterns
            hba_patterns = [
                r"lsi.*9\d{3}",  # LSI 9xxx series
                r"broadcom.*9\d{3}",
                r"sas.*9\d{3}"
            ]

            pci_result = await self.execute_command("lspci | grep -i sas")
            if pci_result.exit_status == 0:
                for line in pci_result.stdout.splitlines():
                    for pattern in hba_patterns:
                        if re.search(pattern, line.lower()):
                            # This looks like an HBA
                            parts = line.split(":", 1)
                            pci_id = parts[0].strip() if parts else "Unknown"
                            model = parts[1].strip() if len(parts) > 1 else "Unknown"

                            hba_info = RAIDControllerInfo(
                                vendor="LSI/Broadcom",
                                model=model,
                                pci_id=pci_id,
                                driver="mpt3sas",
                                mode="it",
                                disk_count=0,  # Will be populated later
                                logical_drives=[],
                                physical_drives=[],
                                recommendation="Excellent for Unraid - individual disk access enabled"
                            )
                            hba_controllers.append(hba_info)
                            _LOGGER.info("Detected HBA controller: %s", model)

        except Exception as err:
            _LOGGER.debug("Error detecting HBA controllers: %s", err)

        return hba_controllers

    async def _count_logical_drives(self) -> List[str]:
        """Count logical drives visible to the system."""
        try:
            result = await self.execute_command("ls /dev/sd* 2>/dev/null")
            if result.exit_status == 0:
                drives = [line.strip() for line in result.stdout.splitlines() 
                         if line.strip() and not line.strip().endswith(tuple('123456789'))]
                return drives
        except Exception as err:
            _LOGGER.debug("Error counting logical drives: %s", err)
        return []

    async def _count_physical_drives(self) -> List[str]:
        """Attempt to count physical drives behind controller."""
        try:
            # This is challenging without controller-specific tools
            # For now, return the same as logical drives
            return await self._count_logical_drives()
        except Exception as err:
            _LOGGER.debug("Error counting physical drives: %s", err)
        return []

    def get_raid_advisory(self) -> Dict[str, Any]:
        """Get RAID controller advisory information."""
        if not self._detected_controllers:
            return {
                "status": "optimal",
                "message": "No RAID controllers detected - optimal for Unraid",
                "controllers": [],
                "recommendations": []
            }

        recommendations = []
        raid_mode_controllers = []
        it_mode_controllers = []

        for controller in self._detected_controllers:
            if controller.mode == "raid":
                raid_mode_controllers.append(controller)
                recommendations.append(controller.recommendation)
            elif controller.mode == "it":
                it_mode_controllers.append(controller)

        if raid_mode_controllers:
            status = "warning"
            message = f"Detected {len(raid_mode_controllers)} RAID controller(s) in RAID mode"
        elif it_mode_controllers:
            status = "optimal"
            message = f"Detected {len(it_mode_controllers)} HBA controller(s) in IT mode"
        else:
            status = "unknown"
            message = "RAID controllers detected but mode unclear"

        return {
            "status": status,
            "message": message,
            "controllers": [
                {
                    "vendor": c.vendor,
                    "model": c.model,
                    "mode": c.mode,
                    "disk_count": c.disk_count,
                    "recommendation": c.recommendation
                }
                for c in self._detected_controllers
            ],
            "recommendations": list(set(recommendations))
        }
