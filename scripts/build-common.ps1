$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-VireloProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function ConvertTo-VireloArchitecture {
    param(
        [Parameter(Mandatory)]
        [string] $Value
    )

    switch -Regex ($Value.Trim().ToLowerInvariant()) {
        "^(amd64|x86_64|x64|win-amd64)$" { return "x64" }
        "^(arm64|aarch64|win-arm64)$" { return "arm64" }
        default { throw "Unsupported 64-bit process architecture '$Value'. Virelo release builds require x64 or arm64." }
    }
}

function Resolve-VireloPythonExecutable {
    param(
        [string] $PythonExecutable
    )

    if ($PythonExecutable) {
        $explicit = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
        if (-not $explicit) {
            throw "The requested Python executable was not found: $PythonExecutable."
        }
        return $explicit.Source
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw "No Python executable was selected. Pass -PythonExecutable with an official CPython 3.13 python.exe path."
    }

    $selected = (& $launcher.Source -3.13 -I -c "import sys; print(sys.executable)" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $selected) {
        throw "The Python Launcher could not select official CPython 3.13. Pass -PythonExecutable explicitly."
    }
    if (-not (Test-Path -LiteralPath $selected -PathType Leaf)) {
        throw "The Python Launcher returned a missing executable: $selected."
    }
    return (Resolve-Path -LiteralPath $selected).Path
}

function Get-VireloPythonProcessArchitecture {
    param(
        [Parameter(Mandatory)]
        [string] $PythonExecutable
    )

    # Use only Python single-quoted literals here. Windows PowerShell 5.1 can
    # strip embedded double quotes from a native program's multiline -c value.
    $code = "import json,platform,struct,sys,sysconfig; print(json.dumps({'executable':sys.executable,'machine':platform.machine(),'pointer_bits':struct.calcsize('P')*8,'platform':sysconfig.get_platform(),'version':sys.version,'base_prefix':sys.base_prefix}))"
    $raw = (& $PythonExecutable -I -c $code 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect Python '$PythonExecutable': $raw."
    }
    $details = $raw | ConvertFrom-Json
    if ([int] $details.pointer_bits -ne 64) {
        throw "Virelo release builds require a 64-bit Python process; '$PythonExecutable' reports $($details.pointer_bits)-bit."
    }

    # Windows x64 emulation on ARM64 does not use WOW64. In that environment,
    # platform.machine() may report ARM64 even though Python and its extension
    # ABI are x64, so the executable PE header is the authoritative build input.
    $peRaw = (& $PythonExecutable -I "$PSScriptRoot\pe_arch.py" $PythonExecutable 2>&1 |
            Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect the Python executable PE architecture: $peRaw."
    }
    $peReport = $peRaw | ConvertFrom-Json
    $peFiles = @($peReport.files)
    if ($peFiles.Count -ne 1 -or $peFiles[0].architecture -notin @("x64", "arm64")) {
        throw "The selected Python executable does not have a supported x64 or ARM64 PE architecture."
    }
    $details | Add-Member -NotePropertyName peMachine -NotePropertyValue $peFiles[0].machine_hex
    $details | Add-Member -NotePropertyName architecture -NotePropertyValue $peFiles[0].architecture
    return $details
}

function Resolve-VireloArchitecture {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("auto", "x64", "arm64")]
        [string] $Architecture,

        [string] $PythonExecutable,

        [switch] $PreferExistingEnvironment
    )

    if ($Architecture -ne "auto") {
        if ($PythonExecutable) {
            $selectedArchitecture = (Get-VireloPythonProcessArchitecture $PythonExecutable).architecture
            if ($selectedArchitecture -ne $Architecture) {
                throw "The selected Python process is $selectedArchitecture, but -Architecture $Architecture was requested. Select a matching official CPython interpreter."
            }
        }
        return $Architecture
    }

    if ($PythonExecutable) {
        return (Get-VireloPythonProcessArchitecture $PythonExecutable).architecture
    }

    if ($PreferExistingEnvironment) {
        $root = Get-VireloProjectRoot
        $existing = @(
            @("x64", "arm64") | Where-Object {
                Test-Path -LiteralPath (Join-Path $root ".venv-$_\Scripts\python.exe") -PathType Leaf
            }
        )
        if ($existing.Count -eq 1) {
            return $existing[0]
        }
        if ($existing.Count -gt 1) {
            throw "Both .venv-x64 and .venv-arm64 exist. Specify -Architecture explicitly."
        }
    }

    $basePython = Resolve-VireloPythonExecutable
    return (Get-VireloPythonProcessArchitecture $basePython).architecture
}

