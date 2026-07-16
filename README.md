# Virelo

A personal Windows desktop utility that snaps windows to configurable sizes and auto-sizes File Explorer columns.

## What It Does

Virelo provides two core features:

1. **Window Snap** -- A multi-press keyboard shortcut snaps the foreground window to a configurable size and position, centered on the current monitor. Press the shortcut again to restore the window to its original dimensions.

2. **Explorer Column Auto-Size** -- Automatically sizes File Explorer Detail view columns when navigating between folders, eliminating the need to manually adjust column widths.

## Requirements

- **Windows 10/11 x64 only** -- Virelo uses Win32 APIs, COM automation, and Windows-specific system features.
- **Administrator privileges** -- The application auto-elevates at launch via UAC prompt. Admin access is required for global keyboard hooks and window manipulation across processes.
- **Personal-use software** -- Built for the author's daily workflow. No telemetry, no accounts, no auto-updates.

## Build from Source

### Prerequisites

- Python 3.12+
- Node.js (for frontend build)
- Inno Setup 6 (only needed for the installer)

### Build Steps

```powershell
scripts/bootstrap.ps1        # Create .venv + install Python deps
scripts/build-frontend.ps1   # Build React frontend
scripts/build-app.ps1        # PyInstaller -> dist/Virelo/Virelo.exe
scripts/build-installer.ps1  # Inno Setup -> installer/dist/VireloSetup.exe
```

Each script validates its preconditions and fails early with a clear error message if a required tool is missing.

## Development Mode

Set the `VIRELO_DEV` environment variable, start the Vite dev server, then run the app:

```powershell
$env:VIRELO_DEV = 1
cd frontend
npm run dev
```

In a separate terminal:

```powershell
python main.py
```

The frontend hot-reloads from `localhost:5173`. Changes to React components appear immediately without restarting the Python backend.

## Architecture

Virelo uses a Python/PySide6 backend that hosts a React frontend inside a QWebEngineView. The two layers communicate through QWebChannel:

- **Python backend** -- Owns all OS-level logic: window management, keyboard hooks, COM automation, system tray, settings persistence (Windows Registry via QSettings).
- **React frontend** -- Renders the settings UI, theme controls, and command palette inside the embedded Chromium browser.
- **QWebChannel bridge** -- A single `VireloBridge` QObject is the sole communication channel. All data crosses the bridge as JSON strings.

In release mode, the frontend is built to static files (`frontend/dist/`) and loaded via `file://` URL. In dev mode, it connects to the Vite dev server.

## Documentation

- [Building from Source](docs/BUILD.md) -- Full build pipeline, development mode, version management
- [Troubleshooting](docs/TROUBLESHOOTING.md) -- Common build and runtime issues with fixes
- [Release Checklist](docs/RELEASE.md) -- Step-by-step release process

## Status

Under active development. Current version 1.5.0.

## License

[MIT](LICENSE)
