# sync-plugin-cache.ps1 - refresh the local Claude plugin cache from this repo.
#
# This is intentionally local-only: it does not call GitHub, modify DB state,
# change permissions, or touch non-Dream-Studio projects.

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredPath {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required $Label not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Test-IsUnderPath {
    param([string]$Path, [string]$Parent)

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    return $resolvedPath.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-RelativePath {
    param([string]$BasePath, [string]$Path)

    $baseUri = [System.Uri](([System.IO.Path]::GetFullPath($BasePath).TrimEnd('\')) + '\')
    $pathUri = [System.Uri]([System.IO.Path]::GetFullPath($Path))
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

function Test-ExcludedPath {
    param([string]$RelativePath)

    $excludedDirs = @(
        ".git",
        ".github",
        ".venv",
        ".dream-studio",
        ".sessions",
        ".planning",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".audit",
        ".census",
        ".archive",
        "_archived",
        ".marketplace",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "dev-dist",
        "htmlcov"
    )
    $parts = $RelativePath -split '[\\/]+' | Where-Object { $_ }
    foreach ($part in $parts) {
        if ($excludedDirs -contains $part) {
            return $true
        }
    }

    $leaf = Split-Path -Leaf $RelativePath
    if ($leaf -like "*.pyc" -or
        $leaf -like "*.pyo" -or
        $leaf -like "*.pyd" -or
        $leaf -like "*.db" -or
        $leaf -eq ".coverage" -or
        $leaf -like "dashboard*.log") {
        return $true
    }

    return $false
}

function Copy-TreeFiltered {
    param(
        [string]$Source,
        [string]$Destination,
        [switch]$DryRun
    )

    $copied = 0
    $skipped = 0

    if ($DryRun) {
        Write-Host "DRY-RUN: would sync directory $Source -> $Destination"
    } else {
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    }

    foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -Force -File) {
        $rel = Get-RelativePath -BasePath $Source -Path $file.FullName
        if (Test-ExcludedPath $rel) {
            $skipped++
            continue
        }

        $destFile = Join-Path $Destination $rel
        if ($DryRun) {
            $copied++
            continue
        }

        $destDir = Split-Path -Parent $destFile
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $destFile -Force
        $copied++
    }

    return @{
        Copied = $copied
        Skipped = $skipped
    }
}

function Copy-FileIfPresent {
    param(
        [string]$Source,
        [string]$Destination,
        [switch]$DryRun
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        return $false
    }

    if ($DryRun) {
        Write-Host "DRY-RUN: would copy file $Source -> $Destination"
        return $true
    }

    $destDir = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    return $true
}

$repoRoot = Resolve-RequiredPath -Path (Join-Path $PSScriptRoot "..\..") -Label "repo root"
$pluginManifestPath = Resolve-RequiredPath -Path (Join-Path $repoRoot ".claude-plugin\plugin.json") -Label "plugin manifest"
$marketplacePath = Resolve-RequiredPath -Path (Join-Path $repoRoot ".claude-plugin\marketplace.json") -Label "marketplace metadata"
$hooksManifestPath = Resolve-RequiredPath -Path (Join-Path $repoRoot "hooks\hooks.json") -Label "hooks manifest"
$skillsPath = Resolve-RequiredPath -Path (Join-Path $repoRoot "skills") -Label "skills directory"
$installedPluginsPath = Resolve-RequiredPath -Path (Join-Path $HOME ".claude\plugins\installed_plugins.json") -Label "installed plugin registry"

$manifest = Get-Content -LiteralPath $pluginManifestPath -Raw | ConvertFrom-Json
$pluginName = [string]$manifest.name
$pluginVersion = [string]$manifest.version
if (-not $pluginName -or -not $pluginVersion) {
    throw "Plugin manifest must include name and version: $pluginManifestPath"
}

$pluginKey = "$pluginName@$pluginName"
$cacheBase = Join-Path $HOME ".claude\plugins\cache\$pluginName\$pluginName"
if (-not (Test-Path -LiteralPath $cacheBase)) {
    throw "Plugin cache base not found: $cacheBase"
}

$targetCache = Join-Path $cacheBase $pluginVersion
if (-not (Test-IsUnderPath -Path $targetCache -Parent $cacheBase)) {
    throw "Refusing to write outside plugin cache base: $targetCache"
}

$repoHead = (git -C $repoRoot rev-parse HEAD).Trim()
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$staging = Join-Path $cacheBase "$pluginVersion.__staging_$timestamp"
$backupTarget = Join-Path $cacheBase "$pluginVersion.__backup_$timestamp"

$installed = Get-Content -LiteralPath $installedPluginsPath -Raw | ConvertFrom-Json
$entry = $null
$canUpdateInstalledMetadata = $false
if ($installed.plugins -and
    ($installed.plugins.PSObject.Properties.Name -contains $pluginKey) -and
    $installed.plugins.$pluginKey.Count -ge 1) {
    $entry = $installed.plugins.$pluginKey[0]
    if (($entry.PSObject.Properties.Name -contains "installPath") -and
        ($entry.PSObject.Properties.Name -contains "version") -and
        ($entry.PSObject.Properties.Name -contains "lastUpdated")) {
        $canUpdateInstalledMetadata = $true
    }
}

$sourceDirs = @(
    ".claude-plugin",
    "agents",
    "hooks",
    "runtime",
    "control",
    "core",
    "interfaces",
    "skills",
    "workflows",
    "packs",
    "rules",
    "templates",
    "shared",
    "guardrails"
)

$sourceFiles = @(
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "CLAUDE.md",
    "packs.yaml",
    "pyproject.toml",
    "requirements.txt"
)

Write-Host "Dream Studio local plugin cache refresh"
Write-Host "Repo:    $repoRoot"
Write-Host "HEAD:    $repoHead"
Write-Host "Version: $pluginVersion"
Write-Host "Target:  $targetCache"
Write-Host "Mode:    $(if ($DryRun) { 'dry-run' } else { 'apply' })"
Write-Host ""

if ($DryRun) {
    Write-Host "DRY-RUN: would stage cache at $staging"
    if (Test-Path -LiteralPath $targetCache) {
        Write-Host "DRY-RUN: existing target would be archived to $backupTarget"
    }
} else {
    if (Test-Path -LiteralPath $staging) {
        throw "Staging path already exists: $staging"
    }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
}

$totalCopied = 0
$totalSkipped = 0
foreach ($dir in $sourceDirs) {
    $src = Join-Path $repoRoot $dir
    if (-not (Test-Path -LiteralPath $src)) {
        continue
    }
    $result = Copy-TreeFiltered -Source $src -Destination (Join-Path $staging $dir) -DryRun:$DryRun
    $totalCopied += $result.Copied
    $totalSkipped += $result.Skipped
}

$filesCopied = 0
foreach ($file in $sourceFiles) {
    $src = Join-Path $repoRoot $file
    if (Copy-FileIfPresent -Source $src -Destination (Join-Path $staging $file) -DryRun:$DryRun) {
        $filesCopied++
    }
}

if ($DryRun) {
    Write-Host ""
    Write-Host "DRY-RUN: would copy $totalCopied files from directories ($totalSkipped generated/cache files skipped)."
    Write-Host "DRY-RUN: would copy $filesCopied root files."
    if ($canUpdateInstalledMetadata) {
        Write-Host "DRY-RUN: would update $pluginKey metadata in $installedPluginsPath"
        Write-Host "         version: $($entry.version) -> $pluginVersion"
        Write-Host "         installPath: $($entry.installPath) -> $targetCache"
        Write-Host "         gitCommitSha: $($entry.gitCommitSha) -> $repoHead"
    } else {
        Write-Host "DRY-RUN: installed plugin metadata schema not recognized; would not update registry."
    }
    exit 0
}

if (Test-Path -LiteralPath $targetCache) {
    if (Test-Path -LiteralPath $backupTarget) {
        throw "Backup target already exists: $backupTarget"
    }
    Move-Item -LiteralPath $targetCache -Destination $backupTarget
    Write-Host "Archived existing target: $backupTarget"
}
Move-Item -LiteralPath $staging -Destination $targetCache
Write-Host "Refreshed cache target: $targetCache"
Write-Host "Copied $totalCopied files from directories ($totalSkipped generated/cache files skipped)."
Write-Host "Copied $filesCopied root files."

if ($canUpdateInstalledMetadata) {
    $registryBackup = "$installedPluginsPath.bak.$timestamp"
    Copy-Item -LiteralPath $installedPluginsPath -Destination $registryBackup -Force
    $entry.installPath = $targetCache
    $entry.version = $pluginVersion
    $entry.lastUpdated = (Get-Date).ToUniversalTime().ToString("o")
    if ($entry.PSObject.Properties.Name -contains "gitCommitSha") {
        $entry.gitCommitSha = $repoHead
    } else {
        $entry | Add-Member -NotePropertyName "gitCommitSha" -NotePropertyValue $repoHead
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText(
        $installedPluginsPath,
        (($installed | ConvertTo-Json -Depth 10) + [Environment]::NewLine),
        $utf8NoBom
    )
    Write-Host "Updated installed plugin metadata: $installedPluginsPath"
    Write-Host "Registry backup: $registryBackup"
} else {
    Write-Warning "Installed plugin metadata schema not recognized; cache refreshed but registry was not updated."
}