function Get-VireloBuildContext {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("auto", "x64", "arm64")]
        [string] $Architecture,

        [string] $PythonExecutable,

        [switch] $Bootstrap,

        [switch] $Provisioning
    )

    $root = Get-VireloProjectRoot
    $basePython = $null
    if ($Bootstrap) {
        $basePython = Resolve-VireloPythonExecutable $PythonExecutable
        $resolvedArchitecture = Resolve-VireloArchitecture $Architecture $basePython
        $activePython = $basePython
    }
    else {
        if ($PythonExecutable) {
            $basePython = Resolve-VireloPythonExecutable $PythonExecutable
            $resolvedArchitecture = Resolve-VireloArchitecture $Architecture $basePython
        }
        else {
            $resolvedArchitecture = Resolve-VireloArchitecture $Architecture -PreferExistingEnvironment
        }
        $venvCandidate = Join-Path $root ".venv-$resolvedArchitecture\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $venvCandidate -PathType Leaf)) {
            $bootstrapHint = ".\scripts\bootstrap.ps1 -Architecture $resolvedArchitecture"
            if ($basePython) {
                $bootstrapHint += " -PythonExecutable `"$basePython`""
            }
            else {
                $bootstrapHint += " -PythonExecutable C:\Path\To\OfficialPython\python.exe"
            }
            throw "Missing architecture-qualified environment '.venv-$resolvedArchitecture'. Run: $bootstrapHint."
        }
        $activePython = (Resolve-Path -LiteralPath $venvCandidate).Path
    }

    $pythonDetails = Get-VireloPythonProcessArchitecture $activePython
    if ($pythonDetails.architecture -ne $resolvedArchitecture) {
        $venvName = ".venv-$resolvedArchitecture"
        throw "$venvName contains $($pythonDetails.architecture) Python, not $resolvedArchitecture. Remove it with 'Remove-Item -Recurse -Force $venvName', then rerun bootstrap with the correct official CPython interpreter."
    }

    $environmentProvenance = $null
    if (-not $Bootstrap -and -not $Provisioning) {
        $environmentProvenance = Assert-VireloEnvironmentProvenance `
            -Root $root `
            -Architecture $resolvedArchitecture `
            -VenvPath (Join-Path $root ".venv-$resolvedArchitecture") `
            -VenvPython $activePython `
            -SelectedPython $basePython
        $basePython = $environmentProvenance.basePythonExecutable
    }

    return [pscustomobject]@{
        Root                  = $root
        Architecture          = $resolvedArchitecture
        VenvPath              = Join-Path $root ".venv-$resolvedArchitecture"
        Python                = $activePython
        BasePython            = $basePython
        PythonDetails         = $pythonDetails
        EnvironmentProvenance = $environmentProvenance
        EnvironmentMarker     = Join-Path $root ".venv-$resolvedArchitecture\.virelo-build-environment.json"
        BuildRoot             = Join-Path $root "build\$resolvedArchitecture"
        WorkPath              = Join-Path $root "build\$resolvedArchitecture\Virelo"
        DistRoot              = Join-Path $root "dist\$resolvedArchitecture"
        BundlePath            = Join-Path $root "dist\$resolvedArchitecture\Virelo"
        EnvironmentReport     = Join-Path $root "build\$resolvedArchitecture\preflight.json"
        PeReport              = Join-Path $root "build\$resolvedArchitecture\pe-report.json"
        QtReport              = Join-Path $root "build\$resolvedArchitecture\qt-deployment.json"
        SourceSmokeReport     = Join-Path $root "build\$resolvedArchitecture\smoke-source.json"
        FrozenSmokeReport     = Join-Path $root "build\$resolvedArchitecture\smoke-frozen.json"
        PyInstallerLog        = Join-Path $root "build\$resolvedArchitecture\pyinstaller.log"
    }
}

