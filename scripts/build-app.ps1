$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

# --- Precondition checks ---
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw ".venv not found. Run scripts\bootstrap.ps1 first."
}

if (-not (Test-Path "Virelo.spec")) {
    throw "Virelo.spec not found in project root."
}

# --- Build frontend first ---
Write-Host "[build-app] Building frontend..."
& "$PSScriptRoot\build-frontend.ps1"
if ($LASTEXITCODE -ne 0) { throw "build-frontend.ps1 failed" }

# --- Run PyInstaller ---
Write-Host "[build-app] Running PyInstaller..."
& ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "Virelo.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

# --- Postcondition check ---
if (-not (Test-Path "dist\Virelo\Virelo.exe")) {
    throw "Build failed: dist\Virelo\Virelo.exe not found"
}

Write-Host "[build-app] OK: dist/Virelo/Virelo.exe exists"
