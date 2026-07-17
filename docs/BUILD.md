# Building Virelo from Source

Virelo has separate x64 and native ARM64 release pipelines. PyInstaller bundles the active
interpreter and its installed native dependencies; it does not cross-compile a Windows payload.
Building on an ARM64 computer is not sufficient evidence of an ARM64 result.

## Supported Release Targets

| Target | Build process | Output | Runtime |
| --- | --- | --- | --- |
| x64 | Official x64 CPython | x64 | x64 Windows, or Windows 11 ARM64 through x64 emulation |
| ARM64 | Official ARM64 CPython on Windows 11 ARM64 | ARM64 | Windows 11 ARM64 only |

The ARM64 installer is restricted to an actual ARM64 operating system. The x64 installer uses
Inno Setup's `x64compatible` condition, which includes x64 Windows and Windows 11 ARM64 systems
that can run x64 applications.

## Prerequisites

- Windows 10 version 1809 or later for x64 builds, or Windows 11 ARM64 for native ARM64 builds.
- Official CPython 3.12 or newer in the requested architecture. Python 3.13 is used in CI.
- Node.js 24 LTS in the process architecture used for the build.
- Inno Setup 6.7.3 for installer builds. CI downloads the versioned official release and verifies
  its SHA-256 digest before a silent runner-local installation.
- A non-administrator PowerShell terminal. The build warns because PyInstaller does not need
  elevation and future PyInstaller releases reject unnecessary administrator builds.

