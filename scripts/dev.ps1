param(
    [Parameter(Position = 0)]
    [string]$Target = "help",

    [string]$Project,
    [string]$ProjectsDir,
    [string]$Platform,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Write-Usage {
    Write-Host "Dream Studio Windows dev commands"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 <target> [options]"
    Write-Host ""
    Write-Host "Core targets:"
    Write-Host "  test                 Run full pytest suite with coverage gate"
    Write-Host "  lint                 Run black --check and flake8"
    Write-Host "  fmt                  Run black formatter"
    Write-Host "  typecheck            Run pyright if available"
    Write-Host "  verify               Run focused runtime verification gates"
    Write-Host "  verify-guarded       Run focused runtime gates under runtime state hash guard"
    Write-Host "  test-guarded         Run full pytest suite under runtime state hash guard"
    Write-Host "  product-readiness    Run narrow product-readiness baseline guardrails"
    Write-Host "  runtime-check         Run runtime reliability pytest marker"
    Write-Host "  docker-runtime-check  Run the Docker clean-room validation harness"
    Write-Host "  run-api              Run projections API with uvicorn"
    Write-Host "  run-ui               Launch dashboard UI through the canonical CLI"
    Write-Host "  clean                Remove local Python/test cache artifacts"
    Write-Host ""
    Write-Host "Makefile parity targets:"
    Write-Host "  install-dev, security, setup, setup-check, ci-gate, install, docs,"
    Write-Host "  sync-cache, validate-analysts, analytics, dashboard, dashboard-check,"
    Write-Host "  adapters, install-statusline"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify-guarded"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 product-readiness"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 docker-runtime-check"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 run-api -Port 8001"
}

function Resolve-Python {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }

        & $candidate.Command @($candidate.Args + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")) *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{
                Command = $candidate.Command
                Args = $candidate.Args
            }
        }
    }

    throw "Python 3.11+ was not found. Install Python or activate the project environment."
}

$Python = Resolve-Python

