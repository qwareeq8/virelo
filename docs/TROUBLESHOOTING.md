# Troubleshooting Virelo

## Architecture and Environment Failures

### An ARM64 computer produced an x64 application

**Cause:** The active Python process was x64 and ran through Windows 11 ARM64 emulation. pip then
selected `win_amd64` wheels, and PyInstaller used its Intel bootloader. The host processor does not
change the architecture of a process or its dependencies.

**Fix:** Select an official ARM64 CPython executable and rebuild a new `.venv-arm64` environment:

```powershell
$python = "C:\Path\To\Official-ARM64-Python\python.exe"
$node = "C:\Path\To\Official-ARM64-Node\node.exe"
& $python -c "import platform, struct, sys; print(sys.executable); print(platform.machine()); print(struct.calcsize('P') * 8)"
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable $python -NodeExecutable $node
```

Do not set `target_arch="arm64"` in `Virelo.spec`. PyInstaller is not a Windows cross-compiler.

### An existing environment is incompatible

**Cause:** `.venv-x64` or `.venv-arm64` was created by a different distribution, executable, or
process architecture.

**Fix:** Follow the remediation path printed by the bootstrap script. Check the path before
removing it:

```powershell
Resolve-Path .venv-arm64
Remove-Item -LiteralPath .venv-arm64 -Recurse -Force
$node = "C:\Path\To\Official-ARM64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture arm64 -PythonExecutable "C:\Path\To\Official-ARM64-Python\python.exe" -NodeExecutable $node
```

Changing the name of a virtual environment does not change its architecture.

### The build detects Conda or Miniforge contamination

**Cause:** The selected interpreter is from Conda, or `PATH`, `PYTHONPATH`, `CONDA_PREFIX`, or DLL
search resolution still references a Conda installation. A `venv` created from that interpreter
remains Conda-based.

**Fix:** Open a clean non-Conda PowerShell session, clear user-supplied `PYTHONPATH`, and pass the
full path to an official CPython executable with `-PythonExecutable`. Do not copy Python, Qt, ICU,
OpenSSL, or VC runtime DLLs from Conda into the bundle.

### The installed Python package closure is not exactly constrained

**Cause:** A direct or transitive third-party package is missing from
`requirements/build-constraints.txt`, an exact pin does not match the installed version, a stale
pin no longer has a corresponding package, or the environment contains an unexpected package.

**Fix:** Inspect `build/<architecture>/python-constraints.json`. Update and test the complete
constraint set as one toolchain; do not merely add an exception for an unexplained package. Then
remove the incompatible architecture-qualified environment and rerun bootstrap. Only the selected
interpreter's bootstrap pip and the editable local Virelo distribution are intentionally outside
the exact third-party package lock.

## Qt and PyInstaller Failures

### QtCore reports `DLL load failed` or `The specified procedure could not be found`

**Cause:** Python, PySide6, Shiboken6, or a loaded Qt dependency has the wrong ABI or architecture.
An unrelated DLL earlier on the search path can also satisfy a filename while exporting the wrong
symbols. The failed build that motivated the architecture pipeline mixed Conda Python with x64
PySide6 wheels on ARM64 Windows.

**Fix:** Recreate the architecture-qualified environment from official CPython, install the
constrained dependencies, and run both isolated import probes before PyInstaller:

```powershell
$python = ".venv-arm64\Scripts\python.exe"
& $python -I -c "from PySide6 import QtCore, QtWidgets, QtWebEngineCore, QtWebEngineWidgets; print(QtCore.qVersion())"
& $python -I -c "import win32api, win32gui, win32event, pythoncom, pywintypes, comtypes"
```

Do not download individual DLLs from third-party sites.

### PyInstaller reports `QtLibraryInfo(PySide6): failed to obtain Qt library info`

**Cause:** PyInstaller could not import and inspect the active PySide6 installation. A zero
PyInstaller exit code after this message does not make the bundle valid.

**Fix:** Treat the build as failed. Correct the import or DLL-resolution problem and rerun a clean
build. The release scripts scan PyInstaller output and reject this hook failure.

### `qwindows.dll` or Qt WebEngine data is missing

**Cause:** The PySide6 hook did not complete, the wrong environment invoked PyInstaller, or a
partially generated `dist` tree was mistaken for a completed build.

**Fix:** Rebuild from the constrained environment and run `.\scripts\verify-release.ps1` for the
target architecture. Verification requires the Windows platform plugin,
`QtWebEngineProcess.exe`, WebEngine resources, locale data, Qt DLLs, and PySide/Shiboken extension
modules. Use PyInstaller's official PySide6 hooks instead of manually enumerating the Qt tree.

### PyInstaller warns about unresolved DLLs

Inspect `build/<architecture>/Virelo/warn-Virelo.txt`, `xref-Virelo.html`, the analysis table of
contents, and the final `_internal` tree.

- Windows API-set contracts and normal operating-system DLLs can be documented as benign after
  confirming that Windows supplies them on the supported operating systems.
- Any missing application, Python, Qt, WebEngine, Shiboken, pywin32, VC runtime, ICU, or OpenSSL
  dependency is actionable.
