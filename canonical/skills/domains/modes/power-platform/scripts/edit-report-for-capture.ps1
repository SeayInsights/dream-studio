# Helper module loaded by screenshot-pbi-desktop.ps1. Pre-launch edits to a PBIR
# report folder so that PBI Desktop opens with the page we want and as little
# pane chrome as possible. ALL edits are reversible; original file content is
# captured in memory and the caller is responsible for invoking the restore in a
# finally block.
#
# What we edit:
#   1) pages/pages.json -> activePageName    (which page opens by default)
#   2) report.json      -> outspacePane.expanded -> "false"
#                          (collapses the filter pane on open; smaller chrome)
#
# What we DON'T edit:
#   - Any visual.json under pages/<id>/visuals/. Their edits are the user's;
#     we never touch them here.
#   - definition.pbir, version.json, .pbi/localSettings.json.
#
# Restore guarantee: Save-ReportEditState writes the original byte-exact content
# of every file we plan to modify into a hashtable. Restore-ReportEditState
# rewrites those files unconditionally (overwrites edits) so a crashed or
# interrupted run leaves the project clean.

function Get-EditLockPath {
    param([Parameter(Mandatory)][string]$ReportRoot)
    return (Join-Path $ReportRoot ".pbi\.troubleshooter-edit-lock.json")
}

# Recovery guard: if a previous run died mid-capture (Ctrl+C, kill, BSOD) before
# the finally block could restore, the lock file holds the original content. On
# next script start, we use it to roll the files back, then delete it.
function Recover-StaleEditLock {
    param([Parameter(Mandatory)][string]$ReportRoot)
    $lockPath = Get-EditLockPath -ReportRoot $ReportRoot
    if (-not (Test-Path -LiteralPath $lockPath)) { return $false }
    try {
        $lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
        Write-Warning "Found stale edit lock from a previous run. Recovering original files..."
        foreach ($entry in $lock.entries) {
            if (Test-Path -LiteralPath $entry.path) {
                [System.IO.File]::WriteAllText($entry.path, $entry.content, (New-Object System.Text.UTF8Encoding($false)))
                Write-Host "  recovered $($entry.path)"
            }
        }
        Remove-Item -LiteralPath $lockPath -Force
        return $true
    } catch {
        Write-Warning "Failed to apply stale edit lock at ${lockPath}: $($_.Exception.Message). You may need to git restore manually."
        return $false
    }
}

function Save-ReportEditState {
    param([Parameter(Mandatory)][string]$ReportRoot)

    if (-not (Test-Path -LiteralPath $ReportRoot)) {
        throw "ReportRoot does not exist: $ReportRoot"
    }
    $state = @{
        ReportRoot = $ReportRoot
        Originals  = @{}    # path -> original content bytes (UTF-8 string)
        Edited     = @{}    # path -> bool (was actually edited?)
        LockPath   = (Get-EditLockPath -ReportRoot $ReportRoot)
        LockWritten = $false
    }
    $candidates = @(
        (Join-Path $ReportRoot "definition\pages\pages.json"),
        (Join-Path $ReportRoot "definition\report.json")
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) {
            $state.Originals[$c] = [System.IO.File]::ReadAllText($c, [System.Text.Encoding]::UTF8)
            $state.Edited[$c] = $false
        }
    }
    return $state
}

# Persist a recovery lock to disk so a crashed run can be cleaned up next time.
# Called once, AFTER the first edit is written, so the lock content reflects the
# pre-edit state.
function Write-EditLock {
    param([Parameter(Mandatory)][hashtable]$State)
    if ($State.LockWritten) { return }
    $entries = @()
    foreach ($path in $State.Originals.Keys) {
        if ($State.Edited[$path]) {
            $entries += @{ path = $path; content = $State.Originals[$path] }
        }
    }
    if ($entries.Count -eq 0) { return }
    $lockDir = Split-Path -Parent $State.LockPath
    if (-not (Test-Path -LiteralPath $lockDir)) { New-Item -ItemType Directory -Path $lockDir -Force | Out-Null }
    $payload = @{ writtenAt = (Get-Date).ToString("o"); entries = $entries } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($State.LockPath, $payload, (New-Object System.Text.UTF8Encoding($false)))
    $State.LockWritten = $true
}

function Remove-EditLock {
    param([Parameter(Mandatory)][hashtable]$State)
    if (Test-Path -LiteralPath $State.LockPath) {
        try { Remove-Item -LiteralPath $State.LockPath -Force } catch { }
    }
}

