# Screenshot a specific PBI Desktop window off-screen, with adaptive multi-stage
# wait for render completion. The user can keep using their machine while we
# capture; PBI Desktop need not be on top.
#
# Phase 2 scope (this file):
#   - PrintWindow + PW_RENDERFULLCONTENT capture (Phase 1, retained)
#   - DPI-aware process so capture resolution matches what PBI is actually rendering
#   - Silent window resize (SWP_NOACTIVATE) to a deterministic size so the canvas
#     fits and run-to-run captures are pixel-comparable
#   - Three-stage adaptive wait:
#       Stage 1: window-title gate (title includes the .pbip stem) - max 60s
#       Stage 2: pixel-stability poll (downsampled-grid frame diff) - max 4 min
#       Stage 3: hard cap on total elapsed - max 5 min
#
# Phase 3 will add page selection (-PageId) and canvas-region cropping.
#
# Usage:
#   powershell -File scripts/screenshot-pbi-desktop.ps1 -Pbip "<file>.pbip" -Out screenshot.png
#   powershell -File scripts/screenshot-pbi-desktop.ps1 -Pbip "<file>.pbip" -Out screenshot.png -ResizeWidth 1600 -ResizeHeight 1000
#   powershell -File scripts/screenshot-pbi-desktop.ps1 -Pbip "<file>.pbip" -Out screenshot.png -KeepOpen
#   powershell -File scripts/screenshot-pbi-desktop.ps1 -Pbip "<file>.pbip" -Out screenshot.png -ReusePid 12345
#
# Exit codes:
#   0   screenshot saved
#   1   capture failed (window not found, PrintWindow returned all-black, etc.)
#   2   FIRST_LAUNCH_LIKELY_NEEDS_SSO
#   3   PBIDESKTOP_CRASHED
#   4   WINDOW_NOT_FOUND_TIMEOUT
#   5   RENDER_TIMEOUT (5 min hard cap exceeded)
#   6   CAPTURE_GATE_TIMEOUT (another Path A capture is running; retry later)

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Pbip,

    [Parameter(Mandatory = $true)]
    [string]$Out,

    # Optional. When provided, we set pages.json's activePageName to this id BEFORE
    # launching PBI Desktop, then restore the original after capture. The id must
    # exist in pageOrder; otherwise we proceed without changing activePageName.
    [string]$PageId = "",

    # Default ON: collapse the filter pane (outspacePane.expanded=false) before
    # launch so the captured frame has more canvas. Restored after capture.
    [switch]$NoCollapseFilterPane,

    # Default 1800x1125 (0.75 of original 2400x1500) - sized for legible canvas
    # captures while keeping multimodal context cost reasonable. Each Path A
    # round-trip ~halves token cost vs 2400x1500. Pass -HighRes for the original
    # 2400x1500 when pixel-precision matters (e.g., diagnosing a 4px overflow).
    # If -ResizeWidth/-ResizeHeight are passed explicitly, they win over -HighRes.
    [int]$ResizeWidth = 0,
    [int]$ResizeHeight = 0,
    [switch]$HighRes,

    [int]$TitleGateSec = 60,
    [int]$StabilityPollSec = 2,
    [int]$StabilityRequiredFrames = 3,
    [int]$StabilityMaxSec = 240,
    [int]$HardCapSec = 300,

    # How long to wait for the machine-wide capture gate (one Path A capture at
    # a time across ALL agent sessions) before giving up with exit 6.
    [int]$CaptureGateWaitSec = 300,

    [double]$StabilityThreshold = 0.001,    # mean per-cell normalized RGB delta; 0.001 ~ 0.1% pixel change

    [switch]$AssumeLoggedIn,

    # Close behavior. By default we force-close any PBI Desktop instance we spawned
    # ourselves (no save prompt — the operator is not left holding a stray window).
    # Pass -KeepOpen to leave it open. Existing PBI Desktop sessions reused via
    # -ReusePid are NEVER auto-closed regardless of this flag.
    [switch]$KeepOpen,

    [switch]$NoResize,

    # Hidden-during-capture mode (Excel-style background processing). Default ON:
    # the moment we find the PBI Desktop window, we hide it and run the entire
    # capture flow off-screen. The user sees a brief flicker during launch (before
    # we get the hwnd) and then nothing. Pass -VisibleDuringCapture to revert to
    # the visible-window behavior.
    [switch]$VisibleDuringCapture,

    [int]$ReusePid = 0,

    [string]$PbiDesktopExe = "",

    # Canvas-only crop. Default ON: after capture, write a second PNG cropped to
    # just the report canvas (excludes ribbon, page tabs, filter pane, Build pane).
    # The crop region is calibrated for 2400x1500 captures and scaled proportionally
    # to the actual capture dimensions. Output path is the same as -Out with
    # "_canvas" inserted before the extension. Pass -NoCropCanvas to skip.
    [switch]$NoCropCanvas,

    # Override the crop rectangle (pixel coords in the captured image). Format
    # "x,y,width,height". Use when the pane state differs from the calibrated
    # default (e.g., user has Build pane manually collapsed).
    [string]$CanvasRect = "",

    # Skip writing the full-window capture; only the canvas-cropped PNG is saved.
    # Useful when Claude only needs the canvas for multimodal review — halves disk
    # usage and signals "the full window is not part of the loop here".
    [switch]$CanvasOnly
)

# Default resize: 1800x1125 (low-res) unless -HighRes is set OR -ResizeWidth/Height passed.
if ($ResizeWidth -le 0)  { $ResizeWidth  = if ($HighRes) { 2400 } else { 1800 } }
if ($ResizeHeight -le 0) { $ResizeHeight = if ($HighRes) { 1500 } else { 1125 } }

