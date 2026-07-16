$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

Write-Host "[verify-release] Checking build artifacts..."

$errors = @()

# --- Read expected version ---
$versionMatch = Select-String -Path "virelo\app\config.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) {
    $errors += "APP_VERSION not found in virelo/app/config.py"
} else {
    $AppVersion = $versionMatch.Matches.Groups[1].Value
    Write-Host "[verify-release] Expected version: $AppVersion"
}

# --- Check frontend build ---
if (-not (Test-Path "frontend\dist\index.html")) {
    $errors += "Missing: frontend\dist\index.html"
} else {
    Write-Host "[verify-release] OK: frontend/dist/index.html"
}

# --- Check PyInstaller output ---
if (-not (Test-Path "dist\Virelo\Virelo.exe")) {
    $errors += "Missing: dist\Virelo\Virelo.exe"
} else {
    Write-Host "[verify-release] OK: dist/Virelo/Virelo.exe"
}

# --- Check installer output ---
if (-not (Test-Path "installer\dist\VireloSetup.exe")) {
    $errors += "Missing: installer\dist\VireloSetup.exe"
} else {
    Write-Host "[verify-release] OK: installer/dist/VireloSetup.exe"
}

# --- Check Virelo.spec exists ---
if (-not (Test-Path "Virelo.spec")) {
    $errors += "Missing: Virelo.spec"
} else {
    Write-Host "[verify-release] OK: Virelo.spec"
}

# --- Check no stale name ---
if (Test-Path "Windows Toolbox.spec") {
    $errors += "Stale file found: Windows Toolbox.spec (should have been renamed to Virelo.spec)"
}

# --- Version cross-check (config.py vs package.json) ---
$pkgJson = Get-Content "frontend\package.json" | ConvertFrom-Json
$pkgJsonVersion = $pkgJson.version
if ($AppVersion -ne $pkgJsonVersion) {
    $errors += "Version mismatch: config.py=$AppVersion, package.json=$pkgJsonVersion"
} else {
    Write-Host "[verify-release] OK: Versions match ($AppVersion)"
}

# --- Version cross-check (Virelo.spec regex vs config.py) ---
# The spec file parses APP_VERSION via regex at build time. Apply the same regex here
# so a spec that silently fails to parse the version cannot go unnoticed.
if (Test-Path "Virelo.spec") {
    $specRegexLine = Select-String -Path "Virelo.spec" -Pattern "re\.search\(r'([^']+)'"
    if ($specRegexLine) {
        $specPattern = $specRegexLine.Matches.Groups[1].Value
        $configText = Get-Content "virelo\app\config.py" -Raw
        $specParse = [regex]::Match($configText, $specPattern)
        if (-not $specParse.Success) {
            $errors += "Virelo.spec version regex does not match virelo/app/config.py"
        } elseif ($specParse.Groups[1].Value -ne $AppVersion) {
            $errors += "Version mismatch: config.py=$AppVersion, Virelo.spec parse=$($specParse.Groups[1].Value)"
        } else {
            Write-Host "[verify-release] OK: Virelo.spec regex parses version $AppVersion"
        }
    } else {
        Write-Host "[verify-release] WARNING: Could not locate the version regex in Virelo.spec, skipping spec parse check"
    }
}

# --- Version cross-check (installed package metadata vs config.py) ---
# The package version is dynamic in pyproject.toml and resolves from APP_VERSION.
# This check is skipped with a warning when no venv exists.
$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $installedVersion = (& $venvPython -c "import importlib.metadata; print(importlib.metadata.version('virelo'))" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[verify-release] WARNING: Could not read the installed virelo package version, skipping metadata check"
    } elseif ($installedVersion -ne $AppVersion) {
        $errors += "Version mismatch: config.py=$AppVersion, installed package=$installedVersion"
    } else {
        Write-Host "[verify-release] OK: Installed package version matches ($AppVersion)"
    }
} else {
    Write-Host "[verify-release] WARNING: .venv not found, skipping installed package version check"
}

# --- Bundled icon.ico in dist/ (PyInstaller 6 onedir places datas under _internal/) ---
if (-not (Test-Path "dist\Virelo\_internal\icon.ico")) {
    $errors += "Missing: dist\Virelo\_internal\icon.ico"
} else {
    Write-Host "[verify-release] OK: dist/Virelo/_internal/icon.ico"
}

# --- Bundled frontend/dist/ in dist/ (PyInstaller 6 onedir places datas under _internal/) ---
if (-not (Test-Path "dist\Virelo\_internal\frontend\dist\index.html")) {
    $errors += "Missing: dist\Virelo\_internal\frontend\dist\index.html"
} else {
    Write-Host "[verify-release] OK: dist/Virelo/_internal/frontend/dist/index.html"
}

# --- No stale naming in dist/ ---
$staleFiles = Get-ChildItem "dist\Virelo" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "(?i)windows.toolbox|(?i)toolbox" }
if ($staleFiles) {
    $errors += "Stale naming found in dist/: $($staleFiles.Name -join ', ')"
} else {
    Write-Host "[verify-release] OK: No stale naming in dist/"
}

# --- Freshness: the built exe must be newer than the newest tracked source ---
# Guards against shipping a stale build whose version string still matches.
$exePath = "dist\Virelo\Virelo.exe"
if (Test-Path $exePath) {
    $exeTime = (Get-Item $exePath).LastWriteTimeUtc
    $newestSource = Get-ChildItem -Recurse -File -Include *.py, *.jsx, *.js, *.css `
        -Path "virelo", "frontend\src" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($newestSource -and $newestSource.LastWriteTimeUtc -gt $exeTime) {
        $errors += "Stale build: $exePath predates $($newestSource.FullName). Rebuild before releasing."
    } else {
        Write-Host "[verify-release] OK: Build is newer than tracked source"
    }
}

# --- Report ---
if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "[verify-release] FAILED: $($errors.Count) issue(s) found:" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host "  - $err" -ForegroundColor Red
    }
    throw "Release verification failed"
}

Write-Host ""
Write-Host "[verify-release] PASSED: All artifacts verified" -ForegroundColor Green
