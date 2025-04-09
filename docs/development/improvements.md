---
layout: default
title: Planned Improvements
---

Based on user feedback and ongoing development, the following improvements are planned for the Home Assistant Unraid Integration.

## SSH Connection Optimization

### Standalone Data Collection Tool

- **Description**: Create a standalone tool for Unraid integration that collects data via SSH and stores it in JSON
- **Benefits**:
  - Reduced SSH connections
  - Lower log spam in Unraid syslog
  - Improved data collection efficiency
  - Better error handling
- **Status**: In development

### Command Batching

- **Description**: Implement batched commands for system statistics, disk information, and SMART data collection
- **Benefits**:
  - Significantly reduced SSH log spam
  - Faster data collection
  - Lower resource usage on both Home Assistant and Unraid
- **Status**: Completed

### SSH Key Authentication

- **Description**: Add support for SSH key-based authentication
- **Benefits**:
  - Enhanced security by removing password authentication
  - Support for servers with password authentication disabled
- **Status**: Planned

## Data Collection Improvements

### SMART Data Mapping

- **Description**: Implement improved SMART data mapping for better disk health monitoring
- **Benefits**:
  - More accurate disk health reporting
  - Better early warning for potential disk failures
  - Support for a wider range of disk types
- **Status**: Completed

### NVMe Temperature Parsing

- **Description**: Add specialized parsing for NVMe temperature data
- **Benefits**:
  - Accurate temperature reporting for NVMe drives
  - Better thermal monitoring for high-performance storage
- **Status**: In development

### USB Boot Drive Handling

- **Description**: Improve handling of USB boot drives that don't support SMART commands
- **Benefits**:
  - Prevent errors when querying USB boot drives
  - Proper identification of boot media
- **Status**: Completed

### ZFS Support

- **Description**: Add support for ZFS-based cache pools
- **Benefits**:
  - Accurate usage reporting for ZFS filesystems
  - Support for advanced ZFS features
- **Status**: Completed

## Bug Fixes

### International Format Parsing

- **Description**: Fix parsing errors for speeds and dates with international formats
- **Benefits**:
  - Support for comma-based decimal separators (e.g., "84,6 MB/s")
  - Correct date parsing regardless of locale
- **Status**: Planned

### Disk Health Reporting

- **Description**: Fix disk health reporting for used space and total size attributes
- **Benefits**:
  - Accurate reporting of disk usage for each array disk
  - Proper monitoring of free space
- **Status**: Planned

## Feature Enhancements

### Docker Container Pause/Unpause

- **Description**: Add pause/unpause functionality for Docker containers
- **Benefits**:
  - More granular control over container states
  - Ability to temporarily suspend resource-intensive containers
- **Status**: Planned

### Docker Update Entities

- **Description**: Add update entities for Docker containers
- **Benefits**:
  - Notification when container updates are available
  - Integration with Home Assistant's update system
- **Status**: Planned

### CPU Load Sensors

- **Description**: Add CPU load sensors in watts for 1, 5, and 15-minute averages
- **Benefits**:
  - Better power usage monitoring
  - More detailed CPU performance metrics
- **Status**: Planned

## Performance Optimizations

### Memory Usage Improvements

- **Description**: Optimize memory usage in the integration
- **Benefits**:
  - Reduced resource consumption
  - Better stability on resource-constrained systems
- **Status**: Ongoing

### Cache Management

- **Description**: Enhance the cache management system
- **Benefits**:
  - More efficient data storage
  - Faster response times
  - Reduced server load
- **Status**: Ongoing
