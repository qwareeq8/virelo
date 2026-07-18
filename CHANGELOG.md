# Changelog

All notable changes to Virelo are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog begins with the current 1.5.0 repository state. Earlier release history has not
been reconstructed from incomplete tags.

## [Unreleased]

### Added

- Added frontend linting and formatting checks, Python branch-coverage reporting, and focused
  regressions for the corrected desktop behavior.
- Added a reviewed native ARM64 Qt WebEngine capability contract and a non-mutating upstream wheel
  watcher.

### Changed

- Replaced the generic letter-tile identity with a snap-frame mark across the application,
  executable icon, and installer artwork.
- Improved keyboard navigation, status feedback, focus visibility, contrast, motion preferences,
  and native window-control ergonomics.

### Fixed

- Fixed frameless-window hit testing on mixed-DPI and negative-origin monitor layouts.
- Fixed the in-app snap test, post-fullscreen resizability detection, and second-launch handling.
- Fixed relative timing, capture-thread ownership, settings normalization, and shutdown cleanup.
- Prevented a lost WebChannel callback from permanently blocking later settings operations.
- Prevented concurrent release builds from deleting or replacing each other's generated payloads.

[Unreleased]: https://github.com/qwareeq8/Virelo/compare/v1.0...HEAD