# ---------- Locate PBI Desktop ----------
# Resolution order: explicit -PbiDesktopExe param > classic install > Store shim.
# The classic install lives at "$ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
# but Microsoft has moved most users to the Store version which exposes a shim at
# "$LOCALAPPDATA\Microsoft\WindowsApps\PBIDesktopStore.exe". The shim accepts a .pbip
# argument and forwards to the actual executable inside %ProgramFiles%\WindowsApps\
# (a reparse point we can't enumerate without elevation, hence going through the shim).
function Resolve-PbiDesktopPath {
    param([string]$Explicit)

    # 1. Explicit param wins.
    if ($Explicit -and (Test-Path -LiteralPath $Explicit)) { return $Explicit }

    # 2. Environment-variable override - lets users pin a non-default install.
    if ($env:PBI_DESKTOP_EXE -and (Test-Path -LiteralPath $env:PBI_DESKTOP_EXE)) {
        return $env:PBI_DESKTOP_EXE
    }

    # 3. .pbip file-association lookup. Whatever Explorer launches when you
    #    double-click a .pbip is what we should use too. Walks HKCR\.pbip ->
    #    ProgID -> shell\open\command. Works across classic, Store, and custom installs.
    try {
        $progId = (Get-ItemProperty -Path "Registry::HKEY_CLASSES_ROOT\.pbip" -Name "(default)" -ErrorAction Stop)."(default)"
        if ($progId) {
            $cmdPath = "Registry::HKEY_CLASSES_ROOT\$progId\shell\open\command"
            $cmd = (Get-ItemProperty -Path $cmdPath -Name "(default)" -ErrorAction Stop)."(default)"
            if ($cmd) {
                # Command is typically: "C:\path\to\PBIDesktop.exe" "%1"
                # Parse the first quoted token; if no quotes, take up to the first space.
                $exe = $null
                if ($cmd -match '^\s*"([^"]+)"') { $exe = $matches[1] }
                elseif ($cmd -match '^\s*(\S+)')  { $exe = $matches[1] }
                if ($exe -and (Test-Path -LiteralPath $exe)) { return $exe }
            }
        }
    } catch { }

    # 4. App-paths registry hive — Windows-standard "where is this exe" lookup.
    foreach ($name in 'PBIDesktop.exe', 'PBIDesktopStore.exe') {
        foreach ($hive in 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths') {
            try {
                $key = "$hive\$name"
                if (Test-Path $key) {
                    $exe = (Get-ItemProperty -Path $key -Name "(default)" -ErrorAction Stop)."(default)"
                    if ($exe -and (Test-Path -LiteralPath $exe)) { return $exe }
                }
            } catch { }
        }
    }

    # 5. Static candidate list — known install locations across versions.
    $candidates = @(
        "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\PBIDesktopStore.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\PBIDesktop.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }

    # 6. PATH search.
    $cmd = Get-Command "PBIDesktop.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command "PBIDesktopStore.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    return $null
}

$ErrorActionPreference = "Stop"
$scriptStart = Get-Date

# ---------- Win32 P/Invoke ----------
$win32Sig = @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32 {
    public const uint PW_RENDERFULLCONTENT = 0x00000002;

    public const uint SWP_NOACTIVATE = 0x0010;
    public const uint SWP_NOZORDER   = 0x0004;
    public const uint SWP_NOMOVE     = 0x0002;
    public const uint SWP_NOSIZE     = 0x0001;
    public const uint SWP_FRAMECHANGED = 0x0020;

    public const int  SW_RESTORE     = 9;
    public const int  SW_HIDE        = 0;
    public const int  SW_SHOWNA      = 8;       // show without activating

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    // Per-monitor DPI awareness (Win 8.1+, refined in Win 10 1607+ via DpiAwarenessContext).
    // We try the modern call first and silently no-op if it isn't present.
    [DllImport("user32.dll")]
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr dpiContext);

    public static readonly IntPtr DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = new IntPtr(-4);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
        public int Width  { get { return Right - Left; } }
        public int Height { get { return Bottom - Top; } }
    }
}
"@
if (-not ("Win32" -as [type])) {
    Add-Type -TypeDefinition $win32Sig -Language CSharp
}

# Best-effort: make our thread DPI-aware so PrintWindow captures at native resolution
# rather than scaled-down logical pixels. Falls back silently on older Windows.
try { [Win32]::SetThreadDpiAwarenessContext([Win32]::DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) | Out-Null } catch { }

# ---------- Helpers ----------
function Get-WindowText([IntPtr]$hwnd) {
    $len = [Win32]::GetWindowTextLength($hwnd)
    if ($len -le 0) { return "" }
    $sb = New-Object System.Text.StringBuilder ($len + 1)
    [Win32]::GetWindowText($hwnd, $sb, $sb.Capacity) | Out-Null
    return $sb.ToString()
}

function Get-WindowClass([IntPtr]$hwnd) {
    $sb = New-Object System.Text.StringBuilder 256
    [Win32]::GetClassName($hwnd, $sb, $sb.Capacity) | Out-Null
    return $sb.ToString()
}

function Find-MainWindowForPids {
    param([int[]]$TargetPids)

    $script:foundRef = [pscustomobject]@{ Value = [IntPtr]::Zero }
    $script:foundPidRef = [pscustomobject]@{ Value = 0 }
    $script:bestScoreRef = [pscustomobject]@{ Value = -1 }
    $script:targetPidsRef = $TargetPids

    $cb = [Win32+EnumWindowsProc] {
        param([IntPtr]$hwnd, [IntPtr]$lparam)
        try {
            if (-not [Win32]::IsWindowVisible($hwnd)) { return $true }
            $procId = 0
            [Win32]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null
            if ($script:targetPidsRef -notcontains [int]$procId) { return $true }

            $title = Get-WindowText $hwnd
            $cls   = Get-WindowClass $hwnd
            $rect  = New-Object Win32+RECT
            [Win32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
            $area  = [Math]::Max(0, $rect.Width) * [Math]::Max(0, $rect.Height)

            if ($area -lt 200000) { return $true }
            $score = $area
            if ($title.Length -gt 0)            { $score += 10000000 }
            if ($cls -match "PBIDesktop")       { $score += 5000000 }
            if ($cls -match "HwndWrapper")      { $score += 1000000 }

            if ($script:bestScoreRef.Value -lt $score) {
                $script:bestScoreRef.Value = $score
                $script:foundRef.Value = $hwnd
                $script:foundPidRef.Value = [int]$procId
            }
        } catch { }
        return $true
    }

    [Win32]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return [pscustomobject]@{ Hwnd = $script:foundRef.Value; Pid = $script:foundPidRef.Value }
}

# Wait for a window owned by ANY currently-living PBI-family process that we
# caused to spawn. Returns hwnd + the PID that actually owns the window (which
# can differ from the shim PID we got back from Start-Process). Default polling
# interval is 100ms — every additional 100ms is more on-screen flash time for
# the launching window, so we poll tight here.
function Wait-ForOwnedWindow {
    param([int[]]$ExcludePids, [int[]]$ExtraIncludePids = @(), [int]$TimeoutSec, [int]$PollIntervalMs = 100)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $candidates = @()
        $candidates += $ExtraIncludePids
        foreach ($p in (Get-PbiFamilyPids)) {
            if ($ExcludePids -notcontains $p -and (Test-PidIsOurs -ProcId $p)) { $candidates += $p }
        }
        $candidates = $candidates | Select-Object -Unique
        if ($candidates.Count -gt 0) {
            $r = Find-MainWindowForPids -TargetPids $candidates
            if ($r.Hwnd -ne [IntPtr]::Zero) { return $r }
        }
        Start-Sleep -Milliseconds $PollIntervalMs
    }
    return [pscustomobject]@{ Hwnd = [IntPtr]::Zero; Pid = 0 }
}

# Resize the PBI window in place without stealing focus or moving it on screen.
# We keep its current position and just change its size.
function Resize-WindowInPlace {
    param([IntPtr]$hwnd, [int]$Width, [int]$Height)

    # If minimized, restore first (PrintWindow on iconic windows can return blank).
    if ([Win32]::IsIconic($hwnd)) {
        [Win32]::ShowWindow($hwnd, [Win32]::SW_RESTORE) | Out-Null
        Start-Sleep -Milliseconds 200
    }

    $flags = [Win32]::SWP_NOACTIVATE -bor [Win32]::SWP_NOZORDER -bor [Win32]::SWP_NOMOVE
    [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, $Width, $Height, $flags) | Out-Null
}

