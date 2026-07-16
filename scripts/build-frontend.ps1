$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

# --- Precondition checks ---
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js not found. Install from https://nodejs.org" }

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) { throw "npm not found. Install Node.js from https://nodejs.org" }

Write-Host "[build-frontend] Node $(node --version), npm $(npm --version)"

# --- Read version from virelo/app/config.py ---
$versionMatch = Select-String -Path "virelo\app\config.py" -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) { throw "APP_VERSION not found in virelo/app/config.py" }
$env:VITE_APP_VERSION = $versionMatch.Matches.Groups[1].Value
Write-Host "[build-frontend] Version: $env:VITE_APP_VERSION"

# --- Install dependencies if needed, then build ---
# The try/finally keeps the location stack balanced when a step throws.
Push-Location frontend
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "[build-frontend] Installing dependencies..."
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    }

    # --- Build ---
    Write-Host "[build-frontend] Building frontend..."
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Pop-Location
}

# --- Postcondition check ---
if (-not (Test-Path "frontend\dist\index.html")) {
    throw "Frontend build failed: frontend\dist\index.html not found"
}

Write-Host "[build-frontend] OK: frontend/dist/index.html exists"
