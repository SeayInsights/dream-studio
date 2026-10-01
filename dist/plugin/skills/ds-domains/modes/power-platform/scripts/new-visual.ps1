# Scaffold a new pbiviz custom visual with the active brand profile's defaults.
# Wraps `pbiviz new` and patches in the profile's colors/fonts in style/visual.less.
#
# Usage:
#   pwsh scripts/new-visual.ps1 -Name "MyVisual" -DisplayName "My Visual" -BrandProfile "<path-to-profile.yml>"
#   pwsh scripts/new-visual.ps1 -Name "MyVisual" -DisplayName "My Visual"   # falls back to brand-profiles/default.yml
#
# -BrandProfile points at a brand-profile YAML conforming to the schema in
# ../../../powerbi/brand-profile.md. If omitted, falls back to this repo's
# ../../../powerbi/brand-profiles/default.yml. Reads the profile's `name`,
# `typography.font_family`, and the `default_text` / `accent_selected` /
# `divider` palette roles to populate the generated LESS variables and the
# scaffold's default org prefix — never hardcodes one client's palette.
#
# Output:
#   Creates <OutDir>/<orgPrefix>-<kebab-name>/ scaffolded from `pbiviz new`,
#   patched with the active brand profile's defaults.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,                    # PascalCase, e.g. "MyVisual"

    [Parameter(Mandatory = $true)]
    [string]$DisplayName,             # User-facing, e.g. "My Visual"

    [Parameter()]
    [string]$BrandProfile = "",       # Path to a brand-profile YAML. Falls back to the default profile below.

    [Parameter()]
    [string]$OrgPrefix = "",          # Short, consistent org prefix. Derived from the brand profile's name if omitted.

    [Parameter()]
    [string]$OutDir = (Get-Location).Path,

    [Parameter()]
    [string]$Description = "Custom Power BI visual.",

    [Parameter()]
    [string]$AuthorName = "",         # Falls back to the brand profile's name if omitted.

    [Parameter()]
    [string]$AuthorEmail = "dev@example.com"
)

$ErrorActionPreference = "Stop"

# ---------- Resolve the active brand profile ----------
if (-not $BrandProfile) {
    $BrandProfile = Join-Path $PSScriptRoot "..\..\..\powerbi\brand-profiles\default.yml"
}
if (-not (Test-Path -LiteralPath $BrandProfile)) {
    Write-Error "Brand profile not found: $BrandProfile (pass -BrandProfile, or ensure the default profile ships at ../../../powerbi/brand-profiles/default.yml)"
    exit 1
}
$profileContent = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $BrandProfile).Path, [System.Text.Encoding]::UTF8)