function Resolve-VireloNodeExecutable {
    param(
        [string] $NodeExecutable
    )

    $node = if ($NodeExecutable) {
        Get-Command $NodeExecutable -ErrorAction SilentlyContinue
    }
    else {
        Get-Command node.exe -ErrorAction SilentlyContinue
    }
    if (-not $node) {
        throw "Node.js was not found. Install Node.js 24 LTS or pass -NodeExecutable."
    }
    return $node.Source
}

function Get-VireloNodeDetails {
    param(
        [Parameter(Mandatory)]
        [string] $NodeExecutable
    )

    $raw = (& $NodeExecutable -p "JSON.stringify({executable:process.execPath,version:process.version,architecture:process.arch,platform:process.platform})" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect Node.js '$NodeExecutable': $raw."
    }
    $details = $raw | ConvertFrom-Json
    $major = [int] ($details.version -replace '^v(\d+).*$', '$1')
    if ($major -ne 24) {
        throw "Node.js 24 LTS is required for release builds; found $($details.version) at $NodeExecutable."
    }
    $details.architecture = ConvertTo-VireloArchitecture $details.architecture
    return $details
}

function Resolve-VireloNpmExecutable {
    param(
        [Parameter(Mandatory)]
        [string] $NodeExecutable
    )

    $adjacent = Join-Path (Split-Path -Parent $NodeExecutable) "npm.cmd"
    if (Test-Path -LiteralPath $adjacent -PathType Leaf) {
        return $adjacent
    }
    throw "npm.cmd was not found next to the selected Node executable: $NodeExecutable."
}

function Start-VireloSanitizedEnvironment {
    param(
        [Parameter(Mandatory)]
        [string] $PythonExecutable,

        [string] $NodeExecutable
    )

    $names = @(
        "PATH", "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV",
        "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_PROMPT_MODIFIER",
        "CONDA_SHLVL", "CONDA_EXE", "_CONDA_EXE", "CONDA_PYTHON_EXE",
        "_CE_CONDA", "_CE_M",
        "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
        "QTWEBENGINEPROCESS_PATH", "QTWEBENGINE_RESOURCES_PATH",
        "QTWEBENGINE_LOCALES_PATH", "QTWEBENGINE_DICTIONARIES_PATH",
        "QTWEBENGINE_CHROMIUM_FLAGS", "QTWEBENGINE_DISABLE_SANDBOX",
        "QT_QPA_PLATFORM", "QT_QPA_PLATFORMTHEME"
    )
    $saved = @{}
    foreach ($name in $names) {
        $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        $saved[$name] = if ($item) { $item.Value } else { $null }
    }

    $redirectVariables = $names | Where-Object {
        $_ -like "QT*" -or $_ -like "QML*"
    }
    $clearedRedirectVariables = @(
        $redirectVariables | Where-Object { $null -ne $saved[$_] }
    )
    if ($clearedRedirectVariables.Count -gt 0) {
        Write-Host (
            "[environment] Clearing Qt/WebEngine redirect variables for build children: " +
            ($clearedRedirectVariables -join ", ")
        )
    }
    else {
        Write-Host "[environment] No Qt/WebEngine redirect variables were set."
    }

    $pythonDetails = Get-VireloPythonProcessArchitecture $PythonExecutable
    $pathEntries = [System.Collections.Generic.List[string]]::new()
    $pathEntries.Add((Split-Path -Parent $PythonExecutable))
    $pathEntries.Add($pythonDetails.base_prefix)
    if ($NodeExecutable) {
        $pathEntries.Add((Split-Path -Parent $NodeExecutable))
    }
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $pathEntries.Add((Split-Path -Parent $git.Source))
    }
    $pathEntries.Add((Join-Path $env:SystemRoot "System32"))
    $pathEntries.Add($env:SystemRoot)
    $pathEntries.Add((Join-Path $env:SystemRoot "System32\Wbem"))
    $env:PATH = (($pathEntries | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique) -join ";")

    foreach ($name in $names | Where-Object { $_ -notin @("PATH", "VIRTUAL_ENV") }) {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }
    $venvRoot = Split-Path -Parent (Split-Path -Parent $PythonExecutable)
    if ((Split-Path -Leaf $venvRoot) -like ".venv-*") {
        $env:VIRTUAL_ENV = $venvRoot
    }
    else {
        Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    }

    return $saved
}

