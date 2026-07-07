# ============================================================================
# doommake-tweak.ps1
# ============================================================================
# Tweaks a fresh DoomMake project — pre-step IWAD fix + template copy +
# entry target replacement
# ============================================================================

param(
    [string]$IwadPath = ""
)

$ErrorActionPreference = "Stop"
$base = Get-Location

# ============================================================================
# EDITABLE SECTION — everything you'll manually add to later lives here.
# Add/remove/comment-out lines below; nothing further down needs to change.
# ============================================================================

# ----------------------------------------------------------------------------
# File Templates to copy: SourceFile / DestPath / Prefix
# ----------------------------------------------------------------------------
$FileTemplates = @(
    @{ SourceFile = "doommake-tweak-FILE_credits.txt";        DestPath = ".\src";                Prefix = "FILE_" }
    @{ SourceFile = "doommake-tweak-FILE_COMPLVL.txt";        DestPath = ".\src\assets\_global";  Prefix = "FILE_" }
    @{ SourceFile = "doommake-tweak-FILE_UMAPINFO.txt";       DestPath = ".\src\assets\_global";  Prefix = "FILE_" }
    @{ SourceFile = "doommake-tweak-FILE_doom1-playpal.cube"; DestPath = ".\";                    Prefix = "FILE_" }
    @{ SourceFile = "doommake-tweak-DECO_main.dh";            DestPath = ".\src\decohack";        Prefix = "DECO_" }
    @{ SourceFile = "doommake-tweak-DECO_strings.dh";         DestPath = ".\src\decohack";        Prefix = "DECO_" }

    @{ SourceFile = "doommake-tweak-WADMERGE_merge-doDehWad.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
    @{ SourceFile = "doommake-tweak-WADMERGE_merge-editorrelease.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
    @{ SourceFile = "doommake-tweak-WADMERGE_merge-editorrelease-map99.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
    @{ SourceFile = "doommake-tweak-WADMERGE_merge-texturesrelease.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
    @{ SourceFile = "doommake-tweak-WADMERGE_merge-texturesrelease-map99.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
    @{ SourceFile = "doommake-tweak-WADMERGE_merge-palette.txt"; DestPath = ".\scripts"; Prefix = "WADMERGE_" }
)

# ----------------------------------------------------------------------------
# Entry Targets to fully replace: ConfFile / EntryName
# ----------------------------------------------------------------------------
$EntryReplacements = @(
    @{ ConfFile = "doommake-tweak_FUNC-REPLACE_make.conf";    EntryName = "make" }
    @{ ConfFile = "doommake-tweak_FUNC-REPLACE_release.conf"; EntryName = "release" }
)

# ----------------------------------------------------------------------------
# Blocks to Insert into doommake.script (functions + entry targets),
# placed just before the first stock "check entry", in listed order
# ----------------------------------------------------------------------------
$AppendBlocks = @(
    "doommake-tweak_FUNC-MAKE-TARGETS_all.conf"
    "doommake-tweak_FUNC-MAKE-TARGETS_final.conf"
)

# ============================================================================
# END EDITABLE SECTION
# ============================================================================

Write-Host ""
Write-Host "==============================================="
Write-Host "=== DoomMake Project Tweaker for MBF21 Wads ==="
Write-Host "==============================================="
Write-Host ""

# Validate we're in a DoomMake project
if (!(Test-Path "doommake.script")) {
    Write-Host "ERROR: doommake.script not found. Are you in a DoomMake project root?" -ForegroundColor Red
    exit 1
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ============================================================================
# PRE-STEP: Resolve {{PROJECT_IWAD}} placeholder in doommake.properties
# ============================================================================
# doommake --project-type creates doommake.properties from a template that
# contains the literal placeholder {{PROJECT_IWAD}}. When piped via stdin the
# value may not be substituted. We accept the real IWAD path as an optional
# first argument and patch the file directly before running any doommake cmds.
#
# Usage: doommake-tweak.ps1 [-IwadPath "D:\path\to\doom2.wad"]

$propsPath = ".\doommake.properties"
if (Test-Path $propsPath) {
    $propsContent = Get-Content $propsPath -Raw

    if ($propsContent -match '\{\{PROJECT_IWAD\}\}') {
        # If no path was passed as a param, try to find it in the file itself
        # (some doommake versions write it correctly on a separate key)
        if (-not $IwadPath) {
            $iwadLine = (Get-Content $propsPath) | Where-Object { $_ -match '^\s*iwad\s*=' -and $_ -notmatch '\{\{' } | Select-Object -First 1
            if ($iwadLine) {
                $IwadPath = ($iwadLine -split '=', 2)[1].Trim()
            }
        }

        if ($IwadPath -and (Test-Path $IwadPath)) {
            Write-Host "  [Fixing] Replacing {{PROJECT_IWAD}} -> $IwadPath" -ForegroundColor Cyan
            $propsContent = $propsContent -replace '\{\{PROJECT_IWAD\}\}', ($IwadPath -replace '\\', '\\')
            [System.IO.File]::WriteAllText($propsPath, $propsContent, $utf8NoBom)
        } else {
            Write-Host "  [WARNING] {{PROJECT_IWAD}} placeholder found but no valid IWAD path available." -ForegroundColor Red
            Write-Host "            Pass it with: doommake-tweak.ps1 -IwadPath 'D:\path\to\doom2.wad'" -ForegroundColor Red
            Write-Host "            Continuing, but doommake steps may fail..." -ForegroundColor Yellow
        }
    }
}

# ============================================================================
# STEP 2: Copy File Templates
# ============================================================================

Write-Host ""
Write-Host "STEP 2: Creating files from templates..." -ForegroundColor Cyan

# Function to copy file templates
function Copy-FileTemplate {
    param(
        [string]$SourceFile,
        [string]$DestPath,
        [string]$Prefix
    )

    $DestFilename = $SourceFile -replace "doommake-tweak-$Prefix", ""
    $SourcePath = Join-Path $PSScriptRoot $SourceFile
    $DestFullPath = Join-Path $DestPath $DestFilename

    if (Test-Path $SourcePath) {
        Copy-Item $SourcePath $DestFullPath -Force
        if (Test-Path $DestFullPath) {
            Write-Host "  [File Created] $DestFullPath" -ForegroundColor Green
        }
    } else {
        Write-Host "  [WARNING] Template not found: $SourceFile" -ForegroundColor Red
    }
}

$copiedCount = 0
foreach ($template in $FileTemplates) {
    Copy-FileTemplate -SourceFile $template.SourceFile -DestPath $template.DestPath -Prefix $template.Prefix
    $copiedCount++
}
if ($copiedCount -eq 0) {
    Write-Host "  [None] No file templates listed - nothing to copy." -ForegroundColor Yellow
}

# ============================================================================
# STEP 3: Replace Entry Targets (full-function replace)
# ============================================================================

Write-Host ""
Write-Host "STEP 3: Replacing entry targets..." -ForegroundColor Cyan

$scriptPath = ".\doommake.script"

# Function to fully replace a "check entry <name>(args) { ... }" block,
# no matter how many nested braces/functions are inside it.
function Replace-CheckEntry {
    param(
        [string]$ConfFile,
        [string]$EntryName
    )

    $confPath = Join-Path $PSScriptRoot $ConfFile

    if (!(Test-Path $confPath)) {
        Write-Host "  [WARNING] Config file not found: $ConfFile" -ForegroundColor Red
        return
    }

    $newBlock = (Get-Content $confPath -Raw).TrimEnd()
    $markerLine = ($newBlock -split "`r?`n")[0].Trim()

    $scriptContent = Get-Content $scriptPath -Raw

    if ($scriptContent.Contains($markerLine)) {
        Write-Host "  [Skipped] '$EntryName' already replaced (marker found)" -ForegroundColor Yellow
        return
    }

    $startPattern = "check entry $EntryName\(args\)\s*\{"
    $m = [regex]::Match($scriptContent, $startPattern)

    if (-not $m.Success) {
        Write-Host "  [WARNING] Could not find 'check entry $EntryName(args)' in doommake.script" -ForegroundColor Red
        return
    }

    # Walk forward from the opening brace, tracking depth, to find the
    # matching closing brace - handles any nesting inside the entry.
    $openBraceIndex = $scriptContent.IndexOf('{', $m.Index)
    $depth = 0
    $i = $openBraceIndex
    $endIndex = -1

    while ($i -lt $scriptContent.Length) {
        if ($scriptContent[$i] -eq '{') { $depth++ }
        elseif ($scriptContent[$i] -eq '}') {
            $depth--
            if ($depth -eq 0) {
                $endIndex = $i
                break
            }
        }
        $i++
    }

    if ($endIndex -eq -1) {
        Write-Host "  [WARNING] Could not find matching closing brace for '$EntryName'" -ForegroundColor Red
        return
    }

    $scriptContent = $scriptContent.Substring(0, $m.Index) + $newBlock + $scriptContent.Substring($endIndex + 1)
    [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
    Write-Host "  [Replaced] entry '$EntryName'" -ForegroundColor Green
}

$replacedCount = 0
foreach ($replacement in $EntryReplacements) {
    Replace-CheckEntry -ConfFile $replacement.ConfFile -EntryName $replacement.EntryName
    $replacedCount++
}
if ($replacedCount -eq 0) {
    Write-Host "  [None] No entry targets listed - nothing to replace." -ForegroundColor Yellow
}

# ============================================================================
# STEP 4: Insert Functions & Entry Targets into doommake.script
# ============================================================================
# Custom blocks are inserted immediately before the FIRST "check entry" found
# in the file, rather than appended to the very end. This keeps them below
# every stock function (so our code can call stock functions) and above
# every stock entry (so stock entries like "release" can call our custom
# functions too). Multiple blocks are inserted in order at the same growing
# point, so later files (e.g. _final.conf) still land after earlier ones
# (e.g. _all.conf).

Write-Host ""
Write-Host "STEP 4: Inserting new functions and entry targets..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

$firstEntryMatch = [regex]::Match($scriptContent, 'check\s+entry\s+\w+\(args\)\s*\{')

if (-not $firstEntryMatch.Success) {
    Write-Host "  [ERROR] Could not find any 'check entry' in doommake.script - cannot determine insertion point." -ForegroundColor Red
} else {
    $insertIndex = $firstEntryMatch.Index
    $insertedCount = 0

    foreach ($block in $AppendBlocks) {

        $confPath = Join-Path $PSScriptRoot $block

        if (!(Test-Path $confPath)) {
            Write-Host "  [WARNING] Config file not found: $block" -ForegroundColor Red
            continue
        }

        $newBlock = (Get-Content $confPath -Raw).TrimEnd()
        $markerLine = ($newBlock -split "`r?`n")[0].Trim()

        if ($scriptContent.Contains($markerLine)) {
            Write-Host "  [Skipped] '$block' already inserted (marker found)" -ForegroundColor Yellow
            continue
        }

        $insertText = $newBlock + "`r`n`r`n"
        $scriptContent = $scriptContent.Substring(0, $insertIndex) + $insertText + $scriptContent.Substring($insertIndex)
        $insertIndex += $insertText.Length

        Write-Host "  [Inserted] $block" -ForegroundColor Green
        $insertedCount++
    }

    [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)

    if ($insertedCount -eq 0) {
        Write-Host "  [None] No blocks listed - nothing to insert." -ForegroundColor Yellow
    }
}

# ============================================================================
# DONE
# ============================================================================

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkCyan
Write-Host "== Template copy complete. ===============" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor DarkCyan
Write-Host ""