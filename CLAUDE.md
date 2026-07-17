# Virelo

Virelo is a personal Windows desktop utility that snaps windows to configurable sizes and
autosizes File Explorer columns. A Python/PySide6 backend hosts a React frontend in QWebEngineView,
and the two layers communicate through QWebChannel.

## Build Commands

All build scripts are in `scripts/` and use PowerShell. Run from the project root.

```powershell
# Bootstrap the supported x64 release environment from an explicit official toolchain.
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable C:\Path\To\x64\python.exe -NodeExecutable C:\Path\To\x64\node.exe

# Future capability check only. This is not a release command while ARM64 Qt WebEngine is absent.
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable C:\Path\To\ARM64\python.exe -NodeExecutable C:\Path\To\ARM64\node.exe

# Remove all build artifacts under dist/, build/, and frontend/dist/.
.\scripts\clean.ps1

# Build the frontend with an explicit Node.js 24 LTS executable.
.\scripts\build-frontend.ps1 -Architecture x64 -PythonExecutable C:\Path\To\x64\python.exe -NodeExecutable C:\Path\To\x64\node.exe

# Build the frontend and PyInstaller application bundle.
.\scripts\build-app.ps1 -Architecture x64 -PythonExecutable C:\Path\To\x64\python.exe -NodeExecutable C:\Path\To\x64\node.exe

# Build installer/dist/VireloSetup-<version>-<architecture>.exe.
.\scripts\build-installer.ps1 -Architecture x64 -PythonExecutable C:\Path\To\x64\python.exe -NodeExecutable C:\Path\To\x64\node.exe

# Verify the release architecture, Qt deployment, smoke report, and installer.
.\scripts\verify-release.ps1 -Architecture x64
```

Current release builds must name `x64` explicitly. The `arm64` option is reserved for fail-closed
future capability checks and must not produce a release while upstream PySide6 ARM64 wheels omit
Qt WebEngine. PyInstaller does not cross-compile Windows payloads; the selected official CPython
process and native wheels determine architecture. Do not use Conda or Miniforge for release builds.

### Dev Mode

```powershell
$env:VIRELO_DEV = 1
cd frontend
npm run dev          # Vite dev server on localhost:5173
```

In a separate terminal:

```powershell
.venv-x64\Scripts\python.exe main.py
```

## Project Structure

- `main.py`: Thin entry shim that invokes `virelo.app.main()`.
- `virelo/`: Python package containing the backend source.
  - `app/`: Application startup, window shell, native hit testing, configuration, and web view.
  - `bridge/`: QWebChannel bridge and thread-safe key-capture guard.
  - `services/`: Window snapping, Explorer column autosizing, and Explorer default-view operations.
  - `workers/`: Background key-capture and Explorer-autosize workers.
  - `platform/`: Windows ABI declarations, path and navigation validation, resources, startup, and
    theme utilities.
  - `settings/`: Settings persistence, key validation, and the validated draft model.
- `frontend/src/`: React 19 frontend.
- `tests/`: Unit tests and Windows Qt integration tests. Windows packaging CI runs the complete
  suite; Linux CI excludes tests marked `requires_qt`.
- `scripts/`: PowerShell build pipeline and dependency-light release verifiers.
- `installer/virelo.iss`: Inno Setup installer script.
- `Virelo.spec`: PyInstaller specification.
- `pyproject.toml`: Project metadata, dependencies, Ruff configuration, and pytest configuration.
- `.github/workflows/ci.yml`: Linux lint, test, and frontend jobs, native x64 packaging, ARM64
  dependency-capability checks, and x64-on-ARM64 emulation acceptance.

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
   - `.venv-x64/`
   - `.venv-arm64/`
   - `__pycache__/`

4. **Never hardcode version strings.** Use `APP_VERSION` from `virelo/app/config.py`. The frontend receives the version via Vite `define` at build time (`__APP_VERSION__`). The installer receives it via ISCC `/D` flag.

## Known Footguns

1. **`virelo/app/config.py` must not be imported in `Virelo.spec`.** The spec file runs in PyInstaller's analysis context where PySide6 may not be importable. Use regex to parse the version string instead of importing the module.

2. **PowerShell `$LASTEXITCODE` must be checked after every external command.**
   `$ErrorActionPreference = "Stop"` catches PowerShell cmdlet errors but not native command
   failures from npm, Python, PyInstaller, or ISCC. Always add:
   `if ($LASTEXITCODE -ne 0) { throw "The command failed." }`.

3. **Vite `define` values must use `JSON.stringify()`.** Without it, Vite treats the value as a
   JavaScript expression instead of a string literal. Example:
   `define: { __APP_VERSION__: JSON.stringify(process.env.VITE_APP_VERSION) }`.

4. **Inno Setup `#define` must use `#ifndef` guard to allow `/D` override.** An unconditional `#define` in the .iss file overrides the command-line `/D` flag. Use `#ifndef MyAppVersion` / `#define MyAppVersion "0.0.0-dev"` / `#endif`.

5. **Never infer payload architecture from the host processor.** Check the operating-system,
   process, interpreter, wheel, bootloader, extension-module, and frozen PE architectures. An x64
   process on Windows 11 ARM64 produces an x64 payload.

6. **Never reuse one virtual environment or `node_modules` tree across architectures.** The x64
   release environment is `.venv-x64`; `.venv-arm64` is reserved for future capability checks.
   Frontend builds must validate Node process architecture because esbuild contains a native
   executable.

7. **Treat failed Qt hook discovery as fatal.** `QtLibraryInfo(PySide6)` failures and missing
   `qwindows.dll`, `QtWebEngineProcess.exe`, resources, or locales invalidate the bundle even when
   PyInstaller returns success.

8. **Do not infer Qt WebEngine support from general Qt Windows ARM64 support.** Current PySide6
   ARM64 wheels omit the WebEngine Python extensions and runtime. Inspect upstream wheel contents
   and require every import, deployment, PE, and smoke check to pass before enabling native ARM64
   packaging.
