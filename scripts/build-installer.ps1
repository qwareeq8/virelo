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

$expectedInnoSetupVersion = "6.7.3"

function Get-VireloInnoSetupCompilerDetails {
    param(
        [Parameter(Mandatory)]
        [string] $CompilerPath,

        [Parameter(Mandatory)]
        [string] $ExpectedVersion,

        [Parameter(Mandatory)]
        [string] $BuildRoot
    )

    $probePath = Join-Path $BuildRoot "inno-setup-version-probe.iss"
    $probeLog = Join-Path $BuildRoot "inno-setup-version-probe.log"
    $probeLines = @(
        "[Setup]",
        "AppId=VireloInnoSetupCompilerProbe",
        "AppName=Virelo Inno Setup Compiler Probe",
        "AppVersion=0",
        "DefaultDirName={tmp}\VireloInnoSetupCompilerProbe",
        "Output=no",
        "OutputDir=$BuildRoot",
        "PrivilegesRequired=lowest",
        "Uninstallable=no"
    )
    $utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines($probePath, $probeLines, $utf8WithoutBom)

    try {
        $probeExitCode = Invoke-VireloNativeCommand `
            -FilePath $CompilerPath `
            -ArgumentList @($probePath) `
            -TranscriptPath $probeLog
        if ($probeExitCode -ne 0) {
            throw "The Inno Setup compiler identity probe failed with exit code $probeExitCode. See $probeLog."
        }
    }
    finally {
        Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue
    }

    $probeTranscript = Get-Content -LiteralPath $probeLog -Raw
    $identityMatch = [regex]::Match(
        $probeTranscript,
        '(?m)^(?<identity>Inno Setup (?<major>\d+) Command-Line Compiler)\r?$'
    )
    $versionMatch = [regex]::Match(
        $probeTranscript,
        '(?m)^Compiler engine version:\s+Inno Setup (?<version>\d+(?:\.\d+){2,3})\r?$'
    )
    if (-not $identityMatch.Success -or -not $versionMatch.Success) {
        throw "The compiler at $CompilerPath did not identify itself as an Inno Setup command-line compiler with a parseable engine version. See $probeLog."
    }

    $identity = $identityMatch.Groups["identity"].Value
    $version = $versionMatch.Groups["version"].Value
    $expectedMajorVersion = $ExpectedVersion.Split('.')[0]
    if ($identityMatch.Groups["major"].Value -ne $expectedMajorVersion -or
        $version -ne $ExpectedVersion) {
        throw "Expected Inno Setup $ExpectedVersion; found '$identity' with engine version $version at $CompilerPath."
    }

    return [pscustomobject]@{
        Identity = $identity
        Version  = $version
        Path     = (Resolve-Path -LiteralPath $CompilerPath).Path
        Sha256   = (Get-FileHash -Algorithm SHA256 -LiteralPath $CompilerPath).Hash.ToLowerInvariant()
    }
}

$root = Get-VireloProjectRoot
$buildLock = Enter-VireloReleaseBuildLock -Root $root
try {
$context = Get-VireloBuildContext `
    -Architecture $Architecture `
    -PythonExecutable $PythonExecutable
$node = Resolve-VireloNodeExecutable $NodeExecutable
$version = Get-VireloAppVersion $context.Root
$installerPath = Join-Path $context.Root "installer\dist\VireloSetup-$version-$($context.Architecture).exe"
$installerManifestPath = Join-Path $context.Root "installer\dist\VireloSetup-$version-$($context.Architecture)-manifest.txt"
$installerEvidencePath = Join-Path $context.BuildRoot "installer.json"
$installerBootstrapPePath = Join-Path $context.BuildRoot "installer-bootstrap-pe.json"
$innoLog = Join-Path $context.BuildRoot "inno-setup.log"
$releaseEvidencePaths = @(
    $installerPath,
    $installerManifestPath,
    $installerEvidencePath,
    $installerBootstrapPePath
)
$installerSucceeded = $false

Push-Location -LiteralPath $context.Root
try {
    # Invalidate old release-looking outputs before any preflight or rebuild can
    # fail. An earlier successful artifact must never masquerade as this run.
    foreach ($releaseEvidencePath in $releaseEvidencePaths) {
        Remove-Item -LiteralPath $releaseEvidencePath -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[build-installer] Building the verified $($context.Architecture) application payload..."
    & "$PSScriptRoot\build-app.ps1" `
        -Architecture $context.Architecture `
        -PythonExecutable $context.Python `
        -NodeExecutable $node `
        -SkipFrontendTests:$SkipFrontendTests
    if ($LASTEXITCODE -ne 0) {
        throw "The application build failed; the installer was not started."
    }

    $manifestPath = Join-Path $context.BundlePath ".release.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "The verified payload manifest is missing: $manifestPath."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.architecture -ne $context.Architecture) {
        throw "The payload manifest is $($manifest.architecture), not $($context.Architecture). Refusing to build a mislabeled installer."
    }

    $isccPath = $env:ISCC_PATH
    if (-not $isccPath) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $isccPath = $candidates | Where-Object {
            $_ -and (Test-Path -LiteralPath $_ -PathType Leaf)
        } | Select-Object -First 1
    }
    if (-not $isccPath) {
        throw "ISCC.exe was not found. Install Inno Setup 6 from its official site or set ISCC_PATH."
    }
    if (-not (Test-Path -LiteralPath $isccPath -PathType Leaf)) {
        throw "ISCC_PATH does not identify an executable file: $isccPath."
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $installerPath) | Out-Null
    Remove-Item -LiteralPath $innoLog -Force -ErrorAction SilentlyContinue

    $savedEnvironment = Start-VireloSanitizedEnvironment `
        -PythonExecutable $context.Python `
        -NodeExecutable $node
    try {
        $compilerDetails = Get-VireloInnoSetupCompilerDetails `
            -CompilerPath $isccPath `
            -ExpectedVersion $expectedInnoSetupVersion `
            -BuildRoot $context.BuildRoot
        Write-Host "[build-installer] $($compilerDetails.Identity) $($compilerDetails.Version): $($compilerDetails.Path)."
        $innoArguments = @(
            "/DMyAppVersion=$version",
            "/DPayloadArchitecture=$($context.Architecture)",
            "installer\virelo.iss"
        )
        $innoExitCode = Invoke-VireloNativeCommand `
            -FilePath $isccPath `
            -ArgumentList $innoArguments `
            -TranscriptPath $innoLog
        if ($innoExitCode -ne 0) {
            throw "Inno Setup failed with exit code $innoExitCode."
        }
    }
    finally {
        Restore-VireloEnvironment $savedEnvironment
    }

    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $installerManifestPath -PathType Leaf)) {
        throw "Inno Setup returned success, but the architecture-qualified installer or output manifest is missing."
    }
    $innoLines = @(Get-Content -LiteralPath $innoLog)
    $innoTranscript = $innoLines -join [Environment]::NewLine
    $warningLines = @(
        $innoLines | Where-Object {
            $_ -match '(?i)\bwarning(?:s|\(s\))?\b' -and
            $_ -notmatch '(?i)\b0\s+warning(?:s|\(s\))?\b'
        }
    )
    if ($warningLines.Count -gt 0) {
        throw "Inno Setup emitted warning text that has not been classified as benign: $($warningLines -join ' | ')."
    }

    $expectedAllowed = if ($context.Architecture -eq "x64") { "x64compatible" } else { "arm64" }
    $expectedMinVersion = if ($context.Architecture -eq "x64") { "10.0.17763" } else { "10.0.22000" }
    $effectiveMarkers = [ordered]@{
        architecture       = "VIRELO_EFFECTIVE_ARCHITECTURE=$($context.Architecture)"
        allowed            = "VIRELO_EFFECTIVE_ALLOWED=$expectedAllowed"
        installIn64BitMode = "VIRELO_EFFECTIVE_64BIT_MODE=$expectedAllowed"
        minVersion         = "VIRELO_EFFECTIVE_MIN_VERSION=$expectedMinVersion"
    }
    foreach ($marker in $effectiveMarkers.Values) {
        if ($innoTranscript -notmatch [regex]::Escape($marker)) {
            throw "Inno Setup did not emit the expected effective configuration marker: $marker."
        }
    }
    $expectedPayloadMarker = 'VIRELO_EFFECTIVE_PAYLOAD=.*[\\/]dist[\\/]' +
    [regex]::Escape($context.Architecture) + '[\\/]Virelo'
    if ($innoTranscript -notmatch $expectedPayloadMarker) {
        throw "Inno Setup did not emit an effective payload path for dist/$($context.Architecture)/Virelo."
    }

    # The Inno bootstrap may be x86 and run under emulation. Record its actual PE
    # machine value without conflating it with the verified application payload.
    & $context.Python scripts\pe_arch.py `
        --json $installerBootstrapPePath `
        $installerPath
    if ($LASTEXITCODE -ne 0) {
        throw "The installer bootstrap is not a valid recognized PE executable."
    }

    $installerEvidence = [ordered]@{
        schemaVersion                   = 4
        architecture                    = $context.Architecture
        architecturesAllowed            = $expectedAllowed
        architecturesInstallIn64BitMode = $expectedAllowed
        compilerIdentity                = $compilerDetails.Identity
        compilerPath                    = $compilerDetails.Path
        compilerSha256                  = $compilerDetails.Sha256
        compilerVersion                 = $compilerDetails.Version
        minVersion                      = $expectedMinVersion
        payloadPath                     = $context.BundlePath
        payloadManifestSha256           = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
        payloadFingerprint              = $manifest.payloadFingerprint
        installerPath                   = $installerPath
        installerSha256                 = (Get-FileHash -Algorithm SHA256 -LiteralPath $installerPath).Hash.ToLowerInvariant()
        outputManifestPath              = $installerManifestPath
        outputManifestSha256            = (Get-FileHash -Algorithm SHA256 -LiteralPath $installerManifestPath).Hash.ToLowerInvariant()
        builtAtUtc                      = [DateTime]::UtcNow.ToString("o")
    }
    $installerEvidence | ConvertTo-Json | Set-Content `
        -LiteralPath $installerEvidencePath `
        -Encoding utf8

    & "$PSScriptRoot\verify-release.ps1" -Architecture $context.Architecture
    if ($LASTEXITCODE -ne 0) {
        throw "Release verification failed after installer creation."
    }

    $installerSucceeded = $true
}
finally {
    if (-not $installerSucceeded) {
        foreach ($releaseEvidencePath in $releaseEvidencePaths) {
            Remove-Item -LiteralPath $releaseEvidencePath -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}

Write-Host "[build-installer] OK: $installerPath contains the verified $($context.Architecture) payload."
}
finally {
    Exit-VireloReleaseBuildLock -Token $buildLock
}
