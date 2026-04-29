# sync-cache.ps1 — copy all skills from builds/skills/ into the plugin cache
# Run from the dream-studio root: pwsh -File scripts/sync-cache.ps1
# Does NOT delete cache-only skills (one-way push, builds → cache)

$buildsSkills = Join-Path $PSScriptRoot "..\skills"
$cacheSkills  = "$env:USERPROFILE\.claude\plugins\cache\dream-studio\dream-studio\0.2.0\skills"

if (-not (Test-Path $cacheSkills)) {
    Write-Error "Cache path not found: $cacheSkills"
    exit 1
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

Write-Host ""
Write-Host "Done. $synced skills synced ($created new)."
Write-Host "Cache: $cacheSkills"