function Restore-VireloEnvironment {
    param(
        [Parameter(Mandatory)]
        [hashtable] $SavedEnvironment
    )

    foreach ($entry in $SavedEnvironment.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            Remove-Item -LiteralPath "Env:$($entry.Key)" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item -LiteralPath "Env:$($entry.Key)" -Value $entry.Value
        }
    }
}

function Get-VireloStringSha256 {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string] $Value
    )

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        $digest = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    return ([BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
}

function Test-VireloPathEquals {
    param(
        [Parameter(Mandatory)]
        [string] $Left,

        [Parameter(Mandatory)]
        [string] $Right
    )

    $leftPath = [IO.Path]::GetFullPath($Left).TrimEnd([char[]] @('\', '/'))
    $rightPath = [IO.Path]::GetFullPath($Right).TrimEnd([char[]] @('\', '/'))
    return $leftPath.Equals($rightPath, [StringComparison]::OrdinalIgnoreCase)
}

function Get-VireloOfficialPythonIdentity {
    param(
        [Parameter(Mandatory)]
        [string] $PythonExecutable
    )

    $resolved = Resolve-VireloPythonExecutable $PythonExecutable
    $signature = Get-AuthenticodeSignature -LiteralPath $resolved
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
        -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch "Python Software Foundation") {
        throw "Release environments require an Authenticode-valid Python Software Foundation interpreter. '$resolved' is not a verified official CPython executable."
    }

    $details = Get-VireloPythonProcessArchitecture $resolved
    return [pscustomobject]@{
        executable       = $resolved
        sha256           = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolved).Hash.ToLowerInvariant()
        version          = $details.version
        architecture     = $details.architecture
        basePrefix       = [IO.Path]::GetFullPath([string] $details.base_prefix)
        signerSubject    = $signature.SignerCertificate.Subject
        signerThumbprint = $signature.SignerCertificate.Thumbprint
    }
}

function Get-VireloPipFreezeSnapshot {
    param(
        [Parameter(Mandatory)]
        [string] $PythonExecutable
    )

    $packages = @(& $PythonExecutable -I -m pip freeze --all)
    if ($LASTEXITCODE -ne 0) {
        throw "pip freeze failed while validating the architecture-qualified environment."
    }
    $normalized = @(
        $packages |
            ForEach-Object { $_.ToString().Trim() } |
            Where-Object { $_ } |
            Sort-Object
    )
    $text = if ($normalized.Count -gt 0) {
        ($normalized -join "`n") + "`n"
    }
    else {
        ""
    }
    return [pscustomobject]@{
        packages = $normalized
        sha256   = Get-VireloStringSha256 $text
    }
}

function Get-VireloEnvironmentRemediationCommand {
    param(
        [Parameter(Mandatory)]
        [string] $Architecture,

        [string] $BasePython
    )

    $selectedBase = if ($BasePython) {
        " -PythonExecutable `"$BasePython`""
    }
    else {
        " -PythonExecutable C:\Path\To\OfficialPython\python.exe"
    }
    return "Remove-Item -LiteralPath `".venv-$Architecture`" -Recurse -Force; .\scripts\bootstrap.ps1 -Architecture $Architecture$selectedBase"
}

function Assert-VireloEnvironmentProvenance {
    param(
        [Parameter(Mandatory)]
        [string] $Root,

        [Parameter(Mandatory)]
        [ValidateSet("x64", "arm64")]
        [string] $Architecture,

        [Parameter(Mandatory)]
        [string] $VenvPath,

        [Parameter(Mandatory)]
        [string] $VenvPython,

        [string] $SelectedPython
    )

    $markerPath = Join-Path $VenvPath ".virelo-build-environment.json"
    $fallbackBase = $null
    if ($SelectedPython -and -not (Test-VireloPathEquals $SelectedPython $VenvPython)) {
        $fallbackBase = (Resolve-VireloPythonExecutable $SelectedPython)
    }
    $remediation = Get-VireloEnvironmentRemediationCommand `
        -Architecture $Architecture `
        -BasePython $fallbackBase

    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw ".venv-$Architecture has no verified Virelo provenance marker. It may predate architecture-safe builds or contain stale packages. Remediation: $remediation."
    }

    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    }
    catch {
        throw ".venv-$Architecture has an unreadable provenance marker. Remediation: $remediation."
    }

    $requiredProperties = @(
        "schemaVersion", "architecture", "basePythonExecutable",
        "basePythonSha256", "basePythonVersion", "basePythonPrefix",
        "basePythonSignerSubject", "basePythonSignerThumbprint",
        "constraintsSha256", "pyprojectSha256", "environmentPythonExecutable",
        "environmentPythonVersion", "environmentBasePrefix", "installedPackagesSha256"
    )
    $missingProperties = @(
        $requiredProperties | Where-Object {
            $marker.PSObject.Properties.Name -notcontains $_
        }
    )
    if ($missingProperties.Count -gt 0) {
        throw ".venv-$Architecture has an incomplete provenance marker (missing $($missingProperties -join ', ')). Remediation: $remediation."
    }

    $baseSelection = if ($SelectedPython -and
        -not (Test-VireloPathEquals $SelectedPython $VenvPython)) {
        $SelectedPython
    }
    else {
        [string] $marker.basePythonExecutable
    }

    try {
        $baseIdentity = Get-VireloOfficialPythonIdentity $baseSelection
    }
    catch {
        throw "$($_.Exception.Message) Remediation: $remediation."
    }
    if (-not $fallbackBase) {
        $remediation = Get-VireloEnvironmentRemediationCommand `
            -Architecture $Architecture `
            -BasePython $baseIdentity.executable
    }

    $venvDetails = Get-VireloPythonProcessArchitecture $VenvPython
    $constraintsPath = Join-Path $Root "requirements\build-constraints.txt"
    $pyprojectPath = Join-Path $Root "pyproject.toml"
    $mismatches = [System.Collections.Generic.List[string]]::new()

    if ([int] $marker.schemaVersion -ne 1) {
        $mismatches.Add("unsupported marker schema")
    }
    if ([string] $marker.architecture -ne $Architecture) {
        $mismatches.Add("marker architecture")
    }
    if ($baseIdentity.architecture -ne $Architecture) {
        $mismatches.Add("base Python architecture")
    }
    if (-not (Test-VireloPathEquals ([string] $marker.basePythonExecutable) $baseIdentity.executable)) {
        $mismatches.Add("base Python path")
    }
    if ([string] $marker.basePythonSha256 -ne $baseIdentity.sha256) {
        $mismatches.Add("base Python hash")
    }
    if ([string] $marker.basePythonVersion -ne $baseIdentity.version) {
        $mismatches.Add("base Python version")
    }
    if (-not (Test-VireloPathEquals ([string] $marker.basePythonPrefix) $baseIdentity.basePrefix)) {
        $mismatches.Add("base Python prefix")
    }
    if ([string] $marker.basePythonSignerSubject -ne $baseIdentity.signerSubject -or
        [string] $marker.basePythonSignerThumbprint -ne $baseIdentity.signerThumbprint) {
        $mismatches.Add("base Python Authenticode identity")
    }
    if (-not (Test-VireloPathEquals ([string] $marker.environmentPythonExecutable) $VenvPython)) {
        $mismatches.Add("environment Python path")
    }
    if ([string] $marker.environmentPythonVersion -ne $venvDetails.version) {
        $mismatches.Add("environment Python version")
    }
    if (-not (Test-VireloPathEquals ([string] $marker.environmentBasePrefix) ([string] $venvDetails.base_prefix))) {
        $mismatches.Add("environment base prefix")
    }
    if (-not (Test-Path -LiteralPath $constraintsPath -PathType Leaf) -or
        [string] $marker.constraintsSha256 -ne
        (Get-FileHash -Algorithm SHA256 -LiteralPath $constraintsPath).Hash.ToLowerInvariant()) {
        $mismatches.Add("build constraints")
    }
    if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf) -or
        [string] $marker.pyprojectSha256 -ne
        (Get-FileHash -Algorithm SHA256 -LiteralPath $pyprojectPath).Hash.ToLowerInvariant()) {
        $mismatches.Add("pyproject dependency metadata")
    }

    try {
        $freeze = Get-VireloPipFreezeSnapshot $VenvPython
        if ([string] $marker.installedPackagesSha256 -ne $freeze.sha256) {
            $mismatches.Add("installed package set")
        }
    }
    catch {
        $mismatches.Add("installed package inventory")
    }

    if ($mismatches.Count -gt 0) {
        throw ".venv-$Architecture provenance mismatch: $($mismatches -join ', '). Remediation: $remediation."
    }
    return $marker
}

