# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Support for future Control4 amp models.
- Placeholder for new features.

---

## [0.2.0] - 2025-09-18
### Added
- Migration from `configuration.yaml` to UI-based device creation and management
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

## [0.2.1] - 2025-09-01
### Added
- Preparation for branding support
- Ability to install the integrations through HACS

---

[Unreleased]: https://github.com/OtisPresley/control4-m edi aplayer/compare/0.2.0...HEAD
[0.2.0]: https://github.com/OtisPresley/control4-m edi aplayer/releases/tag/0.2.0
[0.2.1]: https://github.com/OtisPresley/control4-m edi aplayer/releases/tag/0.2.1
