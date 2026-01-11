# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Migration from `configuration.yaml` to UI-based device creation and management

---

## [2.0.1] - 2025-09-18
### Added
- **Bulk Add**: Add multiple zones at once with a prefix and zone count.
- **Advanced Editor**: YAML/JSON source list editor with “Apply to all zones” option.
- **Friendly messages** in config flow for when channels/zones are already configured.
- Auto-suggest **first available channel** on re-renders.

### Changed
- `unique_id` format standardized as `{host}:{port}:ch{channel}`.
- Source list auto-inherits from existing zones on same amp unless overridden.

### Fixed
- Prevented form re-render unless amplifier size or bulk toggle changes.
- Correctly applies next available channel if chosen one is already configured.

---

## [2.0.1] - 2025-09-18
### Added
- Preparation for branding support
- Ability to install the integrations through HACS

---

## [2.0.2] - 2025-09-18
### Fixed
- Fixed version number in manifest to match version in [Releases](https://github.com/OtisPresley/control4-mediaplayer/releases)

---

## [2.0.3] - 2025-09-18
### Fixed
- Updated README

---

## [2.0.4] - 2025-09-19
### Changed
- Moved assets folder out of the integration directory structure
- Updated README to add badges and prepare for the official HACS repository

---

## [2.1.0] - 2025-09-19
### Changed
- Updated for first release on HACS repo

---

## [2.1.1] - 2025-09-19
### Changed
- Updated README badges

---

## [2.1.2] - 2025-09-20
### Changed
- Updated README badges
- Deleted local icons and logos

---

## [2.1.3] - 2025-09-20
### Fixed
- Fixed broken image links

---

## [2.1.4] - 2025-09-20
### Fixed
- Added missing config flow to manifest

---

## [2.1.5] - 2025-09-21
### Changed
- Updated README minor issues
- Added README acknowledgement

---

## [2.1.6 Beta 1] - 2025-09-22
### Added
- Added build validation with python

### Changed
- Updated README to adjust badges

### Fixed
- Cleaned up code in config flow

---

## [2.1.6] - 2025-09-24
### Added
- Added build validation with python

### Changed
- Updated README to adjust badges
- Moved .pre-commit-config.yaml to tests
- Updated .gitignore with more strings
- Updated ci.yaml to point to new location of requirements

### Fixed
- Cleaned up code in config flow

---

## [2.1.7] - 2026-01-10
### Fixed
- Corrected power button behavior not reflecting state correctly in HA

---

## [2.1.8] - 2026-01-11
### Fixed
- Corrected power button not maintaining state in HA
