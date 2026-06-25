# Control4 Media Player: Home Assistant Custom Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?logo=home-assistant&logoColor=white&style=flat)](https://www.home-assistant.io/)
[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![HA installs](https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.control4_mediaplayer.total&label=Installs&color=41BDF5)](https://analytics.home-assistant.io/custom_integrations.json)
[![License: MIT](https://img.shields.io/badge/nse-MIT-e0b416.svg)](https://github.com/OtisPresley/control4-mediaplayer/blob/main/LICENSE)
[![hassfest](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/hassfest.yaml?branch=main&label=hassfest)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hassfest.yaml)
[![HACS](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/hacs.yaml?branch=main&label=HACS)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hacs.yaml)
[![CI](https://img.shields.io/github/actions/workflow/status/OtisPresley/control4-mediaplayer/ci.yaml?branch=main&event=push)](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/ci.yaml)

Control4 Matrix Amplifier custom integration for [Home Assistant](https://www.home-assistant.io/).  
This integration allows you to use your matrix amplifier without a Control4 Controller and turn its physical audio channels/zones into premium `media_player` entities in Home Assistant.

---

## Table of Contents
- [Highlights](#highlights)
- [Installation](#installation)
  - [HACS (Recommended)](#hacs-recommended)
  - [Manual Install](#manual-install)
- [How It Works (Under the Hood)](#how-it-works-under-the-hood)
  - [Instant UDP Command Engine](#1-instant-udp-command-engine)
  - [Passive State & Volume Restoration](#2-passive-state--volume-restoration)
  - [Glitch-Free Software Max Volume Capping](#3-glitch-free-software-max-volume-capping)
  - [Hardware-Fallback Native Muting](#4-hardware-fallback-native-muting)
  - [Dynamic EQ Control Sliders](#5-dynamic-eq-control-sliders)
- [Configuration & Usage](#configuration--usage)
  - [Initial Setup](#initial-setup)
  - [Managing Zone Options](#managing-zone-options-options-flow)
- [Custom Lovelace Companion Card](#custom-lovelace-companion-card)
- [Services](#services)
  - [`party_mode`](#party_mode)
  - [`send_raw_command`](#send_raw_command)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Highlights

* 🚀 **Instant UDP Command Execution**: Matched UDP responses in 1-2ms, eliminating the legacy 2.0s delays!
* 🎛️ **Optional Per-Zone EQ Sliders**: Dynamically control Treble, Bass, and Balance directly from your dashboard!
* 💾 **Bulletproof State Persistence**: Full support for Home Assistant's `RestoreEntity` and `RestoreNumber` engines. All configuration sliders and player states are perfectly preserved across HA reboots without active playback interruptions.
* 🔄 **Reload-Free Audio Adjustments**: Make adjustments to limits and EQ settings instantly without integration reloads or active zones shutting down.
* 🔊 **Glitch-Free Volume Capping**: Software-enforced volume capping during playback completely eliminates transient spikes to max volume.
* 🧹 **Automatic Registry Cleaner**: Purges orphan and ghost entities programmatically when EQ settings are disabled or upgraded.

---

## Installation

### HACS (recommended)
You can install this integration directly from HACS:

[![Open your Home Assistant instance and show the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OtisPresley&repository=control4-mediaplayer)

After installation, restart Home Assistant and add the integration:

[![Open your Home Assistant instance and add this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=control4_mediaplayer)

#### Manual HACS steps:
1. In Home Assistant, open **HACS → Integrations**.  
2. Click **Explore & Download Repositories**, search for **Control4 Media Player**, then click **Download**.  
3. **Restart Home Assistant**.  
4. Go to **Settings → Devices & Services → Add Integration → Control4 Media Player**.  

### Manual install
1. Copy the `custom_components/control4_mediaplayer` folder to your config `custom_components` directory.
2. **Restart Home Assistant**.
3. Navigate to **Settings > Devices & Services > Add Integration** and search for "Control4 Media Player".
> [!WARNING]
> Manual setup in `configuration.yaml` is not supported. All configuration must be completed through the Home Assistant dashboard.

---

## How It Works (Under the Hood)

This integration is engineered specifically to extract maximum performance from the Control4 Matrix Amplifier's serial-over-UDP protocol.

### 1. Instant UDP Command Engine
Legacy integrations suffered from a mandatory 2.0-second delay per network command due to active socket polling. This integration utilizes a **Prefix Response Matching** algorithm. When Home Assistant sends a command (`0s2aXX...`), it generates a matching response prefix (`0r2aXX...`). The UDP receiver instantly intercepts and matches the corresponding amplifier response.
* **Result**: Latency is reduced from 2,000ms to **1–2ms** per command, offering instantaneous response times when adjusting sliders, muting, or switching sources.

### 2. Passive State & Volume Restoration
Rebooting Home Assistant can often disrupt active audio playback. We resolved this by inheriting from Home Assistant's native **`RestoreEntity`** and **`RestoreNumber`** engines.
* **Passive Boot**: During startup, the integration performs a completely silent restoration of player states, source selections, volume levels, mute states, and ceilings in memory. 
* **Zero Command Boot**: No physical power, volume, or routing commands are sent to the hardware during startup. If you restart Home Assistant while the physical amplifier is actively playing in the background, your audio plays **completely uninterrupted** and the HA UI gracefully loads to reflect correct states.

### 3. Glitch-Free Software Max Volume Capping
The Control4 Matrix Amplifier's hardware-level limit command `c4.amp.chvolmax` has a firmware bug: receiving the command instantly sets the zone's active playback volume to that ceiling value.
* **Enforced in Software**: To prevent this volume spike, adjusting the **Max Volume** slider now strictly and silently updates the limit inside Home Assistant's software memory. If the current playback volume exceeds the new cap, it immediately sends a smooth, capped volume update (`chvol`) to lower the active playback volume. No hardware `chvolmax` command is ever sent during slider adjustments.
* **Silent Transition Syncing**: The hardware limit `chvolmax` is safely and silently synchronized to the physical amplifier only when the zone is quiet (during `async_turn_on()` and `async_turn_off()` transitions), ensuring the hardware and software limits remain perfectly aligned.

### 4. Hardware-Fallback Native Muting
To offer the cleanest audio cut, the integration uses a two-tiered muting system:
1. **Native Muting**: Sends `c4.amp.mute {channel} 01` (mute) or `00` (unmute).
2. **Software Fallback**: If the physical amplifier returns an unsupported error (`n01`) or times out, the integration automatically falls back to volume-based muting, instantly setting the hardware channel volume to 0% (hex value `9b`) and restoring it to the previous active level upon unmuting.

### 5. Dynamic EQ Control Sliders
When toggled on in the Options Flow, three `Number` entities are generated per zone:
* 🔊 **Treble Slider**: `-12dB` to `+12dB` range.
* 🔊 **Bass Slider**: `-12dB` to `+12dB` range.
* 🔊 **Balance Slider**: `-10` (Left) to `+10` (Right) range (where `0` is center).

#### Hardware Protocol Mechanics:
The Control4 Matrix Amplifier expects EQ values as standard **8-bit signed two's complement hex bytes** (e.g., `-5` -> `fb`, `3` -> `03`, `0` -> `00`). The integration translates these ranges automatically on the fly. 

If EQ controls are toggled **OFF**, the integration automatically contacts Home Assistant's `entity_registry` and programmatically purges them from the database, preventing ugly, ghost "unavailable" entities from cluttering your dashboard. Since the settings are saved on the physical hardware chips, whatever values you set will persist perfectly!

---

## Configuration & Usage

### Initial Setup
1. Navigate to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **Control4 Media Player**.
3. Provide the **IP Address** and **Port** (default `8750`) of your Control4 Matrix Amplifier.
4. Provide an optional custom name for your amplifier (e.g., "Main Amplifier").
5. On the second screen, name the physical zone connected to that config flow channel (e.g., "Living Room").

> [!NOTE]
> Each physical zone/channel on the amplifier is configured as an individual config entry in Home Assistant. This is a design requirement that allows Home Assistant to display a dedicated **Configure** button per zone.

### Managing Zone Options (Options Flow)
Click the **Configure** button on any of your zone cards to fine-tune its behavior:

| Setting Option | Description |
|---|---|
| **Zone Name** | Custom display name for the media player and entities. |
| **Power On Volume** | The startup volume percentage (0-100%) when turned on. |
| **Source List** | Input source names (one per line, e.g. `Spotify`, `Apple TV`, `Sonos`). |
| **Input Gain Offsets** | Trim values to balance different audio sources (one per line, e.g. `Input1: +2`). |
| **Enable EQ Controls** | Check this box to dynamically expose Treble, Bass, and Balance sliders. |
| **Copy to all zones** | Check this to instantly copy your current source list, input gains, and EQ toggle configuration to all other zones on this amplifier, saving you from repeating configuration screens! |

---

## Custom Lovelace Companion Card

To get the absolute best visual experience, pair this integration with the custom source-centric card designed specifically for it.

👉 **Install**: [Control4 Media Player Lovelace Card](https://github.com/OtisPresley/control4-mediaplayer-card)

<img width="796" height="534" alt="image" src="https://github.com/user-attachments/assets/a6865404-f68b-4eb2-98fd-964b19a646da" alt="Screenshot" width="320"/>

---

## Services

This integration exposes two highly powerful services to handle system-wide syncs and raw custom integrations.

### `party_mode`
Synchronizes all active zones on your amplifier to a single target input source and volume level instantly.
* **Service ID**: `control4_mediaplayer.party_mode`
* **Parameters**:
  * `source` *(Required)*: The exact source name to route (e.g., `Spotify`).
  * `volume` *(Optional)*: The master volume level (0-100%, default `50`).

### `send_raw_command`
Sends custom hex strings directly over UDP to target zones or the system. This is a bulletproof developer tool to integrate raw custom serial commands.
* **Service ID**: `control4_mediaplayer.send_raw_command`
* **Parameters**:
  * `command` *(Required)*: The exact UDP raw string command (e.g., `c4.amp.trebgain 01 03`).
  * `entity_id` *(Required)*: The target `media_player` or `number` entity ID to identify the correct manager.

---

## Troubleshooting

### Entities are Showing "Unavailable"
* If you recently upgraded from an older version (v26 or below), the versioned registry janitor will clean up outdated entities to prevent database corruption. Simply re-add the integration via the integrations dashboard.
* If you disabled **EQ Controls** in the Options flow, they are programmatically removed from the registry. This is expected behavior to keep your dashboard clean.

### Command Latency or Physical Device Not Responding
* Double-check that your Home Assistant host can reach your amplifier's IP address on Port `8750`.
* Check the Home Assistant logs under **Settings > System > Logs** (search for `control4_mediaplayer`). The prefix acknowledgement system will log any timed out packets.
* Verify the **UDP Timeout** setting in the Options Flow. A congested local network may require raising the timeout slightly (e.g., to `3.0` seconds).

---

## Known Limitations

* **No Physical State Feedback**: The Control4 Matrix Amplifier does not stream physical state updates back over UDP. Home Assistant manages an "assumed state." If you adjust the volume using a separate, physical Control4 keypad or physical controller, Home Assistant's UI will not reflect that adjustment until a command is sent from HA.
* **UI Config Only**: Setup via `configuration.yaml` is not supported.

---

## Acknowledgements
This integration is a fork of the original [control4-mediaplayer](https://github.com/Hansen8601/control4-mediaplayer) by [@Hansen8601](https://github.com/Hansen8601) and is built upon the foundational work of [@kmakar89](https://github.com/kmakar89).  
Special thanks to their their initial work creating the network communications base that made this project possible.

---

## License
This project is licensed under the terms of the [MIT license](LICENSE).
