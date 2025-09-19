**# Control 4 Matrix Amp [[Home Assistant](https://www.home-assistant.io/) Component]

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Validate with hassfest](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hassfest.yaml/badge.svg)
![Validate with HACS](https://github.com/OtisPresley/control4-mediaplayer/actions/workflows/hacs.yaml/badge.svg)

Control4 multi-zone amplifier/media player integration for [Home Assistant](https://www.home-assistant.io/).  
Features a full **Config Flow** (UI), **Bulk Add**, **per-zone unique IDs**, and an **Advanced Editor** for source lists (YAML/JSON).

---

## Highlights
- Add zones from **Settings → Devices & Services → Add Integration → Control4 Media Player**.
- **Unique IDs** per zone: `host:port:chN` → devices/entities are managed in the UI.
- **Bulk Add** with one-pass naming and channel selection.
- **First available channel** auto-suggested on form re-renders.
- Friendly messages (include `host:port`):
  - “All zones are already configured for `host:port`.”
  - “Channel X is already configured on `host:port`. Next available is Y.”
- **Options Flow** for On Volume + Source List, with:
  - Simple editor (comma/newline separated)
  - **Advanced Editor** (YAML/JSON textarea) + “Apply to all zones on this device”

---

## Installation

### HACS (recommended)
1. In Home Assistant, open **HACS → Integrations**.
2. Click the ⋮ menu → **Custom repositories**.
3. Add this repository URL: https://github.com/OtisPresley/control4-mediaplayer

Category: **Integration**
4. Install **Control4 Media Player** from HACS.
5. Restart Home Assistant.

### Manual install
1. Copy the folder `custom_components/control4_mediaplayer` to your HA `config/custom_components` directory.
2. Restart Home Assistant.

> No `configuration.yaml` entries are required. Remove any legacy YAML entries after migrating to the UI.

---

## Adding a Single Zone
1. **Name**: Friendly name for the zone (e.g., “Great Room”).
2. **Host / Port**: IP of your Control4 amp and UDP port (default `8750`).
3. **Amplifier Size**: `4` or `8` → bounds **Channel** and caps **Source List** size.
4. **Channel**: Required, bounded by amplifier size.  
- If a channel is already in use, the form re-shows with the **next available** channel pre-selected.
5. **On Volume**: 0–100 (default from integration).
6. **Source List**: Comma/newline separated.  
Defaults to `1..N` based on amp size, or inherits from another zone on the same amp.

---

## Bulk Add (Add Zones in Bulk)
1. Toggle **Add Zones in Bulk** and **Submit** once → the form re-renders showing:
- **Zone Prefix (bulk)**
- **Zone Count (bulk)** (bounded by remaining free channels)
2. If all zones are already configured for that `host:port`, the flow immediately shows:  
**“All zones are already configured for host:port.”**
3. After submit, you’ll get a second screen to **enter a unique name per channel** (prefilled using the prefix).

---

## Editing Options (per zone)
- **Simple Editor**
- **On Volume**: 0–100
- **Source List**: comma/newline separated (auto-normalized)
- **Apply to All Zones on This Device**: propagate the Source List to other zones with the same `host:port`.
- **Advanced Editor (YAML/JSON)**
- Multiline textarea
- Accepts YAML **or** JSON
- Example:
 ```yaml
 - HC800-1
 - HC800-2
 - Server
 - Home Assistant
 ```
- Parse errors keep you on the page with a friendly message + inline example.

---

## Behavior Notes & Guardrails
- **Form re-render** happens only when:
- **Amplifier Size** changes, or
- **Add Zones in Bulk** is toggled  
(Channel/Host/Port validations still happen on submit.)
- **Channel** is clamped to `1..AmpSize`; **Zone Count** is clamped to available channels.
- **Source List** longer than Amp Size is truncated to Amp Size.
- When editing/adding on the same `host:port`, the **Source List** auto-inherits from an existing zone unless overridden.

---

## Troubleshooting
- **All zones are already configured for host:port.**  
You’ve used all channels for the selected Amp Size.
- **Channel X is already configured on host:port. Next available is Y.**  
Pick Y or another free channel.
- **Channel must be between 1 and N.**  
Adjust the channel or set the correct Amp Size first.
- **Fields don’t appear until after I toggle “Add Zones in Bulk”.**  
Expected: HA forms re-render after you press **Submit** once.
- After updating code, bump `"version"` in `manifest.json` and restart HA.
- If the UI looks stale, hard-refresh your browser (Shift+F5).

---

## Migration from `configuration.yaml`
- YAML platform entries are no longer needed.
- UI-based entries create **unique IDs** and persist your devices/entities in the registry.
- Remove legacy YAML lines to avoid duplication.

---

## Known Limitations
- No automatic network discovery (Control4 protocol behavior without a controller is limited).
- The form can’t live-update fields without submit; we use a minimal “soft refresh” pattern.

---

## Development Notes
- Domain: `control4_mediaplayer`
- User-facing strings are **hard-coded** in `config_flow.py` (translations proved unreliable).
- Advanced editor parsing via `yaml.safe_load` (accepts JSON too). Non-list/str → friendly parse error.
- Unique ID format: `"{host}:{port}:ch{channel}"`

---

## Changelog (UI series)
- Bulk Add with per-channel naming, first-available channel suggestion
- Friendly host:port messages
- Advanced Editor (YAML/JSON) + apply-to-all
- Source List inheritance per device
- Re-render only on Amp Size / Bulk toggle

---

## Acknowledgements

This integration is a fork of the original [control4-mediaplayer](https://github.com/Hansen8601/control4-mediaplayer) by [@Hansen8601](https://github.com/Hansen8601).  
Huge thanks to their initial work building the foundation that made this project possible.  
This fork expands on the original with config flow (UI), bulk add, advanced source editing, and other enhancements.

---

#### [@Hansen8601](https://github.com/Hansen8601) Home Assistant Card
![MyCard](https://github.com/Hansen8601/control4-mediaplayer/blob/f7d66aa66f89b2b0bcf36ea5393bb76a07da0f32/Control4AmpCard.png)

---

## Support
- [Open an issue](https://github.com/OtisPresley/control4-mediaplayer/issues) if you find a bug.
- Contributions via PRs are welcome.

---

## License
This project is licensed under the terms of the [MIT license](LICENSE).
