# Virelo

A personal Windows desktop utility that snaps windows to configurable sizes and autosizes File
Explorer columns.

## What It Does

Virelo provides two core features:

1. **Window Snap:** A multi-press keyboard shortcut snaps the foreground window to a configurable
   size and position, centered on the current monitor. Windows that cannot resize cleanly are
   centered at their current size. Press the shortcut again to restore the window to its original
   dimensions.

2. **Explorer Column Autosize:** Automatically sizes File Explorer Details-view columns when
   navigating between folders, eliminating the need to adjust column widths manually.

## Requirements

- **Windows 10 version 1809 or later on x64, or Windows 11 ARM64 with x64 application
  emulation:** Virelo currently ships a verified x64 payload. Native ARM64 packaging is blocked
  because the published Windows ARM64 PySide6 wheels omit the Qt WebEngine components Virelo
  requires.
- **Administrator privileges:** The application auto-elevates at launch through a UAC prompt.
  Administrator access is required for global keyboard hooks and cross-process window
  manipulation.
- **Personal-use software:** Virelo is built for the author's daily workflow. It has no telemetry,
  accounts, or automatic updates.

## Build from Source

### Prerequisites

- Official x64 CPython 3.12 or newer.
- x64 Node.js 24 LTS.
- Inno Setup 6.7.3, which is needed only for the installer.

Do not use a Conda or Miniforge interpreter for a release build. A virtual environment retains
the interpreter architecture and distribution that created it.

### x64 Build

```powershell
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\build-installer.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\verify-release.ps1 -Architecture x64
```

The bundle is written to `dist/x64/Virelo/`, and the installer is written to
`installer/dist/VireloSetup-<version>-x64.exe`.

### Native ARM64 Status

Virelo does not currently produce a native ARM64 bundle or installer. The published Windows ARM64
PySide6 and PySide6-Addons wheels omit `QtWebEngineCore`, `QtWebEngineWidgets`,
`QtWebEngineProcess.exe`, and the WebEngine resources required by Virelo's embedded frontend. Use
the verified x64 installer on Windows 11 ARM64 through x64 emulation.

The `arm64` build-script option remains available only as a fail-closed future capability check.
It must not yield a release until the native imports, Qt deployment audit, PE scan, and frozen
WebEngine smoke test all pass with upstream ARM64 packages. PyInstaller does not cross-compile
Windows payloads, and an x64 artifact must never be renamed as ARM64.

The x64 release scripts validate their environment and fail when Python, native wheels, or packaged
PE binaries do not match the requested architecture. See [Building from Source](docs/BUILD.md) for
the full preflight, smoke-test, and PE-verification commands.

The supported distributables are the verified x64 PyInstaller bundle and x64 Inno Setup installer.
The bootstrap uses an editable Python installation for source development; an ordinary
non-editable wheel is not an end-user Virelo distribution because the generated React frontend is
assembled by the Windows release pipeline.

## Development Mode

Set the `VIRELO_DEV` environment variable, start the Vite dev server, then run the app:

```powershell
$env:VIRELO_DEV = 1
cd frontend
npm run dev
```

In a separate terminal, use the selected development environment:

```powershell
.venv-x64\Scripts\python.exe main.py
```

The frontend hot-reloads from `localhost:5173`. Changes to React components appear immediately
without restarting the Python backend.

## Development Checks

Run the Python checks from the repository root:

```powershell
.venv-x64\Scripts\python.exe -m ruff format .
.venv-x64\Scripts\python.exe -m ruff check .
.venv-x64\Scripts\python.exe -m pytest -q
```

Run the frontend checks from `frontend/`:

```powershell
npm run format
npm run lint
npm test
npm run build
```

## Architecture

Virelo uses a Python/PySide6 backend that hosts a React frontend inside a QWebEngineView. The two
layers communicate through QWebChannel:

- **Python backend:** Owns all operating-system logic, including window management, keyboard hooks,
  COM automation, the system tray, and settings persistence through QSettings.
- **React frontend:** Renders the settings UI, theme controls, and command palette inside the
  embedded Chromium browser.
- **QWebChannel bridge:** Uses one `VireloBridge` QObject as the communication channel. All data
  crosses the bridge as JSON strings.

In release mode, the frontend is built as static files under `frontend/dist/` and loaded through a
`file:` URL. In development mode, it connects to the Vite development server.

## Documentation

- [Changelog](CHANGELOG.md): User-visible changes in the current development version.
- [Building from Source](docs/BUILD.md): Full build pipeline, development mode, and version
  management.
- [Troubleshooting](docs/TROUBLESHOOTING.md): Common build and runtime issues with fixes.
- [Release Checklist](docs/RELEASE.md): Step-by-step release process.

## Status

Under active development. The current version is defined by `APP_VERSION` in `virelo/app/config.py`.

## License

[MIT](LICENSE)