function Write-VireloEnvironmentProvenance {
    param(
        [Parameter(Mandatory)]
        [string] $Root,

        [Parameter(Mandatory)]
        [ValidateSet("x64", "arm64")]
        [string] $Architecture,

        [Parameter(Mandatory)]
        [string] $BasePython,

        [Parameter(Mandatory)]
        [string] $VenvPython
    )

    $identity = Get-VireloOfficialPythonIdentity $BasePython
    if ($identity.architecture -ne $Architecture) {
        throw "The official base Python is $($identity.architecture), not $Architecture."
    }
    $venvDetails = Get-VireloPythonProcessArchitecture $VenvPython
    $freeze = Get-VireloPipFreezeSnapshot $VenvPython
    $constraintsPath = Join-Path $Root "requirements\build-constraints.txt"
    $pyprojectPath = Join-Path $Root "pyproject.toml"
    $venvPath = Split-Path -Parent (Split-Path -Parent $VenvPython)
    $markerPath = Join-Path $venvPath ".virelo-build-environment.json"
    $marker = [ordered]@{
        schemaVersion               = 1
        architecture                = $Architecture
        basePythonExecutable        = $identity.executable
        basePythonSha256            = $identity.sha256
        basePythonVersion           = $identity.version
        basePythonPrefix            = $identity.basePrefix
        basePythonSignerSubject     = $identity.signerSubject
        basePythonSignerThumbprint  = $identity.signerThumbprint
        constraintsSha256           = (Get-FileHash -Algorithm SHA256 -LiteralPath $constraintsPath).Hash.ToLowerInvariant()
        pyprojectSha256             = (Get-FileHash -Algorithm SHA256 -LiteralPath $pyprojectPath).Hash.ToLowerInvariant()
        environmentPythonExecutable = (Resolve-Path -LiteralPath $VenvPython).Path
        environmentPythonVersion    = $venvDetails.version
        environmentBasePrefix       = [IO.Path]::GetFullPath([string] $venvDetails.base_prefix)
        installedPackagesSha256     = $freeze.sha256
        installedPackages           = $freeze.packages
        verifiedAtUtc               = [DateTime]::UtcNow.ToString("o")
    }
    $json = $marker | ConvertTo-Json -Depth 4
    $utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($markerPath, $json + "`n", $utf8WithoutBom)
    Write-Host "[environment] Wrote verified provenance marker: $markerPath."
    return $markerPath
}

