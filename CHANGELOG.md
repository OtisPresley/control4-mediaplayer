# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.4] - 2026-07-02

### 🚀 Added
- 📦 **Embedded Lovelace Companion Card**: Bundled the `control4-mediaplayer-card` directly inside the integration repo, serving it on startup and automatically registering it as a Lovelace resource (for storage dashboards).

### 🔧 Fixed
- 🌐 **LovelaceData Attribute Compatibility**: Fixed startup failure on Home Assistant 2026.2+ by checking for both `resource_mode` and `mode` attributes.
- ⚙️ **Event Loop Safety (Non-blocking I/O)**: Moved the `manifest.json` file read to Home Assistant's executor thread pool to prevent blocking the async event loop.
- 🧪 **Testing Environment Backward Compatibility**: Conditionally import `StaticPathConfig` and fall back to synchronous static path registration to support unit testing suites executing under older HA environments (like `homeassistant==2023.7.3`).

---

## [2.3.3] - 2026-06-09

### 🔧 Fixed
- 🔇 **Speaker Startup Volume Blast (eliminated)**: Switched to **software-only** volume capping. The hardware max-volume limit command (`c4.amp.chvolmax`) is no longer sent to the physical amplifier under any circumstances. Every time this command was dispatched — even while the zone was silent — the amplifier's internal playback register was being overwritten with the maximum limit, causing an audible blast on the next turn-on. All capping is now enforced purely in Home Assistant software via `chvol`, which is safe and reliable in all conditions.

---

## [2.3.3-beta.3] - 2026-06-08

### 🔧 Fixed
- 🔇 **Speaker Startup Volume Blast (eliminated)**: Switched to **software-only** volume capping. The hardware max-volume limit command (`c4.amp.chvolmax`) is no longer sent to the physical amplifier under any circumstances. Every time this command was dispatched — even while the zone was silent — the amplifier's internal playback register was being overwritten with the maximum limit, causing an audible blast on the next turn-on. All capping is now enforced purely in Home Assistant software via `chvol`, which is safe and reliable in all conditions.

---

## [2.3.3-beta.2] - 2026-06-07

### 🔧 Fixed
- 🔊 **Speaker Startup Volume Blast (sub-second)**: Corrected the command order in the zone turn-on sequence. The play volume (`chvol`) is now written to the amplifier's register *before* the power-save wake command (`psave`) is sent. This ensures the volume register is already at the correct level the instant the amp resumes routing audio, eliminating the remaining sub-second blast at startup.

---

## [2.3.3-beta.1] - 2026-06-05

### 🔧 Fixed
- 🔊 **Speaker Startup Volume Blast**: Restructured maximum volume synchronization logic (`chvolmax`). The limit is now only sent to the physical hardware during silent/inactive states (when the zone is powered off, or when adjusting the slider while the zone is off). This prevents the physical amplifier from forcing the playback register to the maximum during turn-on transitions.

---

## [2.3.2] - 2026-06-01

### 🚀 Added
- 🎛️ **Optional Per-Zone EQ Controls**: Treble, Bass, and Balance can now be exposed directly as `Number` entities in your Home Assistant dashboards. You can toggle this on or off in the Options Flow.
- 🧹 **Programmatic Orphan EQ Cleanup**: Toggling EQ controls to **OFF** now programmatically removes the entities from Home Assistant's Entity Registry instantly, preventing "unavailable" placeholders.
- 💾 **State Persistence (State & Settings)**: Switch from options-flow storage to Home Assistant's native state-restoration (`RestoreNumber` and `RestoreEntity`). Active player states (on/off, volume, active input source, mute) and configuration sliders are perfectly preserved across Home Assistant reboots.

### ⚡ Optimized
- ⚡ **Instant Command Execution**: Eliminated the legacy 2.0-second delay on network commands by matching UDP responses against the amplifier's response prefix. Commands now execute instantly in ~1–2ms.
- 🧹 **Full DRY Codebase Optimization**: Centralized all display name and unique ID formatting into unified, robust helpers (`PREFIX`, `get_unique_id`, `get_entity_name`), eliminating redundant class repetitions.
- 📦 **Consolidated EQ Architecture**: Replaced separate treble, bass, and balance subclasses with a single, highly maintainable generic `C4EQNumber` platform class.

### 🔧 Fixed
- 🔄 **Reload-Free Audio Adjustments**: Switched persistence off of `config_entries.data` modifications, completely resolving the bug where moving any audio slider (Max Volume, Treble, Bass, Balance) triggered integration reloads and turned active zones off.
- 🔊 **Glitch-Free Software Max Volume Capping**: Capped volumes in software during playback and synchronized hardware caps (`chvolmax`) only during silent transitions (turning on or off). This completely eliminates transient volume spikes/jumps to max when moving the ceiling slider.
- 🔄 **Uninterrupted Bootups**: Restoring media player states on HA reboot is now 100% passive, ensuring your background audio playback continues completely uninterrupted when Home Assistant restarts.
- 🔊 **Fallback-Enabled Native Muting**: Native mute commands are attempted first, falling back to volume-based mute if the physical hardware does not support it.

---

## [2.3.1] - 2026-05-25

### 🚀 Added
- 🔊 **UDP timeout setting**: Thanks @Hansen8601 for adding an option to adjust the UDP timeout.

---

## [2.3.1-beta.1] - 2026-05-25

### 🚀 Added
- 🔊 **UDP timeout setting**: Thanks @Hansen8601 for adding an option to adjust the UDP timeout.

