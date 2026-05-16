# Control4 Media Player: Home Assistant Custom Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?logo=home-assistant&logoColor=white&style=flat)](https://www.home-assistant.io/)
[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![HA installs](https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.control4_mediaplayer.total&label=Installs&color=41BDF5)](https://analytics.home-assistant.io/custom_integrations.json)
[![License: MIT](https://raw.githubusercontent.com/otispresley/control4-mediaplayer/main/assets/license-mit.svg)](https://github.com/OtisPresley/control4-mediaplayer/blob/main/LICENSE)
[![hassfest](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/hassfest.yaml?branch=main&label=hassfest)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hassfest.yaml)
[![HACS](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/hacs.yaml?branch=main&label=HACS)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hacs.yaml)
[![CI](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/ci.yaml?branch=main&event=push)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/ci.yaml)

Control4 Matrix Amplifier integration for [Home Assistant](https://www.home-assistant.io/).  
This integration alllows you to use your amplifier without a Control4 Controller and turn the channel/zones into media players in Home Assistant.

---

## Table of Contents
- [Highlights](#highlights)
- [Installation](#installation)
  - [HACS (recommended)](#hacs-recommended)
  - [Manual Install](#manual-install)
- [Migrating from configuration.yaml](#migrating-from-configurationyaml)
- [Configuration](#configuration)
  - [Adding a Single Zone](#adding-a-single-zone)
  - [Bulk Add (Add Zones in Bulk)](#bulk-add-add-zones-in-bulk)
  - [Editing Options](#editing-options-per-zone)
- [Behavior Notes & Guardrails](#behavior-notes--guardrails)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Changelog](https://github.com/OtisPresley/control4-mediaplayer/blob/main/CHANGELOG.md)
- [Acknowledgements](#acknowledgements)
- [Support](#support)
- [License](#license)

---

## Features
* **Unified Device Management**: All 8 zones are grouped under a single "Matrix Amp" device for a cleaner UI.
* **Custom Lovelace Card**: Designed to pair perfectly with the [Control4 Media Player Card](https://github.com/OtisPresley/control4-mediaplayer-card) for a gorgeous, source-centric UI!
* **Per-Zone Configuration**: Customize names and settings for each zone independently.
* **Power-On Volume**: Set a specific volume level (0-100%) that the zone will automatically jump to when turned on.
* **Bulk Input Sync**: Update input names once and sync them to all 8 zones instantly with a single checkbox.
* **Automatic Registry Cleanup**: Modern v27 architecture ensures old "ghost" entities are purged during updates.

<p float="left">
  <img width="500" alt="image" src="https://github.com/user-attachments/assets/0052a65d-e13d-4a90-9551-1bf9f8ac21c1" />
  <img width="500" alt="image" src="https://github.com/user-attachments/assets/cf06c11a-d051-444c-86b4-e5e3d185b0ee" />
</p>

---

## Installation

### HACS (recommended)
You can install this integration directly from HACS:

[![Open your Home Assistant instance and show the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OtisPresley&repository=control4-mediaplayer)

After installation, restart Home Assistant and add the integration:

[![Open your Home Assistant instance and add this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=control4_mediaplayer)

---

#### Manual steps (if you prefer not to use the buttons)
1. In Home Assistant, open **HACS → Integrations**.  
2. Click **Explore & Download Repositories**, search for **Control4 Media Player**, then click **Download**.  
3. **Restart Home Assistant**.  
4. Go to **Settings → Devices & Services → Add Integration → Control4 Media Player**.  

### Manual install
1. Copy the `control4_mediaplayer` folder to your `custom_components` directory.
2. Restart Home Assistant.
3. ⚠️ This integration is configured via the UI. Manual setup in `configuration.yaml` is not supported.
4. Navigate to **Settings > Devices & Services > Add Integration** and search for "Control4 Media Player".
---

## Configuration & Usage

### Initial Setup
1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **Control4 Media Player**.
3. Provide the IP Address and Port (default 8750).
4. Name your amplifier and define your initial input list.
5. On the second screen, name each of your zones (e.g., "Kitchen", "Patio").

### Managing Zone Options
Once installed, you can tune each zone by clicking the **Configure** button on the integration card:
* **Zone Name**: Change the display name for that specific zone.
* **Power On Volume**: Define the startup volume level.
* **Source List**: Edit your input names.
* **Sync to All**: Check **"Copy input list to all zones"** to push your current source names to every other zone on the amplifier automatically.

---

## Behavior Notes & Guardrails

* **Versioned Registry**: This integration uses a versioned unique ID system. When you upgrade or re-add the integration, it automatically purges old, orphaned entities from your Home Assistant registry to prevent "ghost" devices.
* **Power-On Sequence**: Turning on a zone triggers a two-step UDP command: first, it sends a wake-up call to the amplifier's power-save system; second, it sets the zone to the designated Power On Volume and Source.
* **Volume Mapping**: Volume levels in Home Assistant (0.0 to 1.0) are mapped to the Control4 hex scale with a protocol-required offset of 155. 
* **State Synchronization**: Because the Control4 Matrix Amp does not provide a feedback state via UDP, Home Assistant manages the "assumed state". Clicking "Submit" in the Options menu will force a reload of the entity to ensure the UI reflects your latest settings.
* **Bulk Updates**: Using the "Copy to all zones" feature will overwrite the `source_list` on all 8 entries but will *not* change their individual names or power-on volume settings.

Example Dashboard Cards:

<img src="https://raw.githubusercontent.com/otispresley/control4-mediaplayer/main/assets/screenshot4.png" alt="Screenshot 4" width="300"/>

---

## Troubleshooting

* **Integration won't load/500 Error**: Ensure you have restarted Home Assistant after copying the files. The v27 architecture requires a clean boot to register the Options Flow handler.
* **Entities missing after update**: If you previously used an older version (v26 or below), the v27 janitor logic in `__init__.py` will purge those entities to prevent registry corruption. Simply re-add the integration via the UI.
* **Commands not responding**: Verify the IP address and Port (default 8750) are correct in your configuration. The integration uses one-way UDP; if the IP is wrong, Home Assistant will show the device as "On," but the physical amplifier will not react.
* **Config changes not reflecting**: If names or inputs don't update instantly, ensure the `update_listener` is active. A single restart after the first installation usually resolves this.

---

## Known Limitations

* **No State Feedback**: The Control4 Matrix Amp does not send status updates back over UDP. Home Assistant maintains an "assumed state." If you manually change a zone using a physical Control4 keypad, Home Assistant will not reflect that change.
* **UDP Reliability**: As UDP is a connectionless protocol, commands can occasionally be dropped if your network is congested. The integration uses random counters to help the amp distinguish between unique commands.
* **UI Only**: Configuration via `configuration.yaml` is not supported. All setup and zone adjustments must be done through the Home Assistant Integrations dashboard.
* **Single Device Logic**: While all zones appear on a single device page, they are technically individual config entries. This is required to allow the "Configure" button to work for each specific zone.

---

## Acknowledgements
This integration is a fork of the original [control4-mediaplayer](https://github.com/Hansen8601/control4-mediaplayer) by [@Hansen8601](https://github.com/Hansen8601) and based off the work of [@kmakar89](https://github.com/kmakar89).  
Huge thanks to their initial work building the foundation that made this project possible.  
This fork expands with config flow (UI), bulk add, advanced source editing, and other enhancements.

---

## Support
- [Open an issue](https://github.com/OtisPresley/control4-mediaplayer/issues) if you find a bug.
- Contributions via PRs are welcome.

If you find this integration useful and want to support development, you can:

[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-orange)](https://www.buymeacoffee.com/OtisPresley)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/OtisPresley)

---

## License
This project is licensed under the terms of the [MIT license](LICENSE).
