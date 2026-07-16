# Virelo

Virelo is a personal Windows desktop utility that snaps windows to configurable sizes and auto-sizes File Explorer columns. Python/PySide6 backend hosts a React frontend in QWebEngineView, communicating through QWebChannel.

## Build Commands

All build scripts are in `scripts/` and use PowerShell. Run from the project root.

```powershell
# Bootstrap: create .venv and install Python dependencies
scripts/bootstrap.ps1

# Clean: remove all build artifacts (dist/, build/, frontend/dist/)
scripts/clean.ps1

# Build frontend: npm ci (if needed) + npm run build -> frontend/dist/
scripts/build-frontend.ps1

# Build app: build-frontend + PyInstaller -> dist/Virelo/Virelo.exe
scripts/build-app.ps1

# Build installer: build-app + Inno Setup -> installer/dist/VireloSetup.exe
scripts/build-installer.ps1

# Verify release: check dist/ output integrity
scripts/verify-release.ps1
```

### Dev Mode

```powershell
$env:VIRELO_DEV = 1
cd frontend
npm run dev          # Vite dev server on localhost:5173
```

In a separate terminal:

```powershell
python main.py
```

## Project Structure

- `main.py` -- Thin entry shim: `from virelo.app import main; main()`
- `virelo/` -- Python package (all backend source)
  - `app/` -- Application shell
    - `__main__.py` -- Startup: admin elevation, single-instance, QApp, MainWindow
    - `window.py` -- MainWindow: tray, chrome, thread lifecycle, wiring
    - `config.py` -- Product metadata, defaults, version (single source of truth)
    - `webview.py` -- QWebEngineView host
  - `bridge/` -- Python-JS communication
    - `bridge.py` -- QWebChannel bridge (VireloBridge QObject)
    - `capture_guard.py` -- Thread-safe key capture mutex
  - `services/` -- Business logic
    - `snap.py` -- MultiPressHotkeyListener (keyboard detection), SnapRestoreController (window movement), SnapService facade, geometry calculations
    - `explorer_columns.py` -- COM-based Explorer column autosize
    - `explorer_service.py` -- ExplorerService lifecycle manager (start/stop/is_running)
  - `workers/` -- Background QThread workers
    - `key_capture.py` -- KeyCaptureWorker and KeyCaptureSession
    - `explorer.py` -- ExplorerAutosizeWorker and ExplorerAutosizeEngine
  - `platform/` -- Windows platform utilities
    - `win32_helpers.py` -- DPI, monitor rects, fullscreen detection, window geometry
    - `resources.py` -- PyInstaller-compatible resource path resolution
    - `paths.py` -- Path canonicalization
    - `theme.py` -- Theme resolution (system/dark/light)
    - `startup.py` -- Startup shortcut management
  - `settings/` -- Settings persistence
    - `persistence.py` -- QSettings read/write (Settings class)
    - `state.py` -- JSON facade with validation and draft model (SettingsState class)
- `frontend/src/` -- React 19 frontend (app.jsx, pages.jsx, panels.jsx, etc.)
- `tests/` -- Test suite
  - `unit/` -- Pure logic tests (no Qt, runs in CI)
  - `integration/` -- Tests requiring PySide6 (local only)
- `scripts/` -- PowerShell build pipeline
- `installer/virelo.iss` -- Inno Setup installer script
- `Virelo.spec` -- PyInstaller spec file
- `pyproject.toml` -- Project metadata, dependencies, Ruff and pytest config
- `.github/workflows/ci.yml` -- CI: lint, test, frontend build, stale-name check

## Naming Conventions

**Python:** `snake_case` for modules and functions, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.

**JavaScript:** `camelCase` for functions and variables, `PascalCase` for React components.

## Forbidden Changes

1. **Never reintroduce "Windows Toolbox" or "Toolbox" in any file.** The project was renamed to Virelo. All stale naming has been cleaned up.

2. **Never add fake or placeholder UI controls that do not connect to real backend logic.** Every visible control must be wired to the Python bridge. Do not add UI for features that do not exist (e.g., auto-update toggle, telemetry toggle).

3. **Never commit generated artifacts to git.** These directories and files are build output and must stay in `.gitignore`:
   - `frontend/dist/`
   - `dist/`
   - `build/`
   - `.venv/`
   - `__pycache__/`

4. **Never hardcode version strings.** Use `APP_VERSION` from `virelo/app/config.py`. The frontend receives the version via Vite `define` at build time (`__APP_VERSION__`). The installer receives it via ISCC `/D` flag.

## Known Footguns

1. **`virelo/app/config.py` must not be imported in `Virelo.spec`.** The spec file runs in PyInstaller's analysis context where PySide6 may not be importable. Use regex to parse the version string instead of importing the module.

2. **PowerShell `$LASTEXITCODE` must be checked after every external command.** `$ErrorActionPreference = "Stop"` only catches PowerShell cmdlet errors, not native command failures (npm, python, pyinstaller, ISCC). Always add: `if ($LASTEXITCODE -ne 0) { throw "command failed" }`.

3. **Vite `define` values must use `JSON.stringify()`.** Without it, Vite treats the value as a JavaScript expression instead of a string literal. Example: `define: { __APP_VERSION__: JSON.stringify('1.5.0') }`.

4. **Inno Setup `#define` must use `#ifndef` guard to allow `/D` override.** An unconditional `#define` in the .iss file overrides the command-line `/D` flag. Use `#ifndef MyAppVersion` / `#define MyAppVersion "0.0.0-dev"` / `#endif`.