- A dependency resolved from an unrelated Conda, QEMU, Git, or other tool directory is actionable
  even if its PE architecture happens to match.
- `mfc140u.dll` is actionable if `pythonwin/win32ui.pyd` is shipped. Virelo does not use Pythonwin;
  the unused Pythonwin path should be excluded after confirming the module graph, not satisfied by
  copying MFC DLLs into the application.

## Installer Failures

### The x64 installer is rejected on Windows 11 ARM64

**Cause:** `ArchitecturesAllowed=x64os` means an actual x64 operating system. It excludes ARM64
Windows even when x64 application emulation is available.

**Fix:** Build the x64 payload through the architecture-aware installer script. It compiles with
`x64compatible`. The native installer uses `arm64` and is intentionally rejected everywhere else.

### Inno Setup cannot find the payload

**Cause:** The declared architecture does not have a matching
`dist/<architecture>/Virelo/Virelo.exe` output.

**Fix:** Build and verify the application before compiling the installer. The `.iss` file derives
its source directory from `PayloadArchitecture`; do not point an ARM64 installer at the x64 tree.

### Inno Setup warns about administrative install mode and per-user areas

**Cause:** A per-machine installer running elevated tried to delete files in `{localappdata}` or
`{userstartup}`. Those constants describe one profile and cannot correctly represent every user
of a machine-wide installation.

**Fix:** Virelo remains a per-machine, administrator installation under 64-bit Program Files. Its
installer preserves per-user settings, logs, and Explorer recovery backups. During uninstall it
invokes the installed Virelo executable with `--remove-startup-shortcut` before removing the
executable. This removes the shortcut for the account running Uninstall, including ordinary
same-account UAC elevation. Inno Setup does not support `runasoriginaluser` at uninstall time, so
over-the-shoulder elevation with another administrator cannot clean the original user's startup
link automatically. It never enumerates or deletes settings, logs, backups, or startup links from
other profiles.

## Frontend Build Failures

### esbuild has the wrong architecture

**Cause:** `node_modules` was reused after switching between x64 and ARM64 Node processes. The
frontend files are portable, but esbuild is a native executable.

**Fix:** Use Node.js 24 LTS and rerun the release build. It records Node process architecture and
runs deterministic `npm ci` installation. Do not weaken install-script security globally.
`frontend/package.json` permits only the exact audited esbuild package install script,
`frontend/.npmrc` rejects unreviewed scripts, and the macOS-only `fsevents` script is explicitly
denied. The build verifies the resulting PE before using it. Confirm `node -p process.arch` first.

### npm audit reports findings

Run both reports:

```powershell
Push-Location frontend
npm audit
npm audit --omit=dev
Pop-Location
```

The current lockfile passes both the complete and production-only audits with zero findings. If a
future report changes, distinguish shipped runtime dependencies from build and test tools, then
apply compatible lockfile updates. Do not use `npm audit fix --force` because it can make
unreviewed major-version changes.

## Smoke-Test Failures

### A windowed frozen smoke test has no useful console output

Use a machine-readable report and inspect both the process exit code and report:

```powershell
$process = Start-Process -FilePath "dist\x64\Virelo\Virelo.exe" `
    -ArgumentList "--smoke-test", "--smoke-report", "build\x64\manual-smoke.json" `
    -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Frozen smoke test failed with exit code $($process.ExitCode)." }
Get-Content build\x64\manual-smoke.json
```

The smoke flag is parsed before UAC elevation, so CI smoke tests must not prompt. Each WebEngine
callback has a 30-second timeout, and the release scripts enforce a separate 120-second limit for
the complete smoke process. They terminate the process tree on an outer timeout and fail if they
cannot confirm termination. The manual command above is useful for inspection but does not add
that outer guard; use the release scripts for a bounded release gate.

The `Qt WebEngine minimal page load` check must report `loadFinished: true`, the expected title,
and the document marker. A timeout, renderer termination, failed load, or missing marker is a
deployment failure; inspect that check's `error` field before investigating unrelated DLL warnings.

## Runtime Issues

### UAC appears every time Virelo starts

This is expected. Virelo elevates for global keyboard hooks and cross-process window operations.
Approve the prompt with the same Windows account that owns the desktop. If a standard user enters
credentials for a different administrator account, Virelo refuses to change Explorer folder views
because `HKCU` would refer to the administrator profile rather than the visible user's profile.

### Window dragging does not work

The frameless window uses `WM_NCHITTEST` drag zones. `TITLE_BAR_HEIGHT` in
`virelo/app/window_hit_test.py` must match the frontend title bar height.

### Window behavior is wrong on a monitor left of the primary display

Monitor coordinates can be negative. `WM_NCHITTEST` must decode signed coordinates from `lParam`
and all Win32 function prototypes must preserve pointer-sized `HWND`, `WPARAM`, `LPARAM`, and
`LRESULT` values.

### Explorer column autosizing does not run

Column autosizing requires File Explorer Details view. Enable Details view with the Explorer View
menu or `Ctrl+Shift+6`, then confirm the autosize option is enabled in Virelo.
