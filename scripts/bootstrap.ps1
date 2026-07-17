param(
    [ValidateSet("auto", "x64", "arm64")]
    [string] $Architecture = "auto",

    [string] $PythonExecutable,

    [string] $NodeExecutable,

    [switch] $SkipFrontendDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. "$PSScriptRoot\build-common.ps1"

$context = Get-VireloBuildContext `
    -Architecture $Architecture `
    -PythonExecutable $PythonExecutable `
    -Bootstrap
$originalLocation = Get-Location
try {
    Set-Location $context.Root
    New-Item -ItemType Directory -Force -Path $context.BuildRoot | Out-Null

    $node = $null
    if (-not $SkipFrontendDependencies) {
        $node = Resolve-VireloNodeExecutable $NodeExecutable
        $nodeDetails = Get-VireloNodeDetails $node
        if ($nodeDetails.architecture -ne $context.Architecture) {
            throw "Selected Node.js is $($nodeDetails.architecture), but the build target is $($context.Architecture). Pass a matching -NodeExecutable."
        }
    }

    Write-VireloAdministratorWarning
    Write-Host "[bootstrap] Target architecture: $($context.Architecture)."
    Write-Host "[bootstrap] Base Python: $($context.BasePython)."
    Write-Host "[bootstrap] Environment: $($context.VenvPath)."

    $constraints = Join-Path $context.Root "requirements\build-constraints.txt"
    $pyproject = Join-Path $context.Root "pyproject.toml"
    if (-not (Test-Path -LiteralPath $constraints -PathType Leaf) -or
        -not (Test-Path -LiteralPath $pyproject -PathType Leaf)) {
        throw "The build constraints or pyproject dependency metadata is missing."
    }

    $savedEnvironment = Start-VireloSanitizedEnvironment `
        -PythonExecutable $context.BasePython `
        -NodeExecutable $node
    try {
        $baseReport = Join-Path $context.BuildRoot "base-python.json"
        & $context.BasePython scripts\verify_python_environment.py `
            --architecture $context.Architecture `
            --mode base `
            --report $baseReport
        if ($LASTEXITCODE -ne 0) {
            throw "The selected base interpreter failed architecture/distribution preflight. Use an official native CPython 3.12 or newer interpreter."
        }
        $baseIdentity = Get-VireloOfficialPythonIdentity $context.BasePython
        if ($baseIdentity.architecture -ne $context.Architecture) {
            throw "The verified official base Python is $($baseIdentity.architecture), not $($context.Architecture)."
        }

        $venvPython = Join-Path $context.VenvPath "Scripts\python.exe"
        if (Test-Path -LiteralPath $context.VenvPath) {
            if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
                throw "The existing $($context.VenvPath) is incomplete. Remove it with 'Remove-Item -Recurse -Force .venv-$($context.Architecture)', then rerun this command."
            }
            [void] (Assert-VireloEnvironmentProvenance `
                    -Root $context.Root `
                    -Architecture $context.Architecture `
                    -VenvPath $context.VenvPath `
                    -VenvPython $venvPython `
                    -SelectedPython $context.BasePython)
            & $venvPython scripts\verify_python_environment.py `
                --architecture $context.Architecture `
                --mode base `
                --report (Join-Path $context.BuildRoot "existing-environment.json")
            if ($LASTEXITCODE -ne 0) {
                throw "The existing .venv-$($context.Architecture) is incompatible or Conda-based. Remove it with 'Remove-Item -Recurse -Force .venv-$($context.Architecture)', then rerun bootstrap."
            }
            Write-Host "[bootstrap] Reusing verified .venv-$($context.Architecture)."
        }
        else {
            Write-Host "[bootstrap] Creating .venv-$($context.Architecture)..."
            & $context.BasePython -I -m venv $context.VenvPath
            if ($LASTEXITCODE -ne 0) {
                throw "Creating .venv-$($context.Architecture) failed."
            }
        }

        # Switch the sanitized environment to the architecture-qualified venv.
        Restore-VireloEnvironment $savedEnvironment
        $savedEnvironment = Start-VireloSanitizedEnvironment `
            -PythonExecutable $venvPython `
            -NodeExecutable $node

        # A marker describes a fully installed and preflighted environment. Remove
        # it before mutation so an interrupted pip run cannot leave stale evidence.
        Remove-Item `
            -LiteralPath (Join-Path $context.VenvPath ".virelo-build-environment.json") `
            -Force `
            -ErrorAction SilentlyContinue

        $pipReport = Join-Path $context.BuildRoot "pip-install-report.json"
        Write-Host "[bootstrap] Installing constrained binary dependencies..."
        & $venvPython -I -m pip install `
            --disable-pip-version-check `
            --upgrade `
            --only-binary=:all: `
            --constraint $constraints `
            --report $pipReport `
            -e ".[dev,build]"
        if ($LASTEXITCODE -ne 0) {
            throw "Installing Virelo's constrained Python dependencies failed."
        }

        & $venvPython -I -m pip check
        if ($LASTEXITCODE -ne 0) {
            throw "pip check found an inconsistent Python environment."
        }

        & $venvPython -I "$PSScriptRoot\verify_python_constraints.py" `
            --constraints $constraints `
            --report (Join-Path $context.BuildRoot "python-constraints.json") `
            --allow-unconstrained pip `
            --allow-unconstrained virelo
        if ($LASTEXITCODE -ne 0) {
            throw "The installed Python package closure is not fully and exactly constrained."
        }

        $freeze = & $venvPython -I -m pip freeze --all
        if ($LASTEXITCODE -ne 0) {
            throw "pip freeze failed."
        }
        $freeze | Set-Content `
            -LiteralPath (Join-Path $context.BuildRoot "pip-freeze.txt") `
            -Encoding utf8

        $installedContext = Get-VireloBuildContext `
            -Architecture $context.Architecture `
            -PythonExecutable $venvPython `
            -Provisioning
        Invoke-VireloPreflight -Context $installedContext -Mode full

        [void] (Write-VireloEnvironmentProvenance `
                -Root $context.Root `
                -Architecture $context.Architecture `
                -BasePython $context.BasePython `
                -VenvPython $venvPython)
        $installedContext = Get-VireloBuildContext `
            -Architecture $context.Architecture `
            -PythonExecutable $context.BasePython

        if (-not $SkipFrontendDependencies) {
            & "$PSScriptRoot\build-frontend.ps1" `
                -Architecture $context.Architecture `
                -PythonExecutable $context.BasePython `
                -NodeExecutable $node `
                -InstallOnly
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend dependency bootstrap failed."
            }
        }
    }
    finally {
        Restore-VireloEnvironment $savedEnvironment
    }

    Write-Host "[bootstrap] OK: .venv-$($context.Architecture) is architecture and ABI verified."
}
finally {
    Set-Location -LiteralPath $originalLocation.Path
}