# Hide the window completely (Excel-style background). Returns the original
# rect so we can re-show it if needed. PrintWindow + PW_RENDERFULLCONTENT is
# documented to render hidden windows correctly.
function Hide-Window {
    param([IntPtr]$hwnd)
    if ([Win32]::IsIconic($hwnd)) {
        [Win32]::ShowWindow($hwnd, [Win32]::SW_RESTORE) | Out-Null
        Start-Sleep -Milliseconds 100
    }
    [Win32]::ShowWindow($hwnd, [Win32]::SW_HIDE) | Out-Null
}

# Move the window off-screen as a fallback when hidden capture returns blank.
# Some DirectX swap chains skip rendering when the window is SW_HIDE; moving
# the window to (-32000, -32000) keeps it "visible" in Windows' eyes (so the
# render pipeline runs) but invisible on any real monitor.
function Move-WindowOffscreen {
    param([IntPtr]$hwnd, [int]$Width, [int]$Height)
    [Win32]::ShowWindow($hwnd, [Win32]::SW_SHOWNA) | Out-Null
    $flags = [Win32]::SWP_NOACTIVATE -bor [Win32]::SWP_NOZORDER
    [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, -32000, -32000, $Width, $Height, $flags) | Out-Null
}

# Move off-screen WITHOUT changing size. Called the moment we detect a new
# PBI window in Stage 0 — before resize, before title gate — so the visible
# flash is bounded to one window-poll interval (now 100ms).
function Move-WindowOffscreenKeepSize {
    param([IntPtr]$hwnd)
    [Win32]::ShowWindow($hwnd, [Win32]::SW_SHOWNA) | Out-Null
    $flags = [Win32]::SWP_NOACTIVATE -bor [Win32]::SWP_NOZORDER -bor [Win32]::SWP_NOSIZE
    [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, -32000, -32000, 0, 0, $flags) | Out-Null
}

