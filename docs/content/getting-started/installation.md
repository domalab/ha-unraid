---
layout: default
title: Installation
parent: Getting Started
nav_order: 1
show_ads: true
show_header_ad: true
show_footer_ad: true
---

# Installation Guide

This guide will walk you through the process of installing the Unraid Integration for Home Assistant.

## Prerequisites

Before installing the integration, make sure you have:

1. A running Home Assistant installation
2. An Unraid server with SSH enabled
3. Valid login credentials for your Unraid server

## Installation Methods

### HACS (Recommended)

The easiest way to install the Unraid Integration is through HACS (Home Assistant Community Store):

1. Open Home Assistant
2. Navigate to HACS
3. Click on "Integrations"
4. Click the "+ Explore & Download Repositories" button
5. Search for "Unraid"
6. Click on "Unraid Integration"
7. Click "Download"
8. Restart Home Assistant

Alternatively, you can use this button to jump directly to the integration in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=ha-unraid&category=integration)

### Manual Installation

If you prefer to install the integration manually:

1. Download the latest release from the [GitHub repository](https://github.com/domalab/ha-unraid)
2. Extract the `custom_components/unraid` folder
3. Copy the folder to your Home Assistant's `custom_components` directory
4. Restart Home Assistant

## Configuration

After installation, you need to configure the integration:

1. In Home Assistant, navigate to **Configuration > Integrations**
2. Click the **+ ADD INTEGRATION** button
3. Search for and select "Unraid"
4. Follow the configuration steps:
   - Enter your Unraid server's IP address or hostname
   - Enter your username (usually "root")
   - Enter your password
   - Specify the SSH port (default is 22)
   - Set the update intervals

## Enabling SSH on Unraid

The integration uses SSH to communicate with your Unraid server. By default, SSH is disabled on Unraid. To enable it:

1. Log in to your Unraid dashboard
2. Go to **Settings > Management Access**
3. Under the SSH section, set "Enable SSH" to "Yes"
4. Set a strong password if you haven't already
5. Click "Apply"

## Troubleshooting

If you encounter issues during installation:

- Make sure SSH is enabled on your Unraid server
- Verify that the credentials are correct
- Check that the SSH port is open and accessible
- Ensure your Home Assistant can reach your Unraid server on your network

For more detailed troubleshooting, see the [Troubleshooting Guide](/content/troubleshooting). 