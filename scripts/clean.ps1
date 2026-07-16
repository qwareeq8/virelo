$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $projectRoot

$targets = @(
    "build",
    "dist",
    "frontend\dist",
    "installer\dist",
    ".pytest_cache",
    ".ruff_cache"
)

foreach ($target in $targets) {
    if (Test-Path $target) {
        Write-Host "[clean] Removing $target"
        Remove-Item -Recurse -Force $target
    }
}

# Clean *.spec.bak files
Get-ChildItem -Filter "*.spec.bak" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "[clean] Removing $($_.Name)"
    Remove-Item -Force $_.FullName
}

# Recursive __pycache__ and *.pyc removal (D-03)
Get-ChildItem -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "[clean] Removing $($_.FullName)"
        Remove-Item -Recurse -Force $_.FullName
    }

Get-ChildItem -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item -Force $_.FullName
    }

Write-Host "[clean] OK: Build artifacts removed"
