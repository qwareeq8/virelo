# Building Virelo from Source

Virelo currently has one supported release payload: x64. It runs natively on x64 Windows and
through x64 application emulation on Windows 11 ARM64. PyInstaller bundles the active interpreter
and its installed native dependencies; it does not cross-compile a Windows payload.

Native ARM64 packaging is blocked upstream. The published Windows ARM64 PySide6 wheels omit the
Qt WebEngine bindings, helper process, and resources required by Virelo. The build scripts retain
ARM64 validation as a fail-closed future capability check, but no native ARM64 artifact is currently
releasable.

Qt's [supported-platform exceptions](https://doc.qt.io/qt-6/supported-platforms.html#exceptions)
explicitly note that individual modules, especially Qt WebEngine, can differ from the general
platform matrix. CI inventories the pinned official
[PySide6-Addons wheel](https://pypi.org/project/PySide6-Addons/6.11.1/#files) before deciding whether
native packaging is possible.

## Supported Release Targets

| Target | Build process | Output | Runtime |
| --- | --- | --- | --- |
| x64 | Official x64 CPython | x64 | x64 Windows, or Windows 11 ARM64 through x64 emulation |
| ARM64 capability check | Official ARM64 CPython | None | Upstream-blocked |

The supported x64 installer uses Inno Setup's `x64compatible` condition, which includes x64
Windows and Windows 11 ARM64 systems that can run x64 applications. The installer definition keeps
an ARM64 architecture gate for a future verified payload, but no ARM64 installer is currently
produced.

## Prerequisites

- Windows 10 version 1809 or later on x64, or Windows 11 ARM64 with x64 application emulation.
- Official x64 CPython 3.12 or newer. Python 3.13 is used in CI.
- x64 Node.js 24 LTS.
- Inno Setup 6.7.3 for installer builds. CI downloads the versioned official release and verifies
  its SHA-256 digest before a silent runner-local installation.
- A non-administrator PowerShell terminal. The build warns because PyInstaller does not need
  elevation and future PyInstaller releases reject unnecessary administrator builds.

Prefer the x64 installer from [python.org](https://www.python.org/downloads/windows/) for release
builds. Do not rely on whichever `python.exe` happens to be first on `PATH`. An official ARM64
interpreter is relevant only when auditing whether upstream native dependencies have become
complete.

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
& $python -I scripts\pe_arch.py --expected x64 $python
```

On Windows 11 ARM64, do not use `platform.machine()` or WOW64 status alone to identify the selected
Python binary. Microsoft documents that [x64 emulation has no WOW64
layer](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation), while
[`IsWow64Process2`](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2)
returns `IMAGE_FILE_MACHINE_UNKNOWN` for a process that is not under WOW64. An x64-emulated Python
process can therefore report `platform.machine()` as `ARM64`, or produce an
`IsWow64Process2` process-machine result of `UNKNOWN` with native machine `ARM64`. Those values
describe the host or emulation context; they do not prove that `python.exe` is ARM64.

Prove the selected interpreter's architecture from the `python.exe` PE `Machine` field with
`scripts\pe_arch.py`. The x64 release then requires corroborating ABI evidence: `win_amd64` wheel
tags and matching PE fields for the Python DLL, extension modules, Qt runtime, PyInstaller
bootloader, and frozen application. Pointer width only distinguishes 32-bit from 64-bit processes;
it cannot distinguish x64 from ARM64.

## Architecture-Qualified Environments

Bootstrap the supported x64 release environment explicitly:

```powershell
# x64, on x64 Windows or under Windows 11 ARM64 x64 emulation.
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
```

The supported environment is `.venv-x64/`. The scripts reject an existing environment whose
recorded interpreter, distribution, or architecture does not match. After checking the path
carefully, remove only the incompatible environment and recreate it:

```powershell
Resolve-Path .venv-x64
Remove-Item -LiteralPath .venv-x64 -Recurse -Force
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
```

On a native Windows ARM64 machine, `.venv-arm64/` may be created only to repeat the import and wheel
inventory checks when evaluating a newer upstream PySide6 release. It is not a release environment.
`-Architecture auto` is available for local development, but current release commands must name
`x64` explicitly.

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

The preflight records and checks the Python DLL, `QtCore.pyd`, `Qt6Core.dll`, `pythoncom`, and
`pywintypes`. It also verifies that installed wheel tags and PE `Machine` fields match the requested
architecture.

For a future native ARM64 capability check, repeat the imports with `.venv-arm64`. With the
currently published wheels, the Qt WebEngine import fails because the modules are absent. That
failure is a release blocker, not a warning to suppress or a reason to copy x64 Qt binaries into
the environment.

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

### Native ARM64 Status

Do not build or publish a native ARM64 Virelo release from the current dependency set. Published
Windows ARM64 PySide6 wheels omit `QtWebEngineCore`, `QtWebEngineWidgets`,
`QtWebEngineProcess.exe`, and the WebEngine data files used by Virelo's frontend. Native packaging
can be reconsidered only after an upstream wheel passes the isolated imports, Qt deployment audit,
recursive PE scan, and frozen WebEngine smoke test. An x64 payload must never be renamed as ARM64.

The x64 pipeline runs a clean, lockfile-driven `npm ci`, builds the frontend, performs the Python
and Qt preflight, runs PyInstaller's official PySide6 hooks, validates the bundle, compiles the
matching installer, and runs release verification. It treats a failed `QtLibraryInfo(PySide6)`
probe as a build failure even if PyInstaller returns zero.

## Outputs

| Target | PyInstaller analysis | Application bundle | Installer |
| --- | --- | --- | --- |
| x64 | `build/x64/Virelo/` | `dist/x64/Virelo/` | `installer/dist/VireloSetup-<version>-x64.exe` |
| ARM64 capability check | Diagnostic reports only | No supported bundle | No supported installer |

Architecture-qualified paths prevent a future native capability check from overwriting the x64
release. The installer source is derived from its declared `PayloadArchitecture`; Inno Setup stops
if that architecture-qualified payload is missing.

## PE Architecture Verification

The dependency-light verifier reads the PE `Machine` field. It recognizes AMD64 (`0x8664`),
ARM64 (`0xAA64`), and x86 (`0x014C`). To scan an entire bundle and save a machine-readable report:

```powershell
.venv-x64\Scripts\python.exe scripts/pe_arch.py --expected x64 --recursive --json build\x64\pe-report.json dist\x64\Virelo
```

The verifier recognizes ARM64 so a future capability assessment can fail on mixed-architecture
payloads. This support does not imply that a current native ARM64 Virelo bundle exists.

The x64 release pipeline verifies at least Python, the Python DLL, `QtCore.pyd`, `Qt6Core.dll`,
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

The report is required because the frozen executable is windowed and has no console. A zero process
exit code without a successful report is not accepted. Release verification also requires the
report schema, application, version, frozen state, PE-derived process architecture, and 64-bit
pointer width to match the requested target. The smoke process loads an in-memory Qt WebEngine page
and reads it back, which exercises the helper process and runtime resources without displaying or
changing Virelo's normal interface. A future native ARM64 release must pass this same smoke test;
current upstream wheels cannot do so.

Each asynchronous Qt WebEngine operation has a 30-second in-process timeout. The release scripts
also impose a 120-second timeout on the whole source or frozen smoke process, terminate its process
tree if that outer limit expires, and fail if termination cannot be confirmed. The outer limit
prevents a startup or shutdown hang outside the WebEngine callback from blocking a build forever.

## Frontend Dependencies

React and Vite output is architecture-neutral, but `node_modules` is not because tools such as
esbuild contain native executables. Release builds run `npm ci`, and the build records Node's
process architecture so a tree from a different Node architecture is not silently reused. Current
release builds use x64 Node. A future ARM64 capability check must use native ARM64 Node without
being mistaken for a releasable application payload.

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
package. The supported distributables are `dist/x64/Virelo/` and the matching x64 Inno Setup
installer, both of which include the generated frontend, icon, and license.

## Version Management

`APP_VERSION` in `virelo/app/config.py` is the application version source of truth. The frontend,
Python package metadata, PyInstaller metadata, and installer must all match. Do not set
PyInstaller's Windows `target_arch` to attempt cross-compilation.

After changing `APP_VERSION` or Python packaging metadata, rerun the x64 bootstrap before building.
Editable-install distribution metadata is generated by pip and does not update merely because a
source file changed:

```powershell
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.venv-x64\Scripts\python.exe -c "import importlib.metadata; print(importlib.metadata.version('virelo'))"
```

The final verifier also reads the embedded file and product versions from both `Virelo.exe` and the
installer. Do not create an ARM64 release checklist or artifact until upstream Qt WebEngine support
passes every fail-closed capability check described above.
