#Requires -Version 5.1
<#
.SYNOPSIS
    Builds a self-contained texture/flat/palette WAD from a source WAD.

.DESCRIPTION
    Extracts all textures and flats referenced by the input WAD (via wtexlist +
    wtexport), then merges the result with the PLAYPAL and COLORMAP lumps from
    the same source WAD using DoomTools wadmerge.

.PARAMETER InputWad
    Path to the source WAD file.

.PARAMETER Iwad
    Short name of the base IWAD to use for texture extraction.
    Valid values: doom  doom2  tnt  plutonia  heretic  hexen  free1  free2
    Defaults to: doom2

.PARAMETER Log
    If specified, output is written to both the console AND a log file named
    <InputWadBaseName>_log.txt in the same directory as the input WAD.

.EXAMPLE
    .\buildTextureWad.ps1 mymod.wad
    .\buildTextureWad.ps1 mymod.wad -Iwad doom
    .\buildTextureWad.ps1 mymod.wad -Log
    .\buildTextureWad.ps1 mymod.wad -Iwad tnt -Log
#>

param(
    [Parameter(Mandatory, Position = 0)]
    [string]$InputWad,

    [Parameter()]
    [ValidateSet('doom','doom2','tnt','plutonia','heretic','hexen','free1','free2',
                 IgnoreCase = $true)]
    [string]$Iwad = 'doom2',

    [Parameter()]
    [switch]$Log
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── IWAD paths ────────────────────────────────────────────────────────────────
$IwadRoot = 'D:\Projects\DoomProjects\_SourcePorts\_iwads'
$IwadMap  = @{
    doom     = 'doom.wad'
    doom2    = 'doom2.wad'
    tnt      = 'tnt.wad'
    plutonia = 'plutonia.wad'
    heretic  = 'heretic.wad'
    hexen    = 'hexen.wad'
    free1    = 'freedoom1.wad'
    free2    = 'freedoom2.wad'
}

# ── Resolve paths ─────────────────────────────────────────────────────────────
$InputWad  = (Resolve-Path -LiteralPath $InputWad).ProviderPath
$BaseIwad  = Join-Path $IwadRoot $IwadMap[$Iwad.ToLower()]
$BaseName  = [System.IO.Path]::GetFileNameWithoutExtension($InputWad)
$InputDir  = Split-Path $InputWad -Parent
$OutputWad = Join-Path $InputDir "textures_$BaseName.wad"
$LogFile   = Join-Path $InputDir "${BaseName}_log.txt"

# ── Logging helper ────────────────────────────────────────────────────────────
# Writes to console always; also appends to log file if -Log was passed.
function Out {
    param([string]$Message = '')
    Write-Host $Message
    if ($Log) {
        Add-Content -LiteralPath $LogFile -Value $Message -Encoding UTF8
    }
}

# ── Start log file fresh ──────────────────────────────────────────────────────
if ($Log) {
    [System.IO.File]::WriteAllText($LogFile, '', [System.Text.Encoding]::UTF8)
    Write-Host "Logging to: $LogFile"
}

# ── Validate inputs ───────────────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $InputWad)) {
    Out "ERROR: Input WAD not found: $InputWad"; exit 1
}
if (-not (Test-Path -LiteralPath $BaseIwad)) {
    Out "ERROR: Base IWAD not found: $BaseIwad"; exit 1
}

# ── Temp files ────────────────────────────────────────────────────────────────
$Stamp     = [System.IO.Path]::GetRandomFileName().Replace('.','')
$TmpWad    = Join-Path $env:TEMP "texbuild_$Stamp.wad"
$TmpScript = Join-Path $env:TEMP "texbuild_$Stamp.wm"

try {
    Out "Building: $OutputWad"
    Out "  Source : $InputWad"
    Out "  IWAD   : $BaseIwad"
    Out ""

    # ── Step 1: wtexlist | wtexport ───────────────────────────────────────────
    Out "Running wtexlist | wtexport ..."

    $texList = & wtexlist "$InputWad" 2>&1
    $texList | ForEach-Object { Out $_.ToString() }
    if ($LASTEXITCODE -ne 0) { Out "ERROR: wtexlist failed (exit $LASTEXITCODE)"; exit 1 }

    # wtexport reads texture names from stdin, writes to TmpWad
    $texList | & wtexport "$InputWad" --base-wad "$BaseIwad" --output "$TmpWad" --create 2>&1 |
        ForEach-Object { Out $_.ToString() }
    if ($LASTEXITCODE -ne 0) { Out "ERROR: wtexport failed (exit $LASTEXITCODE)"; exit 1 }

    if (-not (Test-Path -LiteralPath $TmpWad)) {
        Out "ERROR: wtexport produced no output file: $TmpWad"; exit 1
    }

    # ── Step 2: wadmerge script ───────────────────────────────────────────────
    # WadMerge treats backslashes as escape sequences in .wm files - use forward slashes.
    $TmpWadFwd    = $TmpWad.Replace('\','/')
    $InputWadFwd  = $InputWad.Replace('\','/')
    $OutputWadFwd = $OutputWad.Replace('\','/')

	$scriptContent = @"
create out
mergewad out "$TmpWadFwd"
mergeentryfile out PLAYPAL "$InputWadFwd"
mergeentryfile out COLORMAP "$InputWadFwd"
finish out "$OutputWadFwd"
end
"@
    [System.IO.File]::WriteAllText($TmpScript, $scriptContent, [System.Text.Encoding]::ASCII)

    Out "Running wadmerge ..."
    & wadmerge "$TmpScript" 2>&1 | ForEach-Object { Out $_.ToString() }
    if ($LASTEXITCODE -ne 0) { Out "ERROR: wadmerge failed (exit $LASTEXITCODE)"; exit 1 }

    if (-not (Test-Path -LiteralPath $OutputWad)) {
        Out "ERROR: wadmerge did not produce output: $OutputWad"; exit 1
    }

    Out ""
    Out "Done: $OutputWad"
}
finally {
    foreach ($f in $TmpWad, $TmpScript) {
        if ($f -and (Test-Path -LiteralPath $f)) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }
}