---

## [2.3.0] - 2026-05-16

### 🚀 Added
- 🔊 **Max Volume Entities**: Added `C4MaxVolumeNumber` entities to set volume ceilings per zone.
- 🎛️ **Input Gain Configuration**: Added input gain trim configuration in the options flow to balance sources.
- 🛠️ **New Services**: Added `party_mode` (sync all zones) and `send_raw_command` (send hex strings directly) services!
- 🎨 **Companion Card**: Released the [Control4 Media Player Card](https://github.com/OtisPresley/control4-mediaplayer-card) for a gorgeous, source-centric UI!

### 🔄 Changed
- 🔒 **Safe Transport Protocol**: Re-engineered UDP communication to use random sequencers and active acknowledgement polling, ensuring commands are delivered and matched correctly!
- 🧹 **Codebase Clean-up**: Stripped out unsupported and dead code to ensure maximum reliability on legacy firmware.

---

## [2.0.1] - 2025-09-18
### 🚀 Added
- **Bulk Add**: Add multiple zones at once with a prefix and zone count.
- **Advanced Editor**: YAML/JSON source list editor with “Apply to all zones” option.
- **Friendly messages** in config flow for when channels/zones are already configured.
- Auto-suggest **first available channel** on re-renders.

### 🔄 Changed
- `unique_id` format standardized as `{host}:{port}:ch{channel}`.
- Source list auto-inherits from existing zones on same amp unless overridden.

### 🐛 Fixed
- Prevented form re-render unless amplifier size or bulk toggle changes.
- Correctly applies next available channel if chosen one is already configured.

---

## [2.0.1] - 2025-09-18
### 🚀 Added
- Preparation for branding support
- Ability to install the integrations through HACS

---

## [2.0.2] - 2025-09-18
### 🐛 Fixed
- Fixed version number in manifest to match version in [Releases](https://github.com/OtisPresley/control4-mediaplayer/releases)

---

## [2.0.3] - 2025-09-18
### 🐛 Fixed
- Updated README

---

## [2.0.4] - 2025-09-19
### 🔄 Changed
- Moved assets folder out of the integration directory structure
- Updated README to add badges and prepare for the official HACS repository

---

## [2.1.0] - 2025-09-19
### 🔄 Changed
- Updated for first release on HACS repo

---

## [2.1.1] - 2025-09-19
### 🔄 Changed
- Updated README badges

---

## [2.1.2] - 2025-09-20
### 🔄 Changed
- Updated README badges
- Deleted local icons and logos

---

## [2.1.3] - 2025-09-20
### 🐛 Fixed
- Fixed broken image links

---

## [2.1.4] - 2025-09-20
### 🐛 Fixed
- Added missing config flow to manifest

---

## [2.1.5] - 2025-09-21
### 🔄 Changed
- Updated README minor issues
- Added README acknowledgement

---

## [2.1.6 Beta 1] - 2025-09-22
### 🚀 Added
- Added build validation with python

### 🔄 Changed
- Updated README to adjust badges

### 🐛 Fixed
- Cleaned up code in config flow

---

## [2.1.6] - 2025-09-24
### 🚀 Added
- Added build validation with python

### 🔄 Changed
- Updated README to adjust badges
- Moved .pre-commit-config.yaml to tests
- Updated .gitignore with more strings
- Updated ci.yaml to point to new location of requirements

### 🐛 Fixed
- Cleaned up code in config flow

---

## [2.1.7] - 2026-01-10
### 🐛 Fixed
- Corrected power button behavior not reflecting state correctly in HA

---

## [2.1.8] - 2026-01-11
### 🐛 Fixed
- Corrected power button not maintaining state in HA

---

## [2.1.9-beta.1] - 2026-01-11
### 🚀 Added
- **External State Polling** per zone:
  - Creates additiona timer-based polling on a per-zone basis
  - Allows customization of the Polling interval between 1 and 300 seconds
  - Good for those who also control the Amp with a Control4 Controller

---

## [2.1.9-beta.4] - 2026-01-17
### 🐛 Fixed
- Polling was not actually firing

---

## [2.2.0] - 2026-05-05

### ⚠️ BREAKING CHANGES
* **Entity Naming & Registry Management**: Transitioned to a versioned registry to support consolidated device grouping. Existing entities from versions 2.1.8 and below will be purged from the registry to prevent "ghost" devices and naming conflicts.
* **Configuration Method**: Manual setup via `configuration.yaml` is no longer supported. All users must migrate to the UI-based configuration via **Settings > Devices & Services**.

### 🚀 Added
* **Power On Volume**: Added a per-zone configuration option to set a specific volume level (0-100%) when the zone is turned on.
* **Bulk Input Sync**: New "Copy input list to all zones" checkbox in the options menu allows users to synchronize source names across all zones instantly.
* **Options Update Listener**: Added a dynamic listener that reloads the integration immediately upon saving changes in the configuration dialog, ensuring names and inputs reflect instantly.
* **Enhanced UI Labels**: Updated `strings.json` and translations to provide clear descriptions for all new configuration fields.

### 🔄 Changed
* **Standalone Options Flow**: Refactored the configuration handler into a standalone `OptionsFlowHandler` class to resolve 500 Internal Server Errors and improve stability.
* **Unique ID Synchronization**: Standardized the unique ID format (`v27_{host}_ch{channel}`) across the entire integration for better reliability in the Home Assistant entity registry.
