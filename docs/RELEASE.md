# Virelo Windows Release Checklist

This checklist validates local unsigned artifacts. It does not authorize a commit, push, tag,
release, or remote change.

## Release Matrix

| Target | Native operating system | Process architecture | Expected payload | Required result |
| --- | --- | --- | --- | --- |
| x64 | x64 Windows 11 | x64 | x64 | Build, install, smoke test, and launch |
| x64 fallback | ARM64 Windows 11 | x64 emulation | x64 | Installer is allowed and application launches |
| ARM64 native | ARM64 Windows 11 | ARM64 | None | Blocked until upstream PySide6 ARM64 wheels include Qt WebEngine |

GitHub Actions builds, installs, smoke-tests, and uninstalls the x64 package, then separately
installs that exact package on `windows-11-arm` under x64 emulation. A native ARM64 job may check
future upstream capability, but it must not publish a release artifact while Qt WebEngine is
absent. Physical Surface testing remains required for the interactive Windows features listed
below.

## Preflight

1. Use a normal, non-administrator PowerShell terminal.
2. Confirm the working tree and intended version without changing them:

   ```powershell
   git status --short
   .venv-x64\Scripts\python.exe -c "from virelo.app.config import APP_VERSION; print(APP_VERSION)"
   ```

3. Confirm the operating system, PowerShell, Python, and Node process architectures:

   ```powershell
   $python = ".venv-x64\Scripts\python.exe"
   $node = "C:\Path\To\Official-x64-Node\node.exe"
   [Runtime.InteropServices.RuntimeInformation]::OSArchitecture
   [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
   & $python -c "import platform, struct, sys; print(sys.executable); print(sys.version); print(platform.machine()); print(struct.calcsize('P') * 8)"
   & $node -p "JSON.stringify({execPath: process.execPath, arch: process.arch, version: process.version})"
   ```

4. If the version or Python packaging metadata changed, rerun `.\scripts\bootstrap.ps1` for x64
   before building. Confirm the editable distribution metadata and frontend versions match
   `APP_VERSION`:

   ```powershell
   .venv-x64\Scripts\python.exe -c "import importlib.metadata; print(importlib.metadata.version('virelo'))"
   .venv-x64\Scripts\python.exe -c "from virelo.app.config import APP_VERSION; print(APP_VERSION)"
   Get-Content frontend\package.json | ConvertFrom-Json | Select-Object -ExpandProperty version
   ```

5. Update `CHANGELOG.md` with only verified user-visible changes. Keep new work under
   `[Unreleased]` until the release version and date are finalized.

6. Retain the exact dependency inventory written by bootstrap. The constraints control third-party
   Python package selection, but the selected CPython patch release and its bundled pip are also
   part of the recorded build environment; the process is auditable, not bit-for-bit hermetic.

   ```powershell
   .venv-x64\Scripts\python.exe -m pip freeze --all
   Get-Content build\x64\pip-freeze.txt
   ```

7. Run the full frontend audit and the production-only audit. Classify any finding before release:

   ```powershell
   Push-Location frontend
   npm audit
   npm audit --omit=dev
   Pop-Location
   ```

## Build x64

Run on x64 Windows, or in x64 emulation on Windows 11 ARM64:

```powershell
$python = "C:\Path\To\Official-x64-Python\python.exe"
$node = "C:\Path\To\Official-x64-Node\node.exe"
.\scripts\bootstrap.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\build-installer.ps1 -Architecture x64 -PythonExecutable $python -NodeExecutable $node
.\scripts\verify-release.ps1 -Architecture x64
```

Expected outputs:

- `dist/x64/Virelo/Virelo.exe`
- `build/x64/Virelo/warn-Virelo.txt`
- `build/x64/Virelo/xref-Virelo.html`
- `installer/dist/VireloSetup-<version>-x64.exe`

## Native ARM64 Release Status

Do not create or publish a native ARM64 release from the current dependency set. Published Windows
ARM64 PySide6 wheels omit the Qt WebEngine bindings, helper process, and resources required by
Virelo. The supported Windows-on-ARM release path is the verified x64 installer running through
x64 emulation.

A future capability check may use official ARM64 Python and Node processes, but it must stop at the
first missing import or runtime component. Native release work can resume only after the isolated
imports, PyInstaller hook, Qt deployment audit, recursive PE scan, source smoke test, frozen smoke
test, installer gate, and physical Surface checklist all pass. Never rename an x64 artifact as
ARM64.

The reviewed upstream boundary is stored in
`requirements/arm64-webengine-contract.json`. The `ARM64 upstream watch` workflow is advisory: a
failed scheduled or manual run means that official PyPI head differs from the reviewed contract, not
that native packaging is safe. Download its `virelo-arm64-upstream-watch` report and inspect the
candidate filename, version, published and computed SHA-256 values, and required and WebEngine ZIP
entries.

To unfreeze native ARM64 after a candidate includes the required payload:

1. Review the candidate report and the official PyPI release files. Do not install or execute the
   candidate as part of this metadata review.