# Sweep ALL visible windows owned by the given PIDs to off-screen coordinates.
# Used during early launch to catch the PBI Desktop splash screen (a separate
# smaller window from the main report window) which would otherwise flash
# briefly over the user's other apps. Idempotent — windows already off-screen
# stay off-screen. Skips windows whose position is already (-32000, -32000).
function Move-AllOwnedWindowsOffscreen {
    param([int[]]$TargetPids)

    if (-not $TargetPids -or $TargetPids.Count -eq 0) { return 0 }

    $script:swept = 0
    $script:sweepPids = $TargetPids
    $cb = [Win32+EnumWindowsProc] {
        param([IntPtr]$hwnd, [IntPtr]$lparam)
        try {
            if (-not [Win32]::IsWindowVisible($hwnd)) { return $true }
            $procId = 0
            [Win32]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null
            if ($script:sweepPids -notcontains [int]$procId) { return $true }

            $rect = New-Object Win32+RECT
            [Win32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
            # Skip already off-screen windows (within tolerance)
            if ($rect.Left -lt -10000) { return $true }
            # Skip zero-size phantom windows
            if ($rect.Width -le 0 -or $rect.Height -le 0) { return $true }

            $flags = [Win32]::SWP_NOACTIVATE -bor [Win32]::SWP_NOZORDER -bor [Win32]::SWP_NOSIZE
            [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, -32000, -32000, 0, 0, $flags) | Out-Null
            $script:swept++
        } catch { }
        return $true
    }
    [Win32]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return $script:swept
}

# Capture the window into an in-memory Bitmap. Returns the Bitmap; caller disposes.
function Capture-BitmapFromWindow {
    param([IntPtr]$hwnd)

    Add-Type -AssemblyName System.Drawing

    $rect = New-Object Win32+RECT
    [Win32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
    $w = $rect.Width
    $h = $rect.Height
    if ($w -le 0 -or $h -le 0) {
        throw "Window has zero/negative size: $w x $h"
    }

    $bitmap = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $hdc = $graphics.GetHdc()
    try {
        $ok = [Win32]::PrintWindow($hwnd, $hdc, [Win32]::PW_RENDERFULLCONTENT)
        if (-not $ok) {
            throw "PrintWindow returned false"
        }
    } finally {
        $graphics.ReleaseHdc($hdc)
    }
    $graphics.Dispose()
    return $bitmap
}

# Compute a small per-cell average RGB grid from a bitmap. Used as a stable,
# noise-tolerant fingerprint for frame-to-frame comparison. Returns a flat
# array of doubles in [0..1].
function Compute-FingerprintGrid {
    param([System.Drawing.Bitmap]$bmp, [int]$Cols = 16, [int]$Rows = 9)

    $w = $bmp.Width
    $h = $bmp.Height
    $grid = New-Object 'double[]' ($Cols * $Rows * 3)

    # BitmapData lets us read pixels in bulk - much faster than GetPixel in a loop.
    $rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $stride = $data.Stride
        $totalBytes = $stride * $h
        $buf = New-Object 'byte[]' $totalBytes
        [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $totalBytes)

        for ($cy = 0; $cy -lt $Rows; $cy++) {
            $y0 = [int]([Math]::Floor($h * $cy / $Rows))
            $y1 = [int]([Math]::Floor($h * ($cy + 1) / $Rows))
            if ($y1 -le $y0) { $y1 = $y0 + 1 }
            for ($cx = 0; $cx -lt $Cols; $cx++) {
                $x0 = [int]([Math]::Floor($w * $cx / $Cols))
                $x1 = [int]([Math]::Floor($w * ($cx + 1) / $Cols))
                if ($x1 -le $x0) { $x1 = $x0 + 1 }

                # Sample a 3x3 sub-grid within the cell to keep work bounded
                $sumR = 0.0; $sumG = 0.0; $sumB = 0.0; $n = 0
                for ($sy = 0; $sy -lt 3; $sy++) {
                    $py = $y0 + [int]([Math]::Floor(($y1 - $y0) * $sy / 3))
                    for ($sx = 0; $sx -lt 3; $sx++) {
                        $px = $x0 + [int]([Math]::Floor(($x1 - $x0) * $sx / 3))
                        $idx = $py * $stride + $px * 4
                        # Format32bppArgb is BGRA in memory
                        $sumB += $buf[$idx]
                        $sumG += $buf[$idx + 1]
                        $sumR += $buf[$idx + 2]
                        $n++
                    }
                }
                $base = (($cy * $Cols) + $cx) * 3
                $grid[$base]     = $sumR / ($n * 255.0)
                $grid[$base + 1] = $sumG / ($n * 255.0)
                $grid[$base + 2] = $sumB / ($n * 255.0)
            }
        }
    } finally {
        $bmp.UnlockBits($data)
    }
    return $grid
}

function Compare-Fingerprints {
    param([double[]]$A, [double[]]$B)
    if ($A.Length -ne $B.Length) { return [double]::PositiveInfinity }
    $sum = 0.0
    for ($i = 0; $i -lt $A.Length; $i++) {
        $d = $A[$i] - $B[$i]
        if ($d -lt 0) { $d = -$d }
        $sum += $d
    }
    return $sum / $A.Length    # mean absolute delta per channel cell
}

# Detect "all single color" GPU-surface failure. Returns $true if frame is suspect.
function Test-FrameLooksBlank {
    param([System.Drawing.Bitmap]$bmp)
    $samples = @()
    foreach ($fy in 0.1, 0.5, 0.9) {
        foreach ($fx in 0.1, 0.5, 0.9) {
            $px = [int]([Math]::Floor($bmp.Width * $fx))
            $py = [int]([Math]::Floor($bmp.Height * $fy))
            $samples += $bmp.GetPixel($px, $py).ToArgb()
        }
    }
    return (($samples | Select-Object -Unique).Count -eq 1)
}

# ---------- Resolve paths + preflight ----------
if (-not (Test-Path -LiteralPath $Pbip)) {
    Write-Error "PBIP not found: $Pbip"
    exit 1
}
$PbipFull = (Resolve-Path -LiteralPath $Pbip).Path
$PbipStem = [System.IO.Path]::GetFileNameWithoutExtension($PbipFull)

$OutDir = Split-Path -Parent $Out
if ($OutDir -and -not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutFull = if ([System.IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path -Path (Get-Location) -ChildPath $Out }

$resolvedExe = Resolve-PbiDesktopPath -Explicit $PbiDesktopExe
if (-not $resolvedExe) {
    Write-Error @"
PBI Desktop executable not found. Tried (in order):
  1. -PbiDesktopExe parameter
  2. `$env:PBI_DESKTOP_EXE
  3. .pbip file association in HKCR
  4. App Paths registry (HKLM/HKCU)
  5. Standard install locations (Program Files, Program Files (x86), WindowsApps shim)
  6. PATH lookup

Fix: install PBI Desktop, set `$env:PBI_DESKTOP_EXE to its full path, or pass -PbiDesktopExe explicitly.
"@
    exit 1
}
$PbiDesktopExe = $resolvedExe
Write-Host "Resolved PBI Desktop: $PbiDesktopExe"

$existingProcs = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue
$alreadyRunning = $existingProcs -and $existingProcs.Count -gt 0

if (-not $alreadyRunning -and -not $AssumeLoggedIn -and $ReusePid -eq 0) {
    [Console]::Error.WriteLine("FIRST_LAUNCH_LIKELY_NEEDS_SSO")
    [Console]::Error.WriteLine("No PBIDesktop process is running. Open Power BI Desktop, sign in, then re-run with -AssumeLoggedIn.")
    exit 2
}

# ---------- Resolve .Report folder for pre-launch edits ----------
# The .pbip points to a sibling .Report folder. We resolve it so we can edit
# pages.json (activePageName) and report.json (outspacePane.expanded) before
# launch, with guaranteed restore after.
$pbipDir = Split-Path -Parent $PbipFull
try {
    $pbipObj = Get-Content -LiteralPath $PbipFull -Raw | ConvertFrom-Json
    $reportRel = $pbipObj.artifacts[0].report.path
} catch {
    Write-Error "Failed to parse $PbipFull as JSON: $($_.Exception.Message)"
    exit 1
}
$reportRoot = if ([System.IO.Path]::IsPathRooted($reportRel)) { $reportRel } else { Join-Path $pbipDir $reportRel }
if (-not (Test-Path -LiteralPath $reportRoot)) {
    Write-Error ".Report folder not found at $reportRoot (resolved from $PbipFull)"
    exit 1
}
Write-Host "Report root: $reportRoot"

# Load editor helper
. (Join-Path $PSScriptRoot "edit-report-for-capture.ps1")

# ---------- Machine-wide capture gate ----------
# Multiple agent sessions (or parallel subagents) can invoke Path A at the same
# time. Two overlapping captures race each other: Stage-0 window identification
# can latch onto the OTHER run's PBI window (wrong capture + cross-session
# kill), and same-report runs clobber each other's pages.json/report.json edit
# locks. Serialize captures machine-wide with a named mutex: one capture at a
# time; later runs queue up to -CaptureGateWaitSec, then exit 6 (retryable).
# Acquired BEFORE stale-lock recovery so a queued run always starts from the
# clean state the previous run's finally block left behind.
$captureGate = $null
$gateAcquired = $false
try {
    $captureGate = New-Object System.Threading.Mutex($false, "Global\pbi-troubleshooter-capture-gate")
    try { $gateAcquired = $captureGate.WaitOne([TimeSpan]::FromSeconds($CaptureGateWaitSec)) }
    catch [System.Threading.AbandonedMutexException] { $gateAcquired = $true }   # holder died mid-run; we own the gate now
} catch {
    Write-Warning "Capture gate unavailable ($($_.Exception.Message)); proceeding UNGATED - concurrent captures may race."
    $captureGate = $null
}
if ($captureGate -and -not $gateAcquired) {
    [Console]::Error.WriteLine("CAPTURE_GATE_TIMEOUT: another Path A capture is still running after ${CaptureGateWaitSec}s. Retry when it finishes, or raise -CaptureGateWaitSec.")
    exit 6
}
if ($gateAcquired) { Write-Host "Capture gate acquired (one Path A capture at a time, machine-wide)." }

# Recovery: if a previous run died mid-edit (Ctrl+C, kill), restore from the
# lock file before doing anything else. This is idempotent — no lock = no-op.
[void](Recover-StaleEditLock -ReportRoot $reportRoot)

# ---------- Resolve target PID ----------
$targetPid = 0
$weSpawned = $false

# Snapshot pre-existing PBI-family PIDs so we can identify the ones we cause to
# spawn. This matters because:
#   - The Store shim (PBIDesktopStore.exe) launches the real PBIDesktop.exe, which
#     can have a different PID and survive the shim's death.
#   - PBI Desktop also spawns helpers (Mashup engine, msmdsrv.exe / Analysis
#     Services, etc.) that we own and should clean up.
function Get-PbiFamilyPids {
    $names = @('PBIDesktop', 'PBIDesktopStore', 'msmdsrv', 'Microsoft.Mashup.Container*')
    $pids = @()
    foreach ($n in $names) {
        $found = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($found) { $pids += $found.Id }
    }
    return ,$pids
}

# Force-close ONLY the PIDs we identified as ours during this run (shim + window
# owner, populated as the script progresses). We NEVER touch any PID present in
# $preExistingPids — that's an existing PBI Desktop session the user is working
# in. Idempotent and safe to call from error paths.
function Close-OurPbiInstance {
    if (-not $script:weSpawned) { return }
    $pids = @($script:ownPidsToKill)
    if ($script:KeepOpen) {
        $joined = ($pids -join ', ')
        Write-Host "Leaving PBIDesktop open per -KeepOpen. Our PIDs: $joined"
        return
    }
    if ($pids.Count -eq 0) { return }
    foreach ($p in $pids) {
        if ($script:preExistingPids -contains $p) {
            Write-Warning "Refusing to kill PID $p - it pre-existed our launch (user's other session)."
            continue
        }
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $procName = $proc.ProcessName
        Write-Host "Closing OUR PBIDesktop PID $p ($procName) without save..."
        try { Stop-Process -Id $p -Force -ErrorAction Stop }
        catch { Write-Warning "Could not stop PID ${p}: $($_.Exception.Message)" }
    }
    Start-Sleep -Milliseconds 500
    foreach ($p in $pids) {
        if ($script:preExistingPids -contains $p) { continue }
        if (Get-Process -Id $p -ErrorAction SilentlyContinue) {
            Start-Sleep -Milliseconds 1000
            try { Stop-Process -Id $p -Force -ErrorAction Stop } catch { }
        }
    }
}

# ---------- Orphan-PID lock ----------
# The finally-block cleanup below covers every in-script exit path, but it CANNOT
# run if this powershell.exe is itself hard-killed (harness tool timeout, Ctrl+C
# on some hosts, task kill). The spawned PBIDesktop.exe survives as an orphan.
# Mitigation: record our spawned PIDs (+ process StartTime, to defeat PID reuse)
# in a global lock file. On the NEXT run, any entry whose owning script is dead
# gets its still-alive PBI-family PIDs force-killed. A named mutex guards the
# read-modify-write so concurrent capture runs don't clobber each other.
$PidLockPath = Join-Path $env:LOCALAPPDATA "pbi-troubleshooter\spawned-pids.json"
$thisScriptStart = (Get-Process -Id $PID).StartTime.ToString("o")

# All PID-lock operations are best-effort: a failure here (mutex denied, disk
# full, corrupt JSON) must never abort a capture run — worst case is a stale
# lock entry, which the StartTime match makes harmless (never a wrong kill).
function Invoke-WithPidLockMutex {
    param([Parameter(Mandatory)][scriptblock]$Body)
    $mutex = $null
    $acquired = $false
    try {
        try {
            $mutex = New-Object System.Threading.Mutex($false, "Global\pbi-troubleshooter-pidlock")
            try { $acquired = $mutex.WaitOne(5000) }
            catch [System.Threading.AbandonedMutexException] { $acquired = $true }
        } catch { $mutex = $null }
        try { & $Body }
        catch { Write-Warning "PID-lock operation failed (non-fatal): $($_.Exception.Message)" }
    } finally {
        if ($mutex) {
            if ($acquired) { try { [void]$mutex.ReleaseMutex() } catch { } }
            $mutex.Dispose()
        }
    }
}

function Read-PidLockRuns {
    if (-not (Test-Path -LiteralPath $script:PidLockPath)) { return @() }
    try {
        $doc = Get-Content -LiteralPath $script:PidLockPath -Raw | ConvertFrom-Json
        if ($doc.runs) { return @($doc.runs) }
    } catch { }
    return @()
}

function Write-PidLockRuns {
    param($Runs)
    $dir = Split-Path -Parent $script:PidLockPath
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $payload = @{ runs = @($Runs) } | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($script:PidLockPath, $payload, (New-Object System.Text.UTF8Encoding($false)))
}

# Record the PIDs we own so a future run can clean up if we die uncleanly.
# Skipped under -KeepOpen: the user asked for the instance to stay open, so it
# must never be eligible for orphan recovery.
function Register-OwnPidsInLock {
    param([int[]]$Pids)
    if ($script:KeepOpen) { return }
    if (-not $Pids -or $Pids.Count -eq 0) { return }
    $entries = @()
    foreach ($p in $Pids) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            try { $entries += @{ procId = [int]$p; start = $proc.StartTime.ToString("o") } } catch { }
        }
    }
    if ($entries.Count -eq 0) { return }
    Invoke-WithPidLockMutex {
        $runs = @(Read-PidLockRuns | Where-Object { $_.scriptPid -ne $PID })
        $runs += @{ scriptPid = $PID; scriptStart = $script:thisScriptStart; pids = $entries }
        Write-PidLockRuns -Runs $runs
    }
}

function Remove-OwnPidLockEntry {
    Invoke-WithPidLockMutex {
        $runs = @(Read-PidLockRuns | Where-Object { $_.scriptPid -ne $PID })
        Write-PidLockRuns -Runs $runs
    }
}

# ---------- Ownership proof for post-launch PBI processes ----------
# "Spawned after our snapshot" is NOT proof a PBI process is ours: the operator
# (or a concurrent agent session) can open PBI Desktop DURING our capture window.
# Without this check, that fresh instance could be swept off-screen, mis-
# captured, and force-killed. A new PBI-family PID only counts as OURS if it is
# the PID we spawned, or its command line references the .pbip we launched
# (the Store shim forwards the argument to the real PBIDesktop.exe).
# Cached per PID — WMI lookups aren't free and the sweep loop runs at 50ms.
$PidOwnershipCache = @{}
function Test-PidIsOurs {
    param([int]$ProcId)
    if ($ProcId -le 0) { return $false }
    if ($ProcId -eq $script:targetPid) { return $true }
    if ($script:PidOwnershipCache.ContainsKey($ProcId)) { return $script:PidOwnershipCache[$ProcId] }
    $ours = $false
    try {
        $ci = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcId" -ErrorAction Stop
        if ($ci -and $ci.CommandLine) {
            $ours = ($ci.CommandLine.IndexOf($script:PbipStem, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        } else {
            # Command line not readable (rare for same-user processes). Fall back
            # to the pre-check behavior (assume ours) rather than risk a leak.
            $ours = $true
        }
    } catch { $ours = $true }
    $script:PidOwnershipCache[$ProcId] = $ours
    return $ours
}

# Kill PBI-family orphans leaked by previous runs that died before their finally
# block. A run's entry is only actioned if its owning script process is gone
# (PID + StartTime both checked, so a reused PID never counts as "alive").
# Each orphan PID must ALSO match its recorded StartTime and be a PBI-family
# process name before we kill it — a reused PID is never touched.
function Recover-OrphanedPbiPids {
    Invoke-WithPidLockMutex {
        $runs = Read-PidLockRuns
        if ($runs.Count -eq 0) { return }
        $keep = @()
        foreach ($run in $runs) {
            $ownerAlive = $false
            if ($run.scriptPid) {
                $owner = Get-Process -Id $run.scriptPid -ErrorAction SilentlyContinue
                if ($owner -and $run.scriptStart) {
                    try { if ($owner.StartTime.ToString("o") -eq $run.scriptStart) { $ownerAlive = $true } } catch { }
                }
            }
            if ($ownerAlive) { $keep += $run; continue }
            foreach ($entry in @($run.pids)) {
                $proc = Get-Process -Id $entry.procId -ErrorAction SilentlyContinue
                if (-not $proc) { continue }
                $nameOk = $proc.ProcessName -match '^(PBIDesktop|PBIDesktopStore|msmdsrv|Microsoft\.Mashup)'
                $startOk = $false
                try { $startOk = ($proc.StartTime.ToString("o") -eq $entry.start) } catch { }
                if ($nameOk -and $startOk) {
                    Write-Warning "Recovering orphaned $($proc.ProcessName) PID $($entry.procId) leaked by a dead run (script PID $($run.scriptPid)). Killing it."
                    try { Stop-Process -Id $entry.procId -Force -ErrorAction Stop }
                    catch { Write-Warning "Could not stop orphan PID $($entry.procId): $($_.Exception.Message)" }
                }
            }
        }
        Write-PidLockRuns -Runs $keep
    }
}

# Recover orphans BEFORE snapshotting pre-existing PIDs — otherwise a leaked
# instance from a dead run lands in $preExistingPids and becomes untouchable.
Recover-OrphanedPbiPids

$preExistingPids = Get-PbiFamilyPids
$ownPidsToKill = @()

# ---------- Apply pre-launch edits (page selection + filter pane collapse) ----------
# Edits are reversible. Save-ReportEditState captures byte-exact originals; the
# finally block at script end calls Restore-ReportEditState. PowerShell's `exit`
# runs finally blocks, so any structured exit also restores. Ctrl+C MAY skip the
# finally on some hosts — if pages.json/report.json show up dirty in git after a
# crash, just `git restore` them.
$editState = Save-ReportEditState -ReportRoot $reportRoot
$editsApplied = $false
if ($PageId) {
    Write-Host "Pre-launch edit: setting activePageName to '$PageId'"
    [void](Set-ActivePage -State $editState -PageId $PageId)
}
if (-not $NoCollapseFilterPane) {
    Write-Host "Pre-launch edit: collapsing filter pane"
    [void](Collapse-FilterPane -State $editState)
}
$editsApplied = $true
# Persist the lock file with the original content; if the process dies before
# the finally block can restore, the next run picks this up via Recover-StaleEditLock.
Write-EditLock -State $editState

try {
if ($ReusePid -gt 0) {
    if (-not (Get-Process -Id $ReusePid -ErrorAction SilentlyContinue)) {
        Write-Error "ReusePid $ReusePid not found"; exit 1
    }
    $targetPid = $ReusePid
    Write-Host "Reusing existing PBIDesktop PID $targetPid"
} else {
    Write-Host "Launching PBI Desktop with: $PbipFull"
    # Launch minimized when we will hide. PBI Desktop tolerates minimized state
    # (it's an ordinary window state). The window then appears only in the taskbar
    # during launch, never on the desktop. -WindowStyle Hidden crashed PBI Desktop
    # during WPF init, so we don't use that. If the user wants to see the window,
    # we launch Normal.
    $launchStyle = if ($VisibleDuringCapture) { 'Normal' } else { 'Minimized' }
    $proc = Start-Process -FilePath $PbiDesktopExe -ArgumentList "`"$PbipFull`"" -PassThru -WindowStyle $launchStyle
    $targetPid = $proc.Id
    $weSpawned = $true
    Write-Host "Spawned PID: $targetPid (shim/initial; -WindowStyle $launchStyle)"

    # Track the spawn immediately: if we exit (or are killed) before Stage 0
    # even finds a window, cleanup/recovery still knows what to close.
    $ownPidsToKill = @($targetPid)
    Register-OwnPidsInLock -Pids $ownPidsToKill

    # Aggressively sweep the splash screen + any other early windows off-screen.
    # PBI Desktop shows a splash window (with logo + "loading...") for ~1-3 seconds
    # before its main window appears. We sweep every 50ms for the first 4 seconds
    # to catch the splash the instant it becomes visible.
    if (-not $VisibleDuringCapture) {
        $sweepStart = Get-Date
        $sweepDeadline = $sweepStart.AddSeconds(4)
        while ((Get-Date) -lt $sweepDeadline) {
            $candidates = @($targetPid)
            foreach ($p in (Get-PbiFamilyPids)) {
                if ($preExistingPids -notcontains $p -and (Test-PidIsOurs -ProcId $p)) { $candidates += $p }
            }
            $candidates = $candidates | Select-Object -Unique
            [void](Move-AllOwnedWindowsOffscreen -TargetPids $candidates)
            Start-Sleep -Milliseconds 50
        }
    }
}

# ---------- Stage 0: window appears ----------
# We look for a window owned by ANY PBI-family PID that spawned after our launch
# (i.e., not in the pre-launch snapshot). If the operator has other PBI Desktop
# instances open, those are in $preExistingPids and we ignore them entirely.
Write-Host "Stage 0: waiting up to 30s for OUR main window (excluding pre-existing PBI sessions)..."
if ($ReusePid -gt 0) {
    $r = Wait-ForOwnedWindow -ExcludePids @() -ExtraIncludePids @($targetPid) -TimeoutSec 30
} else {
    $r = Wait-ForOwnedWindow -ExcludePids $preExistingPids -ExtraIncludePids @($targetPid) -TimeoutSec 30
}
$hwnd = $r.Hwnd
if ($hwnd -eq [IntPtr]::Zero) {
    if (-not (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine("PBIDESKTOP_CRASHED: spawned process exited before main window appeared")
        exit 3
    }
    [Console]::Error.WriteLine("WINDOW_NOT_FOUND_TIMEOUT: no main window for our spawn after 30s")
    exit 4
}
$windowOwnerPid = $r.Pid
Write-Host ("  hwnd=0x{0:X} class='{1}' window_owner_pid={2}" -f $hwnd.ToInt64(), (Get-WindowClass $hwnd), $windowOwnerPid)
# Track our own PIDs only. We will NEVER kill anything in $preExistingPids and we
# only kill these two specific PIDs at end-of-run. If they are the same process,
# the second kill is a no-op.
$ownPidsToKill = @($targetPid, $windowOwnerPid) | Where-Object { $_ -gt 0 } | Select-Object -Unique
Register-OwnPidsInLock -Pids $ownPidsToKill

# CRITICAL: move off-screen IMMEDIATELY upon window detection, before the title
# gate runs (~10-15s). Otherwise the user sees PBI Desktop sitting on their
# screen for the entire title gate, interrupting whatever they're doing.
# Without this, the visible flash was the full title-gate duration.
if (-not $VisibleDuringCapture) {
    Move-WindowOffscreenKeepSize -hwnd $hwnd
    Write-Host "  moved window off-screen immediately (pre-title-gate)"
}

# ---------- Stage 1: window-title gate (file loaded) ----------
# PBI Desktop's main window title goes from '' (or 'Power BI Desktop') to one
# that includes the .pbip stem once the file is parsed. This is a free signal
# that file load has completed.
Write-Host ("Stage 1: title-gate (waiting for title to include '{0}', max ${TitleGateSec}s)..." -f $PbipStem)
$gateStart = Get-Date
$gateDeadline = $gateStart.AddSeconds($TitleGateSec)
$titleSeen = $false
while ((Get-Date) -lt $gateDeadline) {
    if ((Get-Date) -gt $scriptStart.AddSeconds($HardCapSec)) {
        [Console]::Error.WriteLine("RENDER_TIMEOUT: hard cap during title gate")
        exit 5
    }
    $aliveOwners = @($ownPidsToKill | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($aliveOwners.Count -eq 0) {
        [Console]::Error.WriteLine("PBIDESKTOP_CRASHED: all our owned PIDs exited during title gate")
        exit 3
    }
    # Keep sweeping any new windows (e.g., late-spawned dialogs) off-screen.
    if (-not $VisibleDuringCapture) {
        [void](Move-AllOwnedWindowsOffscreen -TargetPids $aliveOwners)
    }
    $r2 = Find-MainWindowForPids -TargetPids $aliveOwners
    $hwnd = $r2.Hwnd
    if ($hwnd -ne [IntPtr]::Zero) {
        $t = Get-WindowText $hwnd
        if ($t -and $t.IndexOf($PbipStem, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $titleSeen = $true
            Write-Host ("  title='{0}' (gate cleared in {1:N1}s)" -f $t, ((Get-Date) - $gateStart).TotalSeconds)
            break
        }
    }
    Start-Sleep -Milliseconds 200
}
if (-not $titleSeen) {
    Write-Warning "Title gate did not see '$PbipStem' within ${TitleGateSec}s; proceeding to stability poll anyway."
}

# Re-resolve hwnd in case PBI swapped windows during load.
$aliveOwners = @($ownPidsToKill | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
if ($aliveOwners.Count -eq 0) {
    [Console]::Error.WriteLine("PBIDESKTOP_CRASHED: all our owned PIDs exited after title gate")
    exit 3
}
$r3 = Find-MainWindowForPids -TargetPids $aliveOwners
$hwnd = $r3.Hwnd
if ($hwnd -eq [IntPtr]::Zero) {
    [Console]::Error.WriteLine("WINDOW_NOT_FOUND_TIMEOUT: window vanished after title gate")
    exit 4
}
# If a new PID owns the window, track it too.
if ($r3.Pid -gt 0 -and $ownPidsToKill -notcontains $r3.Pid) {
    $ownPidsToKill = @($ownPidsToKill + $r3.Pid) | Select-Object -Unique
    Register-OwnPidsInLock -Pids $ownPidsToKill
    Write-Host "  added new window-owning PID $($r3.Pid) to own-pids-to-kill list"
}

# ---------- Hide window (off-screen) + resize before stability polling ----------
# Excel-style: move the window to (-32000, -32000) so it never sits over what
# the user is doing. We DO NOT use ShowWindow(SW_HIDE) because PBI Desktop's
# WPF/DirectX renderer crashes when its window is in the SW_HIDE state.
# Off-screen keeps the window "visible" to Windows (render pipeline runs) but
# invisible on any real monitor.
$captureMode = if ($VisibleDuringCapture) { 'visible' } else { 'offscreen' }
if (-not $NoResize) {
    Write-Host ("Resizing window to ${ResizeWidth}x${ResizeHeight} (capture_mode=$captureMode)...")
    Resize-WindowInPlace -hwnd $hwnd -Width $ResizeWidth -Height $ResizeHeight
    Start-Sleep -Milliseconds 400   # let WM_SIZE propagate
}
if (-not $VisibleDuringCapture) {
    Move-WindowOffscreen -hwnd $hwnd -Width $ResizeWidth -Height $ResizeHeight
    Start-Sleep -Milliseconds 300
}

# ---------- Stage 2: pixel-stability poll ----------
Write-Host ("Stage 2: pixel-stability poll (every ${StabilityPollSec}s, need ${StabilityRequiredFrames} consecutive frames within {0:P2}, max ${StabilityMaxSec}s)..." -f $StabilityThreshold)
$polStart = Get-Date
$polDeadline = $polStart.AddSeconds($StabilityMaxSec)

$prevFp = $null
$consecutiveStable = 0
$pollIdx = 0
$stable = $false

while ((Get-Date) -lt $polDeadline) {
    if ((Get-Date) -gt $scriptStart.AddSeconds($HardCapSec)) {
        [Console]::Error.WriteLine("RENDER_TIMEOUT: hard cap during stability poll")
        exit 5
    }
    $aliveOwners = @($ownPidsToKill | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($aliveOwners.Count -eq 0) {
        [Console]::Error.WriteLine("PBIDESKTOP_CRASHED: all our owned PIDs exited during stability poll")
        exit 3
    }
    $rPoll = Find-MainWindowForPids -TargetPids $aliveOwners
    $hwnd = $rPoll.Hwnd
    if ($hwnd -eq [IntPtr]::Zero) { Start-Sleep -Seconds 1; continue }
    if ($rPoll.Pid -gt 0 -and $ownPidsToKill -notcontains $rPoll.Pid) {
        $ownPidsToKill = @($ownPidsToKill + $rPoll.Pid) | Select-Object -Unique
        Register-OwnPidsInLock -Pids $ownPidsToKill
    }

    try {
        $bmp = Capture-BitmapFromWindow -hwnd $hwnd
    } catch {
        Start-Sleep -Seconds $StabilityPollSec; continue
    }

    # GPU-blank guard: if first frame is single-color, the off-screen approach
    # itself failed (rare). Surface the issue rather than silently capturing junk.
    if ($pollIdx -eq 0 -and (Test-FrameLooksBlank -bmp $bmp)) {
        Write-Warning "First captured frame is single-color. Capture mode=$captureMode may not work for this DirectX path; consider -VisibleDuringCapture."
    }

    $fp = Compute-FingerprintGrid -bmp $bmp
    $bmp.Dispose()
    $pollIdx++

    if ($prevFp -ne $null) {
        $delta = Compare-Fingerprints -A $prevFp -B $fp
        if ($delta -lt $StabilityThreshold) { $consecutiveStable++ } else { $consecutiveStable = 0 }
        Write-Host ("  poll #{0}: delta={1:N5} stable_streak={2}" -f $pollIdx, $delta, $consecutiveStable)
        if ($consecutiveStable -ge ($StabilityRequiredFrames - 1)) {
            $stable = $true
            Write-Host ("  stability reached after {0:N1}s" -f ((Get-Date) - $polStart).TotalSeconds)
            break
        }
    } else {
        Write-Host ("  poll #{0}: baseline" -f $pollIdx)
    }

    $prevFp = $fp
    Start-Sleep -Seconds $StabilityPollSec
}

if (-not $stable) {
    Write-Warning "Stability not reached within ${StabilityMaxSec}s; capturing best-available frame anyway."
}

# ---------- Final capture ----------
$aliveOwners = @($ownPidsToKill | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
if ($aliveOwners.Count -eq 0) {
    [Console]::Error.WriteLine("PBIDESKTOP_CRASHED: all our owned PIDs exited before final capture")
    exit 3
}
$rFinal = Find-MainWindowForPids -TargetPids $aliveOwners
$hwnd = $rFinal.Hwnd
if ($hwnd -eq [IntPtr]::Zero) {
    [Console]::Error.WriteLine("WINDOW_NOT_FOUND_TIMEOUT: window vanished before final capture")
    exit 4
}
$finalTitle = Get-WindowText $hwnd

try {
    $bmp = Capture-BitmapFromWindow -hwnd $hwnd
    $blank = Test-FrameLooksBlank -bmp $bmp
    $bmp.Save($OutFull, [System.Drawing.Imaging.ImageFormat]::Png)
    $finalW = $bmp.Width; $finalH = $bmp.Height
    $bmp.Dispose()

    $elapsed = ((Get-Date) - $scriptStart).TotalSeconds
    Write-Host ("Saved {0}  ({1} x {2})  total_elapsed={3:N1}s  title='{4}'" -f $OutFull, $finalW, $finalH, $elapsed, $finalTitle)

    if ($blank) {
        Write-Warning "Captured frame appears to be a single color. PrintWindow may have hit a GPU-surface case; phase 2 has no fallback yet."
    }

    # ---------- Canvas-only crop ----------
    # The full-window capture includes PBI Desktop chrome (ribbon, page tabs,
    # Build/Visualizations/Data pane). For multimodal review we want just the
    # canvas, which is what an end-user sees in a published report.
    #
    # Crop region calibrated empirically per common capture size. PBI Desktop's
    # chrome (ribbon, page tabs, Build pane) is roughly FIXED in absolute pixels
    # regardless of window size, so the canvas does NOT scale proportionally to
    # the capture. Hardcode the two sizes we ship; everything else falls back to
    # proportional from 2400x1500 (best-effort) or override via -CanvasRect.
    if (-not $NoCropCanvas) {
        if ($ResizeWidth -eq 2400 -and $ResizeHeight -eq 1500) {
            $cropX = 95;  $cropY = 335; $cropW = 1500; $cropH = 830
        } elseif ($ResizeWidth -eq 1800 -and $ResizeHeight -eq 1125) {
            # Tighter horizontal crop than the 2400 case: at 1800 wide the Build
            # pane chrome starts earlier (~x=985) so we stop before it.
            $cropX = 95;  $cropY = 335; $cropW = 890; $cropH = 505
        } else {
            # Fallback: proportional from 2400x1500 baseline. Pass -CanvasRect if
            # the result clips chrome or misses canvas.
            $baseW = 2400; $baseH = 1500
            $cropX = [int][Math]::Round(95   * $ResizeWidth  / $baseW)
            $cropY = [int][Math]::Round(335  * $ResizeHeight / $baseH)
            $cropW = [int][Math]::Round(1500 * $ResizeWidth  / $baseW)
            $cropH = [int][Math]::Round(830  * $ResizeHeight / $baseH)
        }
        if ($CanvasRect) {
            $parts = $CanvasRect -split ','
            if ($parts.Count -ne 4) {
                Write-Warning "Invalid -CanvasRect '$CanvasRect' (expected 'x,y,w,h'); skipping crop."
            } else {
                $cropX = [int]$parts[0]; $cropY = [int]$parts[1]
                $cropW = [int]$parts[2]; $cropH = [int]$parts[3]
            }
        }
        try {
            $srcImg = [System.Drawing.Image]::FromFile($OutFull)
            # Clamp the crop rect to the source image (defensive: a smaller window
            # capture or a different resolution shouldn't throw OutOfBounds).
            $maxX = $srcImg.Width - 1
            $maxY = $srcImg.Height - 1
            $cropX = [Math]::Max(0, [Math]::Min($cropX, $maxX))
            $cropY = [Math]::Max(0, [Math]::Min($cropY, $maxY))
            $cropW = [Math]::Max(1, [Math]::Min($cropW, $srcImg.Width - $cropX))
            $cropH = [Math]::Max(1, [Math]::Min($cropH, $srcImg.Height - $cropY))

            $rect = New-Object System.Drawing.Rectangle($cropX, $cropY, $cropW, $cropH)
            $cropped = New-Object System.Drawing.Bitmap($rect.Width, $rect.Height)
            $g = [System.Drawing.Graphics]::FromImage($cropped)
            $destRect = New-Object System.Drawing.Rectangle(0, 0, $rect.Width, $rect.Height)
            $g.DrawImage($srcImg, $destRect, $rect, [System.Drawing.GraphicsUnit]::Pixel)

            # Output path: same directory as $OutFull, with "_canvas" before extension.
            $outDir = Split-Path -Parent $OutFull
            $outBase = [System.IO.Path]::GetFileNameWithoutExtension($OutFull)
            $outExt = [System.IO.Path]::GetExtension($OutFull)
            $cropOut = Join-Path $outDir "${outBase}_canvas${outExt}"

            $cropped.Save($cropOut, [System.Drawing.Imaging.ImageFormat]::Png)
            Write-Host ("Saved canvas-only crop {0}  ({1} x {2})" -f $cropOut, $rect.Width, $rect.Height)

            $g.Dispose(); $cropped.Dispose(); $srcImg.Dispose()

            # -CanvasOnly: delete the full-window capture now that the canvas crop
            # exists. Caller signaled they only want the canvas — halves disk usage,
            # and removes ambiguity about which file to read into multimodal.
            if ($CanvasOnly -and (Test-Path -LiteralPath $OutFull)) {
                Remove-Item -LiteralPath $OutFull -Force
                Write-Host "  -CanvasOnly: removed full-window capture, kept canvas crop only"
            }
        } catch {
            Write-Warning "Canvas crop failed: $($_.Exception.Message). Full-window capture is still at $OutFull."
        }
    }
} catch {
    # NOTE: must not use Write-Error here — with $ErrorActionPreference = "Stop"
    # it throws a NEW terminating error, skipping the exit below (the old code
    # leaked the PBI instance this way). Plain stderr write + exit instead;
    # the finally block handles cleanup.
    [Console]::Error.WriteLine("CAPTURE_FAILED: $($_.Exception.Message)")
    exit 1
}

} finally {
    # Cleanup runs on EVERY exit path — success, error exits (3/4/5), and thrown
    # errors. PowerShell's `exit` executes finally blocks, so the structured
    # error exits inside the try (WINDOW_NOT_FOUND_TIMEOUT, RENDER_TIMEOUT, ...)
    # all close the PBI Desktop instance we spawned. Before this block existed,
    # those exits leaked one live PBIDesktop.exe per failed run.
    Close-OurPbiInstance
    Remove-OwnPidLockEntry
    # Always restore the report files to their pre-edit state — even on errors,
    # exits, or hard window-not-found / crash exits inside the outer try block.
    if ($editsApplied) {
        Write-Host "Restoring report.json + pages.json to pre-edit state..."
        Restore-ReportEditState -State $editState
        Remove-EditLock -State $editState
    }
    # Release the machine-wide capture gate LAST — after the instance is closed
    # and report files are restored — so a queued run starts from clean state.
    if ($script:gateAcquired -and $script:captureGate) { try { [void]$script:captureGate.ReleaseMutex() } catch { } }
    if ($script:captureGate) { $script:captureGate.Dispose() }
}

exit 0