Prefer the installer from [python.org](https://www.python.org/downloads/windows/) and select the
Windows x64 or Windows ARM64 package deliberately. Do not rely on whichever `python.exe` happens
to be first on `PATH`.

Conda and Miniforge are not supported release interpreters. A normal `venv` created from Conda
still uses the Conda Python executable, DLL, runtime search paths, and ABI. Likewise, creating a
virtual environment from x64 Python on an ARM64 computer does not turn it into ARM64 Python.

## Inspect the Operating System and Processes

Run these commands before bootstrapping:

```powershell
$python = "C:\Path\To\Selected\python.exe"
$node = "C:\Path\To\Selected\node.exe"

[Runtime.InteropServices.RuntimeInformation]::OSArchitecture
[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
& $python -c "import os, platform, struct, sys; print('sys.executable:', sys.executable); print('sys.version:', sys.version); print('platform.machine():', platform.machine()); print('pointer_bits:', struct.calcsize('P') * 8); print('CONDA_PREFIX:', os.environ.get('CONDA_PREFIX'))"
& $node -p "JSON.stringify({execPath: process.execPath, arch: process.arch, platform: process.platform, version: process.version})"
```

On Windows 11 ARM64, an x64 PowerShell or Python process reports x64 process architecture even
though the native operating-system architecture is ARM64. That is the expected setup only for
the x64-emulated target.

## Architecture-Qualified Environments

Bootstrap one environment for each payload architecture:

```powershell
# x64, on x64 Windows or under Windows 11 ARM64 x64 emulation.
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node

# ARM64, on Windows 11 ARM64 only.
$python = "C:\Path\To\Official-ARM64-Python\python.exe"
$node = "C:\Path\To\Official-ARM64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable $python -NodeExecutable $node
```

The environments are `.venv-x64/` and `.venv-arm64/`. The scripts reject an existing environment
whose recorded interpreter, distribution, or architecture does not match. After checking the
path carefully, remove only the incompatible environment and recreate it:

```powershell
Resolve-Path .venv-arm64
Remove-Item -LiteralPath .venv-arm64 -Recurse -Force
$node = "C:\Path\To\Official-ARM64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable "C:\Path\To\Official-ARM64-Python\python.exe" -NodeExecutable $node
```

Use `.venv-x64` in the equivalent commands for an x64 environment. `-Architecture auto` is
available for local development, but release commands should name `x64` or `arm64` explicitly.

Release dependencies are constrained by `requirements/build-constraints.txt`. It pins the direct
and transitive third-party packages installed by `.[dev,build]`, including the isolated PEP 517
setuptools backend. Update the file as one tested toolchain, especially for PySide6, Shiboken6,
PyInstaller, and pywin32. A bootstrap writes `build/<architecture>/pip-freeze.txt` and records the
complete installed package inventory in the environment marker. It also writes
`build/<architecture>/python-constraints.json` and fails if an installed third-party package is
unpinned, a constraint is stale, or an installed version differs from its exact pin. Only pip,
which comes from the selected official interpreter, and the editable local Virelo project are
explicitly outside that third-party package lock.

This controls Python dependency selection, but it is not a claim that independent builds are
bit-for-bit hermetic. The selected official CPython patch release and its bundled pip, the Node.js
24 patch release and npm, Windows system components, and artifact timestamps can still differ.
The build records the concrete interpreter, tool, package, source, and payload identities so those
differences are auditable. Reuse the same recorded tool versions when byte-level comparison is
required.

## Import and ABI Preflight

The build runs isolated child-process imports before PyInstaller. You can repeat them directly:

```powershell
$venvPython = ".venv-x64\Scripts\python.exe"
& $venvPython -I -c "from PySide6 import QtCore, QtWidgets, QtWebEngineCore, QtWebEngineWidgets; print(QtCore.qVersion())"
& $venvPython -I -c "import win32api, win32gui, win32event, pythoncom, pywintypes, comtypes"
```

For ARM64, replace `.venv-x64` with `.venv-arm64`. A failure is fatal. The preflight records and
checks the Python DLL, `QtCore.pyd`, `Qt6Core.dll`, `pythoncom`, and `pywintypes`. It also verifies
that installed wheel tags and PE `Machine` fields match the requested architecture.

## Build Commands

Use explicit Python and Node executables for a release build.

### x64

```powershell
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\build-installer.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\verify-release.ps1 -Architecture x64
```

### Native ARM64

Run in a native ARM64 PowerShell process on Windows 11 ARM64:

```powershell
$python = "C:\Path\To\Official-ARM64-Python\python.exe"
$node = "C:\Path\To\Official-ARM64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable $python -NodeExecutable $node
.\scripts\build-installer.ps1 -Architecture arm64 -PythonExecutable $python -NodeExecutable $node
.\scripts\verify-release.ps1 -Architecture arm64
```

The pipeline runs a clean, lockfile-driven `npm ci`, builds the frontend, performs the Python and Qt
preflight, runs PyInstaller's official PySide6 hooks, validates the bundle, compiles the matching
installer, and runs release verification. It treats a failed `QtLibraryInfo(PySide6)` probe as a
build failure even if PyInstaller returns zero.

## Outputs

| Target | PyInstaller analysis | Application bundle | Installer |
| --- | --- | --- | --- |
| x64 | `build/x64/Virelo/` | `dist/x64/Virelo/` | `installer/dist/VireloSetup-<version>-x64.exe` |
| ARM64 | `build/arm64/Virelo/` | `dist/arm64/Virelo/` | `installer/dist/VireloSetup-<version>-arm64.exe` |

One architecture cannot overwrite the other. The installer source is derived from its declared
`PayloadArchitecture`; Inno Setup stops if that architecture-qualified payload is missing.

## PE Architecture Verification

The dependency-light verifier reads the PE `Machine` field. It recognizes AMD64 (`0x8664`),
ARM64 (`0xAA64`), and x86 (`0x014C`). To scan an entire bundle and save a machine-readable report:

```powershell
.venv-x64\Scripts\python.exe scripts/pe_arch.py --expected x64 --recursive --json build\x64\pe-report.json dist\x64\Virelo
.venv-arm64\Scripts\python.exe scripts/pe_arch.py --expected arm64 --recursive --json build\arm64\pe-report.json dist\arm64\Virelo
```

The release pipeline verifies at least Python, the Python DLL, `QtCore.pyd`, `Qt6Core.dll`,
`QtWebEngineProcess.exe`, `pythoncom`, `pywintypes`, and `Virelo.exe`. Any executable or loadable
extension with the wrong machine type fails the release. The Inno Setup bootstrap itself may be
x86 or x64, as may its generated uninstaller; these are treated separately. The application
payload and installer architecture gate determine the application target.

## Smoke Tests

Run the source smoke test before freezing and the frozen smoke test after building:

```powershell
.venv-x64\Scripts\python.exe -m virelo --smoke-test --smoke-report build\x64\source-smoke.json
dist\x64\Virelo\Virelo.exe --smoke-test --smoke-report build\x64\frozen-smoke.json
```

Use the ARM64 paths for a native build. The report is required because the frozen executable is
windowed and has no console. A zero process exit code without a successful report is not accepted.
Release verification also requires the report schema, application, version, frozen state, PE-derived
process architecture, and 64-bit pointer width to match the requested target. The smoke process
loads an in-memory Qt WebEngine page and reads it back, which exercises the helper process and
runtime resources without displaying or changing Virelo's normal interface.

Each asynchronous Qt WebEngine operation has a 30-second in-process timeout. The release scripts
also impose a 120-second timeout on the whole source or frozen smoke process, terminate its process
tree if that outer limit expires, and fail if termination cannot be confirmed. The outer limit
prevents a startup or shutdown hang outside the WebEngine callback from blocking a build forever.

## Frontend Dependencies

React and Vite output is architecture-neutral, but `node_modules` is not because tools such as
esbuild contain native executables. Release builds run `npm ci`, and the build records Node's
process architecture so a tree created by x64 Node is not silently reused by ARM64 Node.

Run both audit views when changing frontend dependencies:

```powershell
Push-Location frontend
npm audit
npm audit --omit=dev
Pop-Location
```

The audited lockfile currently passes both reports with zero findings. Compatible lockfile updates
should be applied normally if a later audit changes. Do not use `npm audit fix --force`, and do not
disable install-script security globally to accommodate esbuild. `frontend/package.json` permits
the exact audited esbuild package install script, and `frontend/.npmrc` makes unreviewed scripts a
hard failure. The macOS-only `fsevents` script is explicitly denied for this Windows release. The
build then verifies and runs esbuild's native PE.
A blocked or wrong-architecture esbuild installation is actionable.

## Development Mode

For frontend hot reloading:

```powershell
$env:VIRELO_DEV = 1
Push-Location frontend
npm run dev
```

In a separate terminal:

```powershell
.venv-x64\Scripts\python.exe main.py
```

The frontend reloads from `localhost:5173`. Python changes require restarting `main.py`.

The bootstrap installs Virelo in editable mode so source imports and the repository's generated
frontend remain in one verified tree. Do not use a non-editable wheel as an end-user application
package. The supported distributables are `dist/<architecture>/Virelo/` and the matching Inno
Setup installer, both of which include the generated frontend, icon, and license.

## Version Management

`APP_VERSION` in `virelo/app/config.py` is the application version source of truth. The frontend,
Python package metadata, PyInstaller metadata, and installer must all match. Do not set
PyInstaller's Windows `target_arch` to attempt cross-compilation.

After changing `APP_VERSION` or Python packaging metadata, rerun the architecture's bootstrap
before building. Editable-install distribution metadata is generated by pip and does not update
merely because a source file changed:

```powershell
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.venv-x64\Scripts\python.exe -c "import importlib.metadata; print(importlib.metadata.version('virelo'))"
```

Use the corresponding ARM64 paths and executables for a native ARM64 release. The final verifier
also reads the embedded file and product versions from both `Virelo.exe` and the installer.
