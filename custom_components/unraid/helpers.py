"""Helper utilities for Unraid integration."""
from enum import Enum
from dataclasses import dataclass
from typing import Tuple
import math
import logging

_LOGGER = logging.getLogger(__name__)

@dataclass
class NetworkSpeedUnit:
    """Network unit representation."""
    multiplier: int
    symbol: str

NETWORK_UNITS = [
    NetworkSpeedUnit(1, "bit/s"),
    NetworkSpeedUnit(1000, "kbit/s"),
    NetworkSpeedUnit(1000000, "Mbit/s"),
    NetworkSpeedUnit(1000000000, "Gbit/s"),
]

def get_network_speed_unit(bytes_per_sec: float) -> Tuple[float, str]:
    """Get the most appropriate unit for a given network speed."""
    if bytes_per_sec <= 0:
        return (0.0, NETWORK_UNITS[0].symbol)

    # Convert bytes to bits
    bits_per_sec = bytes_per_sec * 8
    
    # Find the appropriate unit
    unit_index = min(
        len(NETWORK_UNITS) - 1,
        max(0, math.floor(math.log10(bits_per_sec) / 3))
    )
    
    selected_unit = NETWORK_UNITS[unit_index]
    converted_value = bits_per_sec / selected_unit.multiplier
    
    return (round(converted_value, 2), selected_unit.symbol)

def format_bytes(bytes_value: float) -> str:
    """Format bytes into appropriate units."""
    if bytes_value <= 0:
        return "0 B"
        
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = min(
        len(units) - 1,
        max(0, math.floor(math.log10(bytes_value) / 3))
    )
    
    value = bytes_value / (1024 ** unit_index)
    return f"{value:.2f} {units[unit_index]}"