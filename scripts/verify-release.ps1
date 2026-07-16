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

# --- Bundled icon.ico in dist/ ---
if (-not (Test-Path "dist\Virelo\icon.ico")) {
    $errors += "Missing: dist\Virelo\icon.ico"
} else {
    Write-Host "[verify-release] OK: dist/Virelo/icon.ico"
}

# --- Bundled frontend/dist/ in dist/ ---
if (-not (Test-Path "dist\Virelo\frontend\dist\index.html")) {
    $errors += "Missing: dist\Virelo\frontend\dist\index.html"
} else {
    Write-Host "[verify-release] OK: dist/Virelo/frontend/dist/index.html"
}

# --- No stale naming in dist/ ---
$staleFiles = Get-ChildItem "dist\Virelo" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "(?i)windows.toolbox|(?i)toolbox" }
if ($staleFiles) {
    $errors += "Stale naming found in dist/: $($staleFiles.Name -join ', ')"
} else {
    Write-Host "[verify-release] OK: No stale naming in dist/"
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
