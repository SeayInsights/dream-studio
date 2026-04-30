# sync-cache.ps1 — mirror skills from builds/skills/ into the plugin cache
# Run from the dream-studio root: pwsh -File scripts/sync-cache.ps1
# Removes cache-only directories that no longer exist in builds (full mirror).

$buildsSkills = Join-Path $PSScriptRoot "..\skills"

# Find the cache path dynamically (version may change)
$cacheBase = "$env:USERPROFILE\.claude\plugins\cache\dream-studio\dream-studio"
$cacheVersion = Get-ChildItem $cacheBase -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $cacheVersion) {
    Write-Error "No cached plugin version found under: $cacheBase"
    exit 1
}
$cacheSkills = Join-Path $cacheVersion.FullName "skills"

if (-not (Test-Path $cacheSkills)) {
    New-Item -ItemType Directory -Path $cacheSkills -Force | Out-Null
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$synced = 0
$created = 0

foreach ($skillDir in Get-ChildItem $buildsSkills -Directory) {
    $dest = Join-Path $cacheSkills $skillDir.Name

    $isNew = -not (Test-Path $dest)
    if ($isNew) {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        $created++
    }

    foreach ($file in Get-ChildItem $skillDir.FullName -Recurse -File) {
        $rel     = $file.FullName.Substring($skillDir.FullName.Length).TrimStart('\', '/')
        $destFile = Join-Path $dest $rel
        $destDir  = Split-Path $destFile -Parent

        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        Copy-Item -Path $file.FullName -Destination $destFile -Force
    }

    $label = if ($isNew) { "(new)" } else { "" }
    Write-Host "  synced: $($skillDir.Name) $label"
    $synced++
}

# Clean stale directories from cache that no longer exist in builds
$removed = 0
foreach ($cacheDir in Get-ChildItem $cacheSkills -Directory) {
    $srcMatch = Join-Path $buildsSkills $cacheDir.Name
    if (-not (Test-Path $srcMatch)) {
        Remove-Item $cacheDir.FullName -Recurse -Force
        Write-Host "  removed stale: $($cacheDir.Name)"
        $removed++
    }
}

Write-Host ""
Write-Host "Done. $synced skills synced ($created new, $removed stale removed)."
Write-Host "Cache: $cacheSkills"
