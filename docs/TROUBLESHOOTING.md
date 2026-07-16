# Troubleshooting Virelo

## Build Issues

### PyInstaller fails with PySide6 import error in Virelo.spec

**Cause:** `virelo/app/config.py` was imported directly in the spec file. The spec runs in
PyInstaller's analysis context where PySide6 may not be importable.

**Fix:** The spec file uses regex to parse `APP_VERSION` from `config.py`. Never add
`from virelo.app.config import ...` to `Virelo.spec`.

### PowerShell build script reports success but the build actually failed

**Cause:** PowerShell's `$ErrorActionPreference = "Stop"` only catches cmdlet errors, not
native command failures (npm, python, pyinstaller, ISCC).

**Fix:** Every external command in build scripts must be followed by:
```powershell
if ($LASTEXITCODE -ne 0) { throw "command failed" }
```

### Vite build injects version as JavaScript expression instead of string

**Cause:** Vite `define` values without `JSON.stringify()` are treated as JS expressions.

**Fix:** Always use `JSON.stringify()` in `vite.config.js`:
```javascript
define: { __APP_VERSION__: JSON.stringify(version) }
```

### Inno Setup ignores /D version override

**Cause:** An unconditional `#define` in the `.iss` file overrides the command-line `/D` flag.

**Fix:** Use `#ifndef` guard:
```
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
```

## Runtime Issues

### UAC prompt appears every time the app starts

**Expected behavior.** Virelo requires administrator privileges for global keyboard hooks and
cross-process window manipulation. The app auto-elevates via `ShellExecuteW("runas", ...)`.

### Window cannot be dragged

**Cause:** The frameless window uses `WM_NCHITTEST` to define drag zones. If the title bar
height constant does not match the frontend, dragging may not work.

**Fix:** Ensure `TITLE_BAR_HEIGHT` in `virelo/app/window.py` matches the frontend TitleBar
component height (34px content + 1px border = 35px).

### Window resize breaks on multi-monitor setup

**Cause:** Monitors to the left of or above the primary monitor have negative screen
coordinates. The `WM_NCHITTEST` handler must use signed 16-bit extraction for `lParam`.

**Fix:** Coordinates must use `ctypes.c_short(val).value` for signed decoding, not
unsigned `val & 0xFFFF`.

### Explorer column auto-size not working

**Cause:** Explorer auto-size uses COM automation (`IShellBrowser`, `IFolderView`) which
requires the Explorer window to be in Details view.

**Fix:** Switch the Explorer window to Details view (View menu or Ctrl+Shift+6).

## Smoke Test

### Smoke test fails on QWebEngine construction

**Cause:** QWebEngine may require specific runtime libraries. In a PyInstaller bundle, the
Qt WebEngine process binary must be present.

**Fix:** Verify `dist/Virelo/` contains the QtWebEngineProcess executable and required DLLs.

### Smoke test triggers UAC prompt

**Cause:** The `--smoke-test` flag was not parsed before the admin elevation check.

**Fix:** Ensure `--smoke-test` is parsed before `_is_admin()` in `virelo/app/__main__.py`.
