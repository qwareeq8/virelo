param(
    [ValidateSet("x64", "arm64", "all")]
    [string] $Architecture = "all",

    [switch] $RemoveEnvironments,

    [switch] $RemoveFrontendDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. "$PSScriptRoot\build-common.ps1"

$root = Get-VireloProjectRoot
Push-Location -LiteralPath $root
try {

    function Remove-WorkspacePath {
        param(
            [Parameter(Mandatory)]
            [string] $Path
        )

        Remove-VireloWorkspacePath -Root $root -Path $Path -Recurse
    }

    $architectures = if ($Architecture -eq "all") { @("x64", "arm64") } else { @($Architecture) }
    foreach ($targetArchitecture in $architectures) {
        Remove-WorkspacePath "build\$targetArchitecture"
        Remove-WorkspacePath "dist\$targetArchitecture"

        foreach ($installerPattern in @(
                "VireloSetup-*-$targetArchitecture.exe",
                "VireloSetup-*-$targetArchitecture-manifest.txt"
            )) {
            Get-ChildItem -LiteralPath (Join-Path $root "installer\dist") `
                -Filter $installerPattern `
                -File `
                -ErrorAction SilentlyContinue | ForEach-Object {
                Remove-WorkspacePath $_.FullName.Substring($root.Length).TrimStart([char[]] @('\', '/'))
            }
        }

        if ($RemoveEnvironments) {
            Remove-WorkspacePath ".venv-$targetArchitecture"
        }
    }

    if ($Architecture -eq "all") {
        # Remove all qualified, legacy, and diagnostic outputs only when the caller
        # explicitly selects every architecture.
        Remove-WorkspacePath "build"
        Remove-WorkspacePath "dist"
        Remove-WorkspacePath "installer\dist"
        Remove-WorkspacePath "frontend\dist"
        foreach ($cachePath in @(".pytest_cache", ".ruff_cache", ".mypy_cache")) {
            try {
                Remove-WorkspacePath $cachePath
            }
            catch {
                # Test/lint caches are never release inputs. A cache owned by a
                # different Windows token must not block removal of environments
                # and architecture-qualified release outputs.
                Write-Warning "Could not remove optional cache '$cachePath': $($_.Exception.Message)."
            }
        }
        if ($RemoveEnvironments) {
            Remove-WorkspacePath ".venv"
        }
        if ($RemoveFrontendDependencies) {
            Remove-WorkspacePath "frontend\node_modules"
        }
    }

    Get-ChildItem -LiteralPath $root -Filter "*.spec.bak" -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-WorkspacePath $_.FullName.Substring($root.Length).TrimStart([char[]] @('\', '/'))
        }

    foreach ($sourceDirectory in @("virelo", "tests", "scripts")) {
        Get-ChildItem -LiteralPath (Join-Path $root $sourceDirectory) `
            -Recurse `
            -Filter "__pycache__" `
            -Directory `
            -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-WorkspacePath $_.FullName.Substring($root.Length).TrimStart([char[]] @('\', '/'))
        }
    }

    $environmentStatus = if ($RemoveEnvironments) { "were" } else { "were not" }
    Write-Host "[clean] OK: Removed $Architecture build outputs. Environments $environmentStatus removed."
}
finally {
    Pop-Location
}
