#!/usr/bin/env python3
"""Script to check the structure of unraid data from the collector."""
import json
import sys
import os

def main():
    """Main function to parse and display Unraid data structure."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <unraid_data.json>")
        sys.exit(1)

    data_file = sys.argv[1]
    if not os.path.exists(data_file):
        print(f"File not found: {data_file}")
        sys.exit(1)

    print(f"Loading data from: {data_file}")
    with open(data_file, "r") as f:
        data = json.load(f)

    print("\n=== Basic Data Structure ===")
    for key in data:
        if isinstance(data[key], dict):
            print(f"{key}: {len(data[key])} entries")
        elif isinstance(data[key], list):
            print(f"{key}: list with {len(data[key])} items")
        else:
            print(f"{key}: {data[key]}")

    # GPU Info
    print("\n=== GPU Info ===")
    gpu_info = data.get("gpu_info", {})
    print(f"NVIDIA GPU: {gpu_info.get('has_nvidia', False)}")
    print(f"AMD GPU: {gpu_info.get('has_amd', False)}")
    print(f"Intel GPU: {gpu_info.get('has_intel', False)}")

    # Check for specific GPU details
    if gpu_info.get("has_nvidia", False):
        print("\nNVIDIA GPU Details:")
        print(f"Info: {gpu_info.get('nvidia_info', 'Not available')}")

    if gpu_info.get("has_amd", False):
        print("\nAMD GPU Details:")
        print(f"Info: {gpu_info.get('amd_info', 'Not available')}")

    if gpu_info.get("has_intel", False):
        print("\nIntel GPU Details:")
        i915_info = gpu_info.get("i915_info", {})
        print(f"Driver version: {i915_info.get('driver_version', 'Unknown')}")
        print(f"Current frequency: {i915_info.get('current_freq_mhz', 'Unknown')} MHz")

    print("\nGPU Drivers:")
    gpu_drivers = gpu_info.get("gpu_drivers", "No drivers found")
    if gpu_drivers:
        for line in gpu_drivers.split("\n")[:5]:  # Show first 5 lines
            if line.strip():
                print(f"  {line}")
        if len(gpu_drivers.split("\n")) > 5:
            print("  ...")

    # ZFS Info
    print("\n=== ZFS Info ===")
    zfs_info = data.get("zfs_info", {})
    print(f"ZFS Available: {zfs_info.get('zfs_available', False)}")

    if zfs_info.get("zfs_available", False):
        print("\nZFS Module Info:")
        zfs_module = zfs_info.get("zfs_module", "No module info")
        if zfs_module:
            for line in zfs_module.split("\n")[:3]:  # Show first 3 lines
                if line.strip():
                    print(f"  {line}")

        print("\nZFS Pools:")
        pool_list = zfs_info.get("zpool_list", "No pools found")
        if pool_list:
            for line in pool_list.split("\n"):
                if line.strip():
                    fields = line.split("\t")
                    if len(fields) >= 8:
                        print(f"  {fields[0]}: {fields[7]} used, {fields[2]} size")
                    else:
                        print(f"  {line}")

        print("\nZFS Pool Status:")
        pool_status = zfs_info.get("zpool_status", "No status info")
        if pool_status:
            lines = pool_status.split("\n")

            current_pool = None
            for line in lines:
                line = line.strip()
                if line.startswith("pool:"):
                    current_pool = line.split(":", 1)[1].strip()
                    print(f"  Pool: {current_pool}")
                elif line.startswith("state:"):
                    state = line.split(":", 1)[1].strip()
                    print(f"  State: {state}")
                elif line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                    print(f"  Status: {status}")

    # emhttp_configs
    print("\n=== emhttp_configs ===")
    emhttp_configs = data.get("emhttp_configs", {})
    print(f"Number of config files: {len(emhttp_configs)}")

    if "emhttp_files_list" in emhttp_configs:
        print("\nConfig files available:")
        files_list = emhttp_configs.get("emhttp_files_list", "")
        for line in files_list.split("\n"):
            if ".ini" in line:
                print(f"  {line.strip()}")

    # Check for specific config files of interest
    for config_name in ["shares.ini", "network.ini", "users.ini"]:
        if config_name in emhttp_configs:
            print(f"\n{config_name} config available")
            config_data = emhttp_configs.get(config_name, "")
            # Just show first few lines
            lines = config_data.split("\n")[:5]
            for line in lines:
                print(f"  {line}")
            print("  ...")

if __name__ == "__main__":
    main()