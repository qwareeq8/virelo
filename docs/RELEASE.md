# Virelo Release Checklist

## Pre-Release

1. **Update version** in `virelo/app/config.py`:
   ```python
   APP_VERSION = "x.y.z"
   ```
   This is the single source of truth. Build scripts propagate it automatically.

2. **Sync frontend version**:
   ```powershell
   cd frontend
   npm version x.y.z --no-git-tag-version
   ```

3. **Verify versions match**:
   ```powershell
   # CI also checks this automatically
   python -c "import re, json; py=re.search(r'APP_VERSION\s*=\s*\`"([^\`"]+)\`"', open('virelo/app/config.py').read()).group(1); js=json.load(open('frontend/package.json'))['version']; assert py==js, f'{py} != {js}'; print(f'Versions match: {py}')"
   ```

## Build

4. **Clean previous build**:
   ```powershell
   scripts/clean.ps1
   ```

5. **Build installer** (runs entire pipeline):
   ```powershell
   scripts/build-installer.ps1
   ```

6. **Run smoke test**:
   ```powershell
   python -m virelo --smoke-test
   ```

7. **Run release verification**:
   ```powershell
   scripts/verify-release.ps1
   ```

   This checks:
   - `dist/Virelo/Virelo.exe` exists
   - `installer/dist/VireloSetup.exe` exists
   - `Virelo.spec` exists
   - No stale legacy naming from before the rename
   - Version in `config.py` matches `frontend/package.json`
   - Version regex in `Virelo.spec` parses the same version from `config.py`
   - Installed package version matches `config.py` (skipped with a warning if `.venv` is absent)
   - Bundled `icon.ico` exists in `dist/Virelo/_internal/`
   - Bundled `frontend/dist/index.html` exists in `dist/Virelo/_internal/`
   - No stale naming in `dist/` output

## Post-Build Verification

8. **Manual verification**:
   - Launch `dist/Virelo/Virelo.exe`
   - Verify window dragging works (drag from title bar)
   - Verify window resizing works (drag from edges/corners)
   - Verify minimize and close buttons work
   - Verify snap functionality with configured hotkey
   - Verify settings save/load cycle
   - Verify system tray icon and menu

9. **Installer verification**:
   - Run `installer/dist/VireloSetup.exe`
   - Complete installation
   - Launch from Start Menu shortcut
   - Verify same functionality as step 8

## Release

10. **Commit and tag**:
    ```powershell
    git add -A
    git commit -m "release: vx.y.z"
    git tag vx.y.z
    ```

11. **Push**:
    ```powershell
    git push origin main --tags
    ```
