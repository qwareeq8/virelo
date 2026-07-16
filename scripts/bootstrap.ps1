$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

# --- Precondition checks ---
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python not found. Install from https://www.python.org" }

Write-Host "[bootstrap] Python $(python --version)"

# --- Create .venv if absent ---
if (-not (Test-Path ".venv")) {
    Write-Host "[bootstrap] Creating virtual environment..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
} else {
    Write-Host "[bootstrap] .venv already exists, skipping creation"
}

# --- Install Python dependencies ---
Write-Host "[bootstrap] Installing Python dependencies..."
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed" }

# --- Install frontend dependencies ---
$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Write-Host "[bootstrap] Installing frontend dependencies..."
    Push-Location frontend
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    Pop-Location
} else {
    Write-Host "[bootstrap] WARNING: npm not found, skipping frontend dependencies"
}

Write-Host "[bootstrap] OK: Environment ready"
