# Building Virelo from Source

## Prerequisites

- Windows 10/11 x64
- Python 3.12+
- Node.js (LTS recommended)
- Inno Setup 6 (only required for building the installer)

## Quick Start

```powershell
git clone https://github.com/yusufqwareeq/virelo.git
cd virelo
scripts/bootstrap.ps1
scripts/build-app.ps1
```

The built application is at `dist/Virelo/Virelo.exe`.

## Build Pipeline

Virelo uses PowerShell scripts in `scripts/` for all build operations. Each script validates
its preconditions and fails early if a required tool is missing.

| Script | What It Does | Output |
|--------|-------------|--------|
| `scripts/bootstrap.ps1` | Creates `.venv` and installs Python dependencies from `pyproject.toml` | `.venv/` directory |
| `scripts/build-frontend.ps1` | Runs `npm ci` (if needed) and `npm run build` | `frontend/dist/` |
| `scripts/build-app.ps1` | Builds frontend, then runs PyInstaller via `Virelo.spec` | `dist/Virelo/Virelo.exe` |
| `scripts/build-installer.ps1` | Builds app, then runs Inno Setup | `installer/dist/VireloSetup.exe` |
| `scripts/clean.ps1` | Removes all build artifacts (`dist/`, `build/`, `frontend/dist/`, `__pycache__/`, etc.) | Clean working tree |
| `scripts/verify-release.ps1` | Checks build output integrity (versions, assets, naming) | Pass/fail report |

### Build Order

The scripts handle dependencies automatically:

- `build-frontend.ps1` calls `npm ci` if `node_modules/` is missing
- `build-app.ps1` calls `build-frontend.ps1` before PyInstaller
- `build-installer.ps1` calls `build-app.ps1` before Inno Setup

For a full release build: `scripts/build-installer.ps1` runs the entire pipeline.

## Development Mode

For frontend hot-reloading during development:

```powershell
$env:VIRELO_DEV = 1
cd frontend
npm run dev          # Vite dev server on localhost:5173
```

In a separate terminal:

```powershell
python main.py
```

The React frontend hot-reloads from `localhost:5173`. Python backend changes require restarting
`main.py`.

## Version Management

The single source of truth for the application version is `virelo/app/config.py` (`APP_VERSION`).

- The frontend receives the version via Vite `define` at build time
- The installer receives it via Inno Setup `/D` flag
- The PyInstaller spec file parses it via regex (not import -- see [Troubleshooting](TROUBLESHOOTING.md))

Do not hardcode version strings anywhere else.

## Smoke Test

After building, verify the application initializes correctly:

```powershell
python -m virelo --smoke-test
```

This runs 6 subsystem checks without showing a window or requiring admin privileges.