# Minimal, schema-scoped YAML scalar reader — not a general YAML parser. Reads
# a single "key: value" line (optionally quoted) at any indentation. Fine for
# the flat scalar fields this schema defines (name, font_family, ...).
function Get-YamlScalar {
    param([string]$Content, [string]$Key)
    $pattern = "(?m)^\s*$([regex]::Escape($Key)):\s*`"?([^`"\r\n]+?)`"?\s*$"
    $m = [regex]::Match($Content, $pattern)
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

# Finds a palette entry shaped:
#   - role: <Role>
#     hex: "<value>"
# and returns <value>. Scoped to this schema's list-of-{role,hex} shape.
function Get-YamlRoleHex {
    param([string]$Content, [string]$Role)
    $pattern = "(?ms)-\s*role:\s*$([regex]::Escape($Role))\s*\r?\n\s*hex:\s*`"([^`"]+)`""
    $m = [regex]::Match($Content, $pattern)
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

$profileName   = Get-YamlScalar -Content $profileContent -Key "name"
if (-not $profileName) { $profileName = "Default Neutral" }

$fontFamily    = Get-YamlScalar -Content $profileContent -Key "font_family"
if (-not $fontFamily) { $fontFamily = "Segoe UI" }

$textHex       = Get-YamlRoleHex -Content $profileContent -Role "default_text"
if (-not $textHex) { $textHex = "#1F2933" }

$accentHex     = Get-YamlRoleHex -Content $profileContent -Role "accent_selected"
if (-not $accentHex) { $accentHex = "#2E6FDB" }

$series3Hex    = Get-YamlRoleHex -Content $profileContent -Role "series_3"
if (-not $series3Hex) { $series3Hex = $accentHex }

$series4Hex    = Get-YamlRoleHex -Content $profileContent -Role "series_4"
if (-not $series4Hex) { $series4Hex = $textHex }

$dividerHex    = Get-YamlRoleHex -Content $profileContent -Role "divider"
if (-not $dividerHex) { $dividerHex = "#D7DEE5" }

Write-Host "Active brand profile: $profileName ($BrandProfile)"

# Derive a short org prefix from the profile name if the caller didn't supply
# one: lowercase, strip non-alphanumerics, take the first word.
if (-not $OrgPrefix) {
    $firstWord = ($profileName -split '\s+')[0]
    $OrgPrefix = ($firstWord -creplace '[^A-Za-z0-9]', '').ToLower()
    if (-not $OrgPrefix) { $OrgPrefix = "org" }
}

if (-not $AuthorName) { $AuthorName = $profileName }

function Convert-PascalToKebab($s) {
    # MyVisual -> my-visual
    return ($s -creplace '([A-Z])', '-$1').ToLower().TrimStart('-')
}

$kebab = Convert-PascalToKebab $Name
$folderName = "$OrgPrefix-$kebab"
$visualName = "$OrgPrefix$Name"      # e.g. acmeMyVisual
$visualDisplayName = if ($DisplayName) { $DisplayName } else { "$OrgPrefix $Name" }

$targetPath = Join-Path -Path $OutDir -ChildPath $folderName
if (Test-Path -LiteralPath $targetPath) {
    Write-Error "Folder already exists: $targetPath"
    exit 1
}

# Generate a fresh GUID (visual name + 32 hex chars from a random GUID)
$rawGuid = ([guid]::NewGuid().ToString("N"))
$fullGuid = "$visualName$rawGuid"

Write-Host "Scaffolding $folderName/"
Write-Host "  visualName     = $visualName"
Write-Host "  displayName    = $visualDisplayName"
Write-Host "  guid           = $fullGuid"
Write-Host "  apiVersion     = 5.3.0"
Write-Host "  output folder  = $targetPath"

# 1. Run pbiviz new
Push-Location $OutDir
try {
    & pbiviz new $folderName --apiVersion 5.3.0
    if ($LASTEXITCODE -ne 0) { throw "pbiviz new failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

# 2. Patch pbiviz.json
$pbivizJsonPath = Join-Path -Path $targetPath -ChildPath "pbiviz.json"
$pbiviz = Get-Content -LiteralPath $pbivizJsonPath -Raw | ConvertFrom-Json
$pbiviz.visual.name = $visualName
$pbiviz.visual.displayName = $visualDisplayName
$pbiviz.visual.guid = $fullGuid
$pbiviz.visual.description = $Description
if (-not $pbiviz.author) { $pbiviz | Add-Member -NotePropertyName author -NotePropertyValue (New-Object PSObject) -Force }
$pbiviz.author.name = $AuthorName
$pbiviz.author.email = $AuthorEmail
$pbiviz | ConvertTo-Json -Depth 10 | Out-File -LiteralPath $pbivizJsonPath -Encoding utf8

# 3. Overwrite style/visual.less with the active brand profile's colors
$lessPath = Join-Path -Path $targetPath -ChildPath "style\visual.less"
$lessContent = @"
@font-family: "$fontFamily", "Segoe UI", sans-serif;
@text-color: $textHex;
@accent-color: $accentHex;
@series-3: $series3Hex;
@series-4: $series4Hex;
@border-color: $dividerHex;
@white: #FFFFFF;

.visual-container {
  font-family: @font-family;
  color: @text-color;
  overflow: hidden;

  .empty-state {
    color: @text-color;
    font-size: 12px;
    padding: 16px;
    text-align: center;
  }

  .tile {
    background: @white;
    color: @text-color;
    border: 1px solid @border-color;
    padding: 8px 12px;

    &--selected {
      background: @border-color;
      border-color: @accent-color;
    }

    &--dimmed {
      opacity: 0.35;
    }
  }
}
"@
$lessContent | Out-File -LiteralPath $lessPath -Encoding utf8

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  cd `"$targetPath`""
Write-Host "  npm install"
Write-Host "  npm start            # then sideload Developer Visual in PBI Desktop"
Write-Host ""
Write-Host "References:"
Write-Host "  ../../../powerbi/custom-visuals.md"
Write-Host "  ../../../powerbi/brand-profile.md"
