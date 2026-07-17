param(
    [ValidateSet("auto", "x64", "arm64")]
    [string] $Architecture = "auto",

    [string] $PythonExecutable,

    [string] $NodeExecutable,

    [switch] $SkipFrontendTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. "$PSScriptRoot\build-common.ps1"

$root = Get-VireloProjectRoot
$targetArchitecture = if ($Architecture -eq "auto") {
    Resolve-VireloArchitecture `
        -Architecture $Architecture `
        -PythonExecutable $PythonExecutable `
        -PreferExistingEnvironment
}
else {
    $Architecture
}
$version = Get-VireloAppVersion $root
$staleDirectories = @(
    (Join-Path $root "build\$targetArchitecture\Virelo"),
    (Join-Path $root "dist\$targetArchitecture\Virelo")
)
$staleFiles = @(
    (Join-Path $root "installer\dist\VireloSetup-$version-$targetArchitecture.exe"),
    (Join-Path $root "installer\dist\VireloSetup-$version-$targetArchitecture-manifest.txt"),
    (Join-Path $root "build\$targetArchitecture\installer.json"),
    (Join-Path $root "build\$targetArchitecture\installer-bootstrap-pe.json"),
    (Join-Path $root "build\$targetArchitecture\inno-setup.log"),
    (Join-Path $root "build\$targetArchitecture\pe-report.json"),
    (Join-Path $root "build\$targetArchitecture\pyinstaller-audit.json"),
    (Join-Path $root "build\$targetArchitecture\pyinstaller.log"),
    (Join-Path $root "build\$targetArchitecture\qt-deployment.json"),
    (Join-Path $root "build\$targetArchitecture\smoke-frozen.json"),
    (Join-Path $root "build\$targetArchitecture\smoke-source.json")
)
Write-Host "[build-app] Invalidating stale $targetArchitecture release artifacts..."
foreach ($staleDirectory in $staleDirectories) {
    Remove-VireloWorkspacePath -Root $root -Path $staleDirectory -Recurse
}
foreach ($staleFile in $staleFiles) {
    Remove-VireloWorkspacePath -Root $root -Path $staleFile
}

$context = Get-VireloBuildContext `
    -Architecture $targetArchitecture `
    -PythonExecutable $PythonExecutable
Push-Location -LiteralPath $context.Root
try {
    if (-not (Test-Path -LiteralPath "Virelo.spec" -PathType Leaf)) {
        throw "Virelo.spec was not found in the project root."
    }

    $node = Resolve-VireloNodeExecutable $NodeExecutable
    $nodeDetails = Get-VireloNodeDetails $node
    if ($nodeDetails.architecture -ne $context.Architecture) {
        throw "Node.js is $($nodeDetails.architecture), but the application target is $($context.Architecture). Pass a matching -NodeExecutable."
    }

    Write-VireloAdministratorWarning
    Write-Host "[build-app] Target architecture: $($context.Architecture)."
    Write-Host "[build-app] Python: $($context.Python)."
    Write-Host "[build-app] Work path: $($context.WorkPath)."
    Write-Host "[build-app] Bundle path: $($context.BundlePath)."

    New-Item -ItemType Directory -Force -Path $context.BuildRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $context.DistRoot | Out-Null

    $savedEnvironment = Start-VireloSanitizedEnvironment `
        -PythonExecutable $context.Python `
        -NodeExecutable $node
    $buildSucceeded = $false
    try {
        & "$PSScriptRoot\build-frontend.ps1" `
            -Architecture $context.Architecture `
            -PythonExecutable $context.Python `
            -NodeExecutable $node `
            -SkipTests:$SkipFrontendTests
        if ($LASTEXITCODE -ne 0) {
            throw "The architecture-safe frontend build failed."
        }

        Invoke-VireloPreflight -Context $context -Mode full

        Remove-Item -LiteralPath $context.SourceSmokeReport -Force -ErrorAction SilentlyContinue
        Write-Host "[build-app] Running the source smoke test..."
        $sourceSmokeExitCode = Invoke-VireloBoundedProcess `
            -FilePath $context.Python `
            -ArgumentList @(
            "-I", "-m", "virelo", "--smoke-test", "--smoke-report",
            "`"$($context.SourceSmokeReport)`""
        ) `
            -TimeoutSeconds 120 `
            -Hidden
        if ($sourceSmokeExitCode -ne 0 -or
            -not (Test-Path -LiteralPath $context.SourceSmokeReport -PathType Leaf)) {
            throw "The source smoke test failed or did not write its JSON report."
        }
        $sourceSmoke = Get-Content -LiteralPath $context.SourceSmokeReport -Raw | ConvertFrom-Json
        if ([int] $sourceSmoke.exitCode -ne 0 -or [bool] $sourceSmoke.frozen) {
            throw "The source smoke report is invalid or reports a failure."
        }

        Remove-Item -LiteralPath $context.PyInstallerLog -Force -ErrorAction SilentlyContinue
        Write-Host "[build-app] Running PyInstaller from the verified $($context.Architecture) interpreter..."
        $pyInstallerArguments = @(
            "-I", "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            "--log-level", "INFO",
            "--workpath", $context.BuildRoot,
            "--distpath", $context.DistRoot,
            "Virelo.spec"
        )
        $pyInstallerExitCode = Invoke-VireloNativeCommand `
            -FilePath $context.Python `
            -ArgumentList $pyInstallerArguments `
            -TranscriptPath $context.PyInstallerLog
        if ($pyInstallerExitCode -ne 0) {
            throw "PyInstaller failed with exit code $pyInstallerExitCode."
        }

        $transcript = Get-Content -LiteralPath $context.PyInstallerLog -Raw
        $fatalPatterns = @(
            "QtLibraryInfo\(PySide6\): failed to obtain Qt library info",
            "failed to obtain Qt library info",
            "DLL load failed while importing QtCore"
        )
        foreach ($pattern in $fatalPatterns) {
            if ($transcript -match $pattern) {
                throw "PyInstaller reported a fatal Qt hook/import failure even though it returned success: $pattern."
            }
        }

        $frozenExe = Join-Path $context.BundlePath "Virelo.exe"
        if (-not (Test-Path -LiteralPath $frozenExe -PathType Leaf)) {
            throw "PyInstaller returned success, but $frozenExe is missing."
        }

        $pythonPrefix = (& $context.Python -I -c "import sys; print(sys.prefix)" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Python failed while resolving sys.prefix for PyInstaller provenance verification."
        }
        $pythonBasePrefix = (& $context.Python -I -c "import sys; print(sys.base_prefix)" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Python failed while resolving sys.base_prefix for PyInstaller provenance verification."
        }
        $auditReport = Join-Path $context.BuildRoot "pyinstaller-audit.json"
        & $context.Python scripts\audit_pyinstaller.py `
            --architecture $context.Architecture `
            --build-dir $context.WorkPath `
            --bundle $context.BundlePath `
            --python-prefix $pythonPrefix `
            --python-base-prefix $pythonBasePrefix `
            --transcript $context.PyInstallerLog `
            --report $auditReport
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller provenance, warning, or analysis-table verification failed."
        }

        & $context.Python scripts\verify_qt_deployment.py `
            --architecture $context.Architecture `
            --bundle $context.BundlePath `
            --report $context.QtReport
        if ($LASTEXITCODE -ne 0) {
            throw "The frozen Qt platform/WebEngine deployment is incomplete or has the wrong architecture."
        }

        & $context.Python scripts\pe_arch.py `
            --expected $context.Architecture `
            --recursive `
            --json $context.PeReport `
            $context.BundlePath
        if ($LASTEXITCODE -ne 0) {
            throw "The frozen payload contains a missing, unknown, or cross-architecture PE binary."
        }

        Remove-Item -LiteralPath $context.FrozenSmokeReport -Force -ErrorAction SilentlyContinue
        Write-Host "[build-app] Running the frozen smoke test..."
        $frozenSmokeExitCode = Invoke-VireloBoundedProcess `
            -FilePath $frozenExe `
            -ArgumentList @("--smoke-test", "--smoke-report", "`"$($context.FrozenSmokeReport)`"") `
            -TimeoutSeconds 120 `
            -Hidden
        if ($frozenSmokeExitCode -ne 0) {
            throw "The frozen smoke test failed with exit code $frozenSmokeExitCode."
        }
        if (-not (Test-Path -LiteralPath $context.FrozenSmokeReport -PathType Leaf)) {
            throw "The windowed frozen executable did not write its smoke report."
        }
        $frozenSmoke = Get-Content -LiteralPath $context.FrozenSmokeReport -Raw | ConvertFrom-Json
        if ([int] $frozenSmoke.exitCode -ne 0 -or -not [bool] $frozenSmoke.frozen) {
            throw "The frozen smoke report is invalid or reports a failure."
        }

        $head = (& git -C $context.Root rev-parse HEAD | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "git rev-parse HEAD failed while creating release evidence."
        }
        $dirty = [bool] ((& git -C $context.Root status --porcelain=v1 --untracked-files=all | Out-String).Trim())
        if ($LASTEXITCODE -ne 0) {
            throw "git status failed while creating release evidence."
        }
        $payloadFingerprint = Get-VireloDirectoryFingerprint `
            -Directory $context.BundlePath `
            -ExcludeNames @(".release.json")
        $manifest = [ordered]@{
            schemaVersion             = 2
            application               = "Virelo"
            version                   = $version
            architecture              = $context.Architecture
            sourceCommit              = $head
            sourceDirty               = $dirty
            sourceFingerprint         = Get-VireloSourceFingerprint $context.Root
            payloadFingerprint        = $payloadFingerprint
            pythonExecutable          = $context.Python
            pythonProcessArchitecture = $context.PythonDetails.architecture
            pythonVersion             = $context.PythonDetails.version
            nodeExecutable            = $nodeDetails.executable
            nodeProcessArchitecture   = $nodeDetails.architecture
            nodeVersion               = $nodeDetails.version
            packageLockSha256         = (Get-FileHash -Algorithm SHA256 -LiteralPath "frontend\package-lock.json").Hash.ToLowerInvariant()
            specSha256                = (Get-FileHash -Algorithm SHA256 -LiteralPath "Virelo.spec").Hash.ToLowerInvariant()
            environmentReportSha256   = (Get-FileHash -Algorithm SHA256 -LiteralPath $context.EnvironmentReport).Hash.ToLowerInvariant()
            peReport                  = $context.PeReport
            qtReport                  = $context.QtReport
            sourceSmokeReport         = $context.SourceSmokeReport
            frozenSmokeReport         = $context.FrozenSmokeReport
            builtAtUtc                = [DateTime]::UtcNow.ToString("o")
        }
        $manifest | ConvertTo-Json -Depth 5 | Set-Content `
            -LiteralPath (Join-Path $context.BundlePath ".release.json") `
            -Encoding utf8
        $buildSucceeded = $true
    }
    finally {
        if (-not $buildSucceeded) {
            try {
                Remove-VireloWorkspacePath `
                    -Root $context.Root `
                    -Path $context.BundlePath `
                    -Recurse
            }
            catch {
                Write-Warning "Failed to remove an incomplete frozen bundle: $($_.Exception.Message)."
            }
        }
        Restore-VireloEnvironment $savedEnvironment
    }
}
finally {
    Pop-Location
}

Write-Host "[build-app] OK: $($context.BundlePath) is verified as $($context.Architecture)."