function Remove-VireloWorkspacePath {
    param(
        [Parameter(Mandatory)]
        [string] $Root,

        [Parameter(Mandatory)]
        [string] $Path,

        [switch] $Recurse
    )

    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd([char[]] @('\', '/'))
    $targetPath = if ([IO.Path]::IsPathRooted($Path)) {
        [IO.Path]::GetFullPath($Path)
    }
    else {
        [IO.Path]::GetFullPath((Join-Path $rootPath $Path))
    }
    $rootPrefix = $rootPath + [IO.Path]::DirectorySeparatorChar
    if ($targetPath.Equals($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
        -not $targetPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the Virelo workspace: $targetPath."
    }

    $rootItem = Get-Item -LiteralPath $rootPath -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing recursive deletion because the workspace root is a reparse point: $rootPath."
    }
    $relative = $targetPath.Substring($rootPrefix.Length)
    $current = $rootPath
    foreach ($component in $relative.Split(
            [char[]] @('\', '/'),
            [StringSplitOptions]::RemoveEmptyEntries
        )) {
        $current = Join-Path $current $component
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing recursive deletion through a reparse point: $current."
            }
        }
    }

    if (-not (Test-Path -LiteralPath $targetPath)) {
        return
    }
    Write-Host "[clean] Removing $targetPath."
    if ($Recurse) {
        Remove-Item -LiteralPath $targetPath -Recurse -Force
    }
    else {
        Remove-Item -LiteralPath $targetPath -Force
    }
}

function Invoke-VireloNativeCommand {
    param(
        [Parameter(Mandatory)]
        [string] $FilePath,

        [Parameter(Mandatory)]
        [string[]] $ArgumentList,

        [Parameter(Mandatory)]
        [string] $TranscriptPath
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "The native executable does not exist: $FilePath."
    }
    $resolvedFilePath = (Resolve-Path -LiteralPath $FilePath).Path
    $lines = [System.Collections.Generic.List[string]]::new()
    $previousPreference = $ErrorActionPreference
    $exitCode = $null
    try {
        # In Windows PowerShell 5.1, redirected native stderr is represented as
        # ErrorRecord objects. PyInstaller logs normally to stderr, so collect
        # it under Continue and preserve the real native exit code explicitly.
        $ErrorActionPreference = "Continue"
        # LASTEXITCODE is an automatic global. Clear the global value so a
        # launch failure cannot reuse a successful code from an earlier tool.
        $global:LASTEXITCODE = $null
        & $resolvedFilePath @ArgumentList 2>&1 | ForEach-Object {
            $line = $_.ToString()
            Write-Host $line
            $lines.Add($line)
        }
        $exitCode = $global:LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    $parent = Split-Path -Parent $TranscriptPath
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines($TranscriptPath, $lines, $utf8WithoutBom)
    if ($null -eq $exitCode) {
        throw "The native command could not be launched reliably: $resolvedFilePath."
    }
    return [int] $exitCode
}

function Invoke-VireloBoundedProcess {
    param(
        [Parameter(Mandatory)]
        [string] $FilePath,

        [string[]] $ArgumentList = @(),

        [ValidateRange(1, 2147483)]
        [int] $TimeoutSeconds = 120,

        [switch] $Hidden
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "The bounded process executable does not exist: $FilePath."
    }

    $startParameters = @{
        FilePath     = (Resolve-Path -LiteralPath $FilePath).Path
        ArgumentList = $ArgumentList
        PassThru     = $true
    }
    if ($Hidden) {
        $startParameters.WindowStyle = "Hidden"
    }

    $process = Start-Process @startParameters
    try {
        $timeoutMilliseconds = [int] ([long] $TimeoutSeconds * 1000)
        if (-not $process.WaitForExit($timeoutMilliseconds)) {
            $taskkillPath = Join-Path $env:SystemRoot "System32\taskkill.exe"
            $taskkillResult = "taskkill.exe is unavailable"
            if (Test-Path -LiteralPath $taskkillPath -PathType Leaf) {
                $taskkillProcess = $null
                try {
                    $taskkillProcess = Start-Process `
                        -FilePath $taskkillPath `
                        -ArgumentList @("/PID", $process.Id, "/T", "/F") `
                        -WindowStyle Hidden `
                        -PassThru
                    if ($taskkillProcess.WaitForExit(10000)) {
                        $taskkillProcess.WaitForExit()
                        $taskkillResult = "taskkill exit code $($taskkillProcess.ExitCode)"
                    }
                    else {
                        $taskkillProcess.Kill()
                        [void] $taskkillProcess.WaitForExit(5000)
                        $taskkillResult = "taskkill itself exceeded its 10-second timeout"
                    }
                }
                catch {
                    $taskkillResult = "taskkill failed: $($_.Exception.Message)"
                }
                finally {
                    if ($taskkillProcess) {
                        $taskkillProcess.Dispose()
                    }
                }
            }

            $process.Refresh()
            if (-not $process.HasExited -and -not $process.WaitForExit(10000)) {
                try {
                    $process.Kill()
                }
                catch {
                    throw "Process $($process.Id) exceeded the $TimeoutSeconds-second timeout and could not be terminated. $taskkillResult. Parent-process termination also failed: $($_.Exception.Message)."
                }
                if (-not $process.WaitForExit(10000)) {
                    throw "Process $($process.Id) exceeded the $TimeoutSeconds-second timeout and did not exit after termination. $taskkillResult."
                }
            }
            throw "Process $($process.Id) exceeded the $TimeoutSeconds-second timeout and was terminated. $taskkillResult."
        }

        # The parameterless wait flushes process state before ExitCode is read.
        $process.WaitForExit()
        return [int] $process.ExitCode
    }
    finally {
        $process.Dispose()
    }
}

function Write-VireloAdministratorWarning {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warning "This terminal is elevated. PyInstaller release builds should run from a non-administrator terminal."
    }
}

function Get-VireloAppVersion {
    param(
        [Parameter(Mandatory)]
        [string] $Root
    )

    $match = Select-String -LiteralPath (Join-Path $Root "virelo\app\config.py") -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
    if (-not $match) {
        throw "APP_VERSION was not found in virelo/app/config.py."
    }
    return $match.Matches.Groups[1].Value
}

function Get-VireloSourceFingerprint {
    param(
        [Parameter(Mandatory)]
        [string] $Root
    )

    $paths = @(& git -C $Root ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-files failed while computing the release input fingerprint."
    }
    $builder = [Text.StringBuilder]::new()
    foreach ($relative in ($paths | Sort-Object -Unique)) {
        $absolute = Join-Path $Root $relative
        if (Test-Path -LiteralPath $absolute -PathType Leaf) {
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $absolute).Hash.ToLowerInvariant()
            [void] $builder.Append($relative.Replace('\', '/')).Append("`0").Append($hash).Append("`n")
        }
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes($builder.ToString())
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    return ([BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
}

function Get-VireloDirectoryFingerprint {
    param(
        [Parameter(Mandatory)]
        [string] $Directory,

        [string[]] $ExcludeNames = @()
    )

    $resolved = (Resolve-Path -LiteralPath $Directory).Path
    $builder = [Text.StringBuilder]::new()
    $files = Get-ChildItem -LiteralPath $resolved -Recurse -File | Sort-Object FullName
    foreach ($file in $files) {
        if ($file.Name -in $ExcludeNames) {
            continue
        }
        $relative = $file.FullName.Substring($resolved.Length).TrimStart([char[]] @('\', '/'))
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
        [void] $builder.Append($relative.Replace('\', '/')).Append("`0").Append($hash).Append("`n")
    }
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($builder.ToString()))
    }
    finally {
        $sha256.Dispose()
    }
    return ([BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
}

function Invoke-VireloPreflight {
    param(
        [Parameter(Mandatory)]
        [pscustomobject] $Context,

        [ValidateSet("base", "full")]
        [string] $Mode = "full",

        [string] $PythonExecutable,

        [string] $ReportPath
    )

    if (-not $PythonExecutable) {
        $PythonExecutable = $Context.Python
    }
    if (-not $ReportPath) {
        $ReportPath = $Context.EnvironmentReport
    }
    New-Item -ItemType Directory -Force -Path $Context.BuildRoot | Out-Null
    $arguments = @(
        "scripts\verify_python_environment.py",
        "--architecture", $Context.Architecture,
        "--mode", $Mode,
        "--report", $ReportPath
    )
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python $Mode architecture/ABI preflight failed for $($Context.Architecture)."
    }
}
