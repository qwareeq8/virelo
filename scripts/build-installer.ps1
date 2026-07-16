$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

# --- Build app first (includes frontend build) ---
Write-Host "[build-installer] Building application..."
& "$PSScriptRoot\build-app.ps1"
if ($LASTEXITCODE -ne 0) { throw "build-app.ps1 failed" }

# --- Read version from virelo/app/config.py ---
$versionMatch = Select-String -Path "virelo\app\config.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) { throw "APP_VERSION not found in virelo/app/config.py" }
$AppVersion = $versionMatch.Matches.Groups[1].Value
Write-Host "[build-installer] Version: $AppVersion"

# --- Locate ISCC.exe ---
$IsccPath = $env:ISCC_PATH
if (-not $IsccPath) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $IsccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $IsccPath) {
    throw "ISCC.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php or set ISCC_PATH env var."
}

Write-Host "[build-installer] ISCC: $IsccPath"

# --- Build installer with version ---
Write-Host "[build-installer] Building installer..."
& $IsccPath "/DMyAppVersion=$AppVersion" "installer\virelo.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC.exe failed with exit code $LASTEXITCODE" }

# --- Postcondition check ---
if (-not (Test-Path "installer\dist\VireloSetup.exe")) {
    throw "Installer build failed: installer\dist\VireloSetup.exe not found"
}

Write-Host "[build-installer] OK: installer/dist/VireloSetup.exe ($AppVersion)"
