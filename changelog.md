# Changelog

## Unreleased

### Added
- ZFS cache pool support: The integration now correctly detects and reports usage for ZFS-based cache pools
- Enhanced device path detection for ZFS pools
- Automatic filesystem type detection for cache pools (ZFS, Btrfs, XFS, etc.)

### Fixed
- Fixed incorrect cache usage reporting for ZFS pools (previously showing 0.0%)
- Improved handling of device paths in `disk_state.py` for ZFS devices