2. Update the four exact cohort pins in `requirements/build-constraints.txt` together:
   `PySide6`, `PySide6-Addons`, `PySide6-Essentials`, and `shiboken6`.
3. Update the reviewed version, exact ARM64 wheel filename and tag, SHA-256, expected status, and
   reason code in `requirements/arm64-webengine-contract.json`.
4. Run `python -I scripts/verify_arm64_webengine_contract.py`, then push the change so the native
   Windows runner installs that exact wheel and runs the capability probe. Do not bypass a
   contradiction between the installed payload and the contract.
5. Resume release work only if the ARM64 PyInstaller build, Qt deployment audit, recursive PE scan,
   source and frozen WebEngine smoke tests, installer gate, fresh-install check, and physical
   Windows 11 ARM64 checklist all pass.

## Required Automated Evidence

For the x64 target, retain the architecture, dependency, smoke, and PyInstaller reports produced
under `build/x64/`. Confirm all of the following:

- The isolated PySide6 and pywin32/comtypes import preflights pass.
- `python-constraints.json` proves that every installed third-party package has an exact matching
  constraint and that no stale constraint remains.
- Python and pip report the intended process and wheel architecture.
- No Qt, ICU, OpenSSL, Python, or VC runtime dependency resolves from Conda, Miniforge, or an
  unrelated tool installation.
- PyInstaller's PySide6 Qt information probe succeeds.
- `qwindows.dll`, `QtWebEngineProcess.exe`, WebEngine resources, WebEngine locales, required Qt
  DLLs, and PySide/Shiboken extensions exist in the final bundle.
- PE verification matches the target for Python, the Python DLL, `QtCore.pyd`, `Qt6Core.dll`,
  `QtWebEngineProcess.exe`, `pythoncom`, `pywintypes`, `Virelo.exe`, and all recursively scanned
  loadable payload binaries.
- The source and frozen smoke reports both succeed.
- The installer filename contains the version and architecture, and its source tree matches the
  declared architecture.
- `Virelo.exe` and the installer embed file and product versions matching `APP_VERSION`.
- The frozen bundle and installer contain the repository's `LICENSE` file.

Inspect `warn-Virelo.txt`, `xref-Virelo.html`, the analysis table of contents, and `_internal`.
Document Windows API-set and operating-system DLL warnings as benign only after confirming the
supported Windows versions supply them. Treat missing non-system dependencies and unrelated DLL
search-path resolutions as actionable.

## Physical Surface Checklist

Run the verified x64 installer on a current Windows 11 ARM64 Surface through x64 emulation.

- Launch the installer and confirm the x64 payload is accepted through x64 emulation.
- Launch Virelo and confirm the expected UAC prompt occurs once per launch, without an elevation
  loop during `--smoke-test`.
- In Task Manager, add the **Architecture** column and confirm Virelo reports `x64`. This is the
  expected architecture for the supported Windows-on-ARM release.
- Confirm the main window, system tray icon, tray menu, minimize behavior, and exit behavior.
- Capture and use the configured global hotkey.
- Snap and restore ordinary resizable windows.
- Test windows owned by `GoogleDriveFS.exe` and `LightBulb.exe`. Confirm Virelo always centers
  those known resize-hostile windows at their current size without first requesting a resize. Also
  test an otherwise resizable window that rejects or alters a requested size, and confirm Virelo
  restores its original size before centering it.
- Test monitors with different scaling values and, when available, a monitor left of or above the
  primary display. Confirm centering, resizing, and restore geometry at each DPI.
- Open several File Explorer directories in Details view and confirm all visible columns autosize.
  Include local, network, cloud-backed, empty, and long-filename folders where available.
- Apply and reset the default folder view only after file copies, moves, and deletions finish. If
  testing over-the-shoulder UAC with another administrator's credentials, confirm Virelo refuses
  the per-user registry change instead of writing the administrator profile.
- Enable **Run at startup**, sign out and back in, and confirm the per-user startup shortcut starts
  Virelo. Leave it enabled for the uninstall trial and confirm a normal same-account UAC uninstall
  removes that account's startup shortcut before deleting the application.
- Uninstall silently and interactively in separate trials. Confirm application files, Start menu
  shortcuts, and the optional common desktop shortcut are removed. Confirm per-user settings and
  Explorer recovery backups remain available as intended. Also test over-the-shoulder elevation,
  if available, and record that Inno Setup cannot execute uninstall cleanup as the original user;
  the original profile's startup link then requires manual removal.
- Reinstall the x64 package and repeat the smoke test to detect stale or partially removed files.

Record the Windows build number, Surface model, display topology and scaling, installer SHA-256,
test time, Task Manager architecture result, and pass/fail result for every checklist item.

## Release Boundary

An Inno Setup or PyInstaller zero exit code is only one input. Do not release when an import hook,
runtime load, required-file check, PE scan, source smoke test, frozen smoke test, or installer gate
fails. A smoke process that exceeds the 120-second outer timeout is a failure even if it wrote a
partial report. Do not rename an x64-emulated artifact to ARM64.