function Invoke-Python {
    param([string[]]$Arguments)
    & $Python.Command @($Python.Args + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Invoke-GuardedPython {
    param(
        [string]$Label,
        [string[]]$Arguments
    )
    $guardArgs = @(
        "scripts/runtime_state_hash_guard.py",
        "--label", $Label,
        "--",
        $Python.Command
    ) + $Python.Args + $Arguments

    & $Python.Command @($Python.Args + $guardArgs)
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Invoke-External {
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Assert-Command {
    param([string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$Command is not available on PATH."
    }
}

function Remove-RepoPath {
    param([System.IO.FileSystemInfo]$Item)
    $resolved = Resolve-Path -LiteralPath $Item.FullName
    if (-not $resolved.Path.StartsWith($RepoRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside repo: $($resolved.Path)"
    }
    Remove-Item -LiteralPath $resolved.Path -Recurse -Force
}

switch ($Target) {
    "help" {
        Write-Usage
    }

    "test" {
        Invoke-Python @(
            "-m", "pytest", "tests/",
            "--cov=hooks/lib",
            "--cov=packs/domains/domain_lib",
            "--cov-fail-under=70",
            "-q"
        )
    }

    "lint" {
        Invoke-Python @("-m", "black", "--check", ".")
        Invoke-Python @("interfaces/cli/lint_baseline.py", "check")
    }

    "fmt" {
        Invoke-Python @("-m", "black", ".")
    }

    "typecheck" {
        if (Get-Command pyright -ErrorAction SilentlyContinue) {
            Invoke-External "pyright" @()
        } elseif (Get-Command npx -ErrorAction SilentlyContinue) {
            Invoke-External "npx" @("pyright")
        } else {
            throw "pyright is not available. Install pyright or Node/npx, then rerun typecheck."
        }
    }

    "verify" {
        Invoke-Python @("-m", "pytest", "tests/integration/test_schema_migrations.py", "-q")
        Invoke-Python @("-m", "pytest", "-m", "runtime_reliability", "-q")
        Invoke-Python @("-m", "pytest", "tests/unit/test_hook_runtime_reliability.py", "-q")
    }

    "verify-guarded" {
        Invoke-GuardedPython "schema_migrations" @(
            "-m", "pytest", "tests/integration/test_schema_migrations.py", "-q"
        )
        Invoke-GuardedPython "runtime_reliability" @(
            "-m", "pytest", "-m", "runtime_reliability", "-q"
        )
        Invoke-GuardedPython "hook_runtime_reliability" @(
            "-m", "pytest", "tests/unit/test_hook_runtime_reliability.py", "-q"
        )
    }

    "test-guarded" {
        Invoke-GuardedPython "powershell_test" @(
            "-m", "pytest", "tests/",
            "--cov=hooks/lib",
            "--cov=packs/domains/domain_lib",
            "--cov-fail-under=70",
            "-q"
        )
    }

    "product-readiness" {
        Invoke-Python @(
            "-m", "pytest",
            "tests/unit/test_product_readiness_baseline.py",
            "-q", "--tb=line"
        )
    }

    "runtime-check" {
        Invoke-Python @("-m", "pytest", "-m", "runtime_reliability", "-q")
    }

    "docker-runtime-check" {
        Assert-Command "docker"
        Invoke-External "docker" @("build", "-f", "Dockerfile.runtime-check", "-t", "dream-studio-runtime-check", ".")
        Invoke-External "docker" @(
            "run", "--rm", "--network", "none",
            "-e", "HOME=/tmp/dream-studio-user",
            "-e", "DREAM_STUDIO_HOME=/tmp/dream-studio-home",
            "dream-studio-runtime-check"
        )
    }

    "run-api" {
        Invoke-Python @("-m", "uvicorn", "projections.api.main:app", "--host", $HostName, "--port", "$Port")
    }

    "run-ui" {
        Invoke-Python @("interfaces/cli/ds_dashboard.py", "--host", $HostName, "--port", "$Port")
    }

    "dashboard" {
        Invoke-Python @("interfaces/cli/ds_dashboard.py")
    }

    "dashboard-check" {
        Invoke-Python @("interfaces/cli/ds_dashboard.py", "--check")
    }

    "setup" {
        Invoke-Python @("interfaces/cli/setup.py")
    }

    "setup-check" {
        Invoke-Python @("interfaces/cli/setup.py", "--check")
    }

    "ci-gate" {
        Invoke-Python @("interfaces/cli/ci_gate.py")
    }

    "install" {
        Invoke-Python @("interfaces/cli/generate_routing.py")
    }

    "docs" {
        Invoke-Python @("interfaces/cli/sync_docs.py")
    }

    "sync-cache" {
        Invoke-External "powershell.exe" @("-ExecutionPolicy", "Bypass", "-File", "interfaces/cli/sync-cache.ps1")
    }

    "validate-analysts" {
        Invoke-Python @("interfaces/cli/validate_analysts.py")
    }

    "analytics" {
        $args = @("interfaces/cli/ds_analytics/main.py")
        if ($Project) {
            $args += @("--project", $Project)
        }
        if ($ProjectsDir) {
            $args += @("--projects-dir", $ProjectsDir)
        }
        Invoke-Python $args
    }

    "adapters" {
        $args = @("interfaces/cli/build_adapters.py")
        if ($Platform) {
            $args += @("--platform", $Platform)
        }
        Invoke-Python $args
    }

    "security" {
        Invoke-Python @("-m", "pip_audit", "-r", "requirements-dev.txt", "-r", "requirements.txt")
    }

    "install-dev" {
        Invoke-Python @("-m", "pip", "install", "-r", "requirements-dev.txt")
        Invoke-Python @("-m", "pre_commit", "install")
    }

    "install-statusline" {
        $source = Join-Path $RepoRoot "interfaces/cli/statusline-command.sh"
        $targetDir = Join-Path $HOME ".claude"
        $target = Join-Path $targetDir "statusline-command.sh"
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
        Write-Host "Copied statusline-command.sh to $target"
        Write-Host 'Add to ~/.claude/settings.json:'
        Write-Host '  "statusLine": { "type": "command", "command": "bash \"~/.claude/statusline-command.sh\"" }'
    }

    "clean" {
        Get-ChildItem -Path $RepoRoot -Directory -Recurse -Force -Filter "__pycache__" | ForEach-Object {
            Remove-RepoPath $_
        }
        foreach ($path in @(".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov")) {
            $fullPath = Join-Path $RepoRoot $path
            if (Test-Path $fullPath) {
                Remove-RepoPath (Get-Item $fullPath)
            }
        }
        foreach ($path in @(".coverage")) {
            $fullPath = Join-Path $RepoRoot $path
            if (Test-Path $fullPath) {
                Remove-Item -LiteralPath (Resolve-Path $fullPath).Path -Force
            }
        }
    }

    default {
        Write-Usage
        throw "Unknown target: $Target"
    }
}