function Restore-ReportEditState {
    param([Parameter(Mandatory)][hashtable]$State)

    if (-not $State -or -not $State.Originals) { return }
    foreach ($path in @($State.Originals.Keys)) {
        if (-not $State.Edited[$path]) { continue }
        try {
            [System.IO.File]::WriteAllText($path, $State.Originals[$path], (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "  restored $path"
        } catch {
            Write-Warning "Failed to restore ${path}: $($_.Exception.Message)"
        }
    }
}

# Edit pages.json's activePageName via surgical regex so JSON formatting is
# preserved (spacing, key order, line endings). PBIR JSON is hand-edited
# directly in an IDE, so we don't want a ConvertTo-Json round-trip changing
# whitespace.
function Set-ActivePage {
    param(
        [Parameter(Mandatory)][hashtable]$State,
        [Parameter(Mandatory)][string]$PageId
    )
    $pagesJson = (Join-Path $State.ReportRoot "definition\pages\pages.json")
    if (-not $State.Originals.ContainsKey($pagesJson)) {
        Write-Warning "pages.json not in tracked state; skipping activePageName edit"
        return $false
    }

    # Validate the page actually exists in pageOrder before editing.
    $original = $State.Originals[$pagesJson]
    if ($original -notmatch [regex]::Escape($PageId)) {
        Write-Warning "Page id '$PageId' not found in pages.json. Will not edit; PBI will open whatever activePageName points to currently."
        return $false
    }

    # Surgical replace of the activePageName value. The PBIR schema declares
    # activePageName as a string; we match the key + colon + quoted value.
    # We distinguish three outcomes:
    #   (a) regex didn't find activePageName at all - FATAL (caller should exit)
    #   (b) regex matched and current value == target - INFO, no-op (still success)
    #   (c) regex matched and current value != target - apply edit
    $pattern = '("activePageName"\s*:\s*")([^"]*)(")'
    $m = [regex]::Match($original, $pattern)
    if (-not $m.Success) {
        # (a) regex didn't match. This is FATAL: PBI will open whatever page it
        # opened last, which silently mis-targets the capture. Throwing here lets
        # the caller exit with a meaningful code instead of warning and continuing.
        throw "FATAL: activePageName key not found in pages.json. PBI Desktop would open the wrong page silently. Aborting."
    }
    $currentValue = $m.Groups[2].Value
    if ($currentValue -eq $PageId) {
        # (b) already at target - no edit needed. Don't mark file dirty.
        Write-Host "  pages.json: activePageName already at '$PageId' (no edit needed)"
        return $true
    }
    # (c) apply the replacement.
    $replacement = "`${1}$PageId`${3}"
    $modified = [regex]::Replace($original, $pattern, $replacement, [System.Text.RegularExpressions.RegexOptions]::None)

    [System.IO.File]::WriteAllText($pagesJson, $modified, (New-Object System.Text.UTF8Encoding($false)))
    $State.Edited[$pagesJson] = $true
    Write-Host "  pages.json: activePageName '$currentValue' -> '$PageId'"
    return $true
}

# Collapse the filter pane (outspacePane.expanded -> false) so PBI opens with
# more canvas room. Without this edit, the filter pane uses ~250 px on the right.
function Collapse-FilterPane {
    param([Parameter(Mandatory)][hashtable]$State)

    $reportJson = (Join-Path $State.ReportRoot "definition\report.json")
    if (-not $State.Originals.ContainsKey($reportJson)) {
        Write-Warning "report.json not in tracked state; skipping filter pane collapse"
        return $false
    }

    $original = $State.Originals[$reportJson]

    # Match the outspacePane block specifically. Pattern looks for outspacePane,
    # then within its expanded.expr.Literal block, replace Value "true" -> "false".
    # This is multi-line so we use [\s\S]*? for non-greedy across lines.
    $pattern = '("outspacePane"\s*:\s*\[[\s\S]*?"expanded"\s*:\s*\{[\s\S]*?"Literal"\s*:\s*\{[\s\S]*?"Value"\s*:\s*")(true|false)(")'
    $modified = [regex]::Replace($original, $pattern, "`${1}false`${3}", [System.Text.RegularExpressions.RegexOptions]::None)

    if ($modified -eq $original) {
        # Either the outspacePane block isn't present, or it's already false.
        # Both are acceptable; just don't claim we edited.
        return $false
    }

    [System.IO.File]::WriteAllText($reportJson, $modified, (New-Object System.Text.UTF8Encoding($false)))
    $State.Edited[$reportJson] = $true
    Write-Host "  report.json: outspacePane.expanded -> false"
    return $true
}
