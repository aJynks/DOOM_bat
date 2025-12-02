[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

# -------------------------------------------------------------------------
# Check if this is a DoomTools project root
# -------------------------------------------------------------------------

$requiredFiles = @(
    "doommake.project.properties",
    "doommake.properties"
)

$missing = @()

foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $file)) {
        $missing += $file
    }
}

if ($missing.Count -gt 0) {

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "   ERROR: This is NOT a valid DoomTools project"   -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host ""

    Write-Host "The following required file(s) are missing:" -ForegroundColor Yellow
    foreach ($m in $missing) {
        Write-Host ("  - " + $m) -ForegroundColor DarkYellow
    }

    Write-Host ""
    Write-Host "You must run 'deco' from the ROOT folder of a DoomTools project." -ForegroundColor Cyan
    Write-Host ""

    exit 1
}

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

function Get-RelativePath {
    param([string]$Path)
    $base = (Get-Location).Path
    $full = Resolve-Path $Path | Convert-Path
    $relative = $full.Replace($base, "").Replace("\", "/")
    if ($relative.StartsWith("/")) { return "." + $relative }
    return "./" + $relative
}

function Show-FinalCommand {
    param([string]$DhFile, [string]$OutDEH, [string]$OutDH)
    $relDh  = Get-RelativePath $DhFile
    $relDeh = $OutDEH.Replace("\", "/")
    $relSrc = $OutDH.Replace("\", "/")
    Write-Host ('decohack "{0}" -o "{1}" -s "{2}"' -f $relDh, $relDeh, $relSrc) -ForegroundColor Yellow
}

function Ensure-DirectoryForFile {
    param([string]$FilePath)
    $dir = Split-Path -Path $FilePath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Show-DecoHelp {

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "                   DECO WRAPPER HELP              " -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""

    Write-Host " USAGE:" -ForegroundColor Yellow
    Write-Host "   deco [command] [options]" -ForegroundColor Gray
    Write-Host ""

    Write-Host " COMMANDS:" -ForegroundColor Yellow

    Write-Host "   help" -ForegroundColor Green
    Write-Host "       Shows this help information." -ForegroundColor Gray
    Write-Host ""

    Write-Host "   build" -ForegroundColor Green
    Write-Host "       Builds the default script:" -ForegroundColor Gray
    Write-Host "         src/decohack/main.dh" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   build <file.dh>" -ForegroundColor Green
    Write-Host "       Builds a specific .dh file found anywhere under src/decohack/." -ForegroundColor Gray
    Write-Host "       Errors if more than one file matches the name." -ForegroundColor Gray
    Write-Host ""

    Write-Host "   <file.dh>" -ForegroundColor Green
    Write-Host "       Shortcut for 'deco build <file.dh>'." -ForegroundColor Gray
    Write-Host ""

    Write-Host "   dump-constants" -ForegroundColor Green
    Write-Host "       Runs 'decohack --dump-constants'." -ForegroundColor Gray
    Write-Host ""
    Write-Host "   dump-constants <pattern>" -ForegroundColor Green
    Write-Host "       Filters using findstr (comma-separated terms allowed)." -ForegroundColor Gray
    Write-Host "       Example: deco dump-constants ammo,clip,shell" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   dump-constants <pattern> save <name>" -ForegroundColor Green
    Write-Host "       Saves filtered constants to:" -ForegroundColor Gray
    Write-Host "         src/decohack/_dump/<name>.dump" -ForegroundColor Gray
    Write-Host ""

    Write-Host "   dump-pointers" -ForegroundColor Green
    Write-Host "       Prints all pointer blocks (A_* functions) with descriptions." -ForegroundColor Gray
    Write-Host ""
    Write-Host "   dump-pointers <pattern>" -ForegroundColor Green
    Write-Host "       Finds and prints matching pointer blocks (block-based search)." -ForegroundColor Gray
    Write-Host "       Pattern may be comma-separated (for example: ammo,fire,noammo)." -ForegroundColor Gray
    Write-Host ""
    Write-Host "   dump-pointers <pattern> save <name>" -ForegroundColor Green
    Write-Host "       Saves matching pointer blocks to:" -ForegroundColor Gray
    Write-Host "         src/decohack/_dump/<name>.dump" -ForegroundColor Gray
    Write-Host ""

    Write-Host "   dump-pointers-html" -ForegroundColor Green
    Write-Host "       Saves 'decohack --dump-pointers-html' output to:" -ForegroundColor Gray
    Write-Host "         src/decohack/_dump/pointerDump.html" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   dump-pointers-html <name>" -ForegroundColor Green
    Write-Host "       Saves HTML dump to:" -ForegroundColor Gray
    Write-Host "         src/decohack/_dump/<name>.html" -ForegroundColor Gray
    Write-Host ""

    Write-Host " NOTES:" -ForegroundColor Yellow
    Write-Host "   - Running 'deco' with no arguments builds main.dh." -ForegroundColor Gray
    Write-Host "   - Running 'deco <file.dh>' builds that .dh file." -ForegroundColor Gray
    Write-Host "   - Running 'deco --help' calls the real decohack help." -ForegroundColor Gray
    Write-Host "   - All dump files are stored under:" -ForegroundColor Gray
    Write-Host "         src/decohack/_dump/" -ForegroundColor Gray
    Write-Host ""

    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
}

# -------------------------------------------------------------------------
# build logic
# -------------------------------------------------------------------------

function Invoke-DecoBuild {
    param([string]$DhTarget)

    $projectRoot = Get-Location
    $srcDecoDir  = Join-Path $projectRoot "src\decohack"

    if (-not (Test-Path $srcDecoDir)) {
        Write-Host ""
        Write-Host "==================================================" -ForegroundColor Red
        Write-Host "  ERROR: Could not find src\decohack directory"    -ForegroundColor Red
        Write-Host "==================================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "Expected directory: src\decohack under the project root." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    $dehOut = "./build/_deh/dehacked.deh"
    $srcOut = "./build/_deh/decohack.dh"

    Ensure-DirectoryForFile $dehOut
    Ensure-DirectoryForFile $srcOut

    # Default main.dh
    if (-not $DhTarget) {
        $mainPath = Join-Path $srcDecoDir "main.dh"
        if (-not (Test-Path $mainPath)) {
            Write-Host ""
            Write-Host "==================================================" -ForegroundColor Red
            Write-Host "  ERROR: main.dh is missing"                       -ForegroundColor Red
            Write-Host "==================================================" -ForegroundColor Red
            Write-Host ""
            exit 1
        }

        Show-FinalCommand $mainPath $dehOut $srcOut
        & decohack $mainPath "-o" $dehOut "-s" $srcOut
        exit $LASTEXITCODE
    }

    # Specific target
    $dhName = $DhTarget
    if (-not $dhName.ToLower().EndsWith(".dh")) { $dhName += ".dh" }

    $matches = Get-ChildItem $srcDecoDir -Recurse -File | Where-Object { $_.Name -ieq $dhName }

    if ($matches.Count -eq 0) {
        Write-Host ""
        Write-Host "==================================================" -ForegroundColor Red
        Write-Host "  ERROR: Could not find '$dhName'"                  -ForegroundColor Red
        Write-Host "==================================================" -ForegroundColor Red
        Write-Host ""
        exit 1
    }

    if ($matches.Count -gt 1) {
        Write-Host ""
        Write-Host "==================================================" -ForegroundColor Red
        Write-Host "  ERROR: Multiple files named '$dhName'"           -ForegroundColor Red
        Write-Host "==================================================" -ForegroundColor Red
        foreach ($m in $matches) { Write-Host "  - $($m.FullName)" -ForegroundColor Yellow }
        Write-Host ""
        exit 1
    }

    $target = $matches[0].FullName
    Show-FinalCommand $target $dehOut $srcOut
    & decohack $target "-o" $dehOut "-s" $srcOut
    exit $LASTEXITCODE
}

# -------------------------------------------------------------------------
# dump-constants logic (comma-based patterns with findstr)
# -------------------------------------------------------------------------

function Invoke-DumpConstants {
    param([string[]]$TailArgs)

    $pattern  = $null
    $saveBase = $null

    if ($TailArgs.Count -gt 0) {

        # Starts with "save" -> no pattern, just save
        if ($TailArgs[0].ToLower() -eq 'save') {
            if ($TailArgs.Count -lt 2) {
                Write-Host "ERROR: Missing filename after save" -ForegroundColor Red
                exit 1
            }
            $saveBase = $TailArgs[1]
            if ($TailArgs.Count -gt 2) {
                Write-Host "ERROR: Too many arguments to dump-constants" -ForegroundColor Red
                exit 1
            }
        }
        else {
            # First token is pattern (possibly comma-separated)
            $pattern = $TailArgs[0]

            # Convert commas to spaces for findstr OR semantics
            if ($pattern.Contains(",")) {
                $pattern = $pattern.Replace(",", " ")
            }

            # Optional save
            if ($TailArgs.Count -ge 2 -and $TailArgs[1].ToLower() -eq 'save') {
                if ($TailArgs.Count -lt 3) {
                    Write-Host "ERROR: Missing filename after save" -ForegroundColor Red
                    exit 1
                }
                $saveBase = $TailArgs[2]
                if ($TailArgs.Count -gt 3) {
                    Write-Host "ERROR: Too many arguments to dump-constants" -ForegroundColor Red
                    exit 1
                }
            }
            elseif ($TailArgs.Count -gt 1) {
                Write-Host "ERROR: Too many arguments to dump-constants" -ForegroundColor Red
                exit 1
            }
        }
    }

    # No save -> stdout only
    if (-not $saveBase) {
        if (-not $pattern) {
            & decohack --dump-constants
            exit $LASTEXITCODE
        }
        else {
            & decohack --dump-constants | findstr /i "$pattern"
            exit $LASTEXITCODE
        }
    }

    # Save -> write to ./src/decohack/_dump/<name>.dump
    $dumpDir  = "./src/decohack/_dump"
    $dumpFile = "$dumpDir/$saveBase.dump"

    if (-not (Test-Path $dumpDir)) {
        New-Item -ItemType Directory -Path $dumpDir -Force | Out-Null
    }

    if (-not $pattern) {
        & decohack --dump-constants | Out-File $dumpFile -Encoding UTF8
        Write-Host ("Saved constants dump to " + (Get-RelativePath $dumpFile)) -ForegroundColor Cyan
        exit 0
    }
    else {
        & decohack --dump-constants | findstr /i "$pattern" | Out-File $dumpFile -Encoding UTF8
        Write-Host ("Saved filtered constants dump to " + (Get-RelativePath $dumpFile)) -ForegroundColor Cyan
        exit 0
    }
}

# -------------------------------------------------------------------------
# dump-pointers logic (block-based, with save)
# -------------------------------------------------------------------------

function Invoke-DumpPointers {
    param([string[]]$TailArgs)

    $pattern  = $null    # raw user input, e.g. "noammo" or "refire,noammo"
    $saveBase = $null    # base filename for save (without .dump)

    if ($TailArgs.Count -gt 0) {
        if ($TailArgs[0].ToLower() -eq 'save') {
            # deco dump-pointers save name
            if ($TailArgs.Count -lt 2) {
                Write-Host "ERROR: Missing filename after save" -ForegroundColor Red
                exit 1
            }
            $saveBase = $TailArgs[1]
            if ($TailArgs.Count -gt 2) {
                Write-Host "ERROR: Too many arguments to dump-pointers" -ForegroundColor Red
                exit 1
            }
        }
        else {
            # deco dump-pointers pattern [save name]
            $pattern = $TailArgs[0]

            if ($TailArgs.Count -ge 2 -and $TailArgs[1].ToLower() -eq 'save') {
                if ($TailArgs.Count -lt 3) {
                    Write-Host "ERROR: Missing filename after save" -ForegroundColor Red
                    exit 1
                }
                $saveBase = $TailArgs[2]
                if ($TailArgs.Count -gt 3) {
                    Write-Host "ERROR: Too many arguments to dump-pointers" -ForegroundColor Red
                    exit 1
                }
            }
            elseif ($TailArgs.Count -gt 1) {
                Write-Host "ERROR: Too many arguments to dump-pointers" -ForegroundColor Red
                exit 1
            }
        }
    }

    # Get full dump from decohack
    $lines = & decohack --dump-pointers

    if (-not $lines -or $lines.Count -eq 0) {
        Write-Host "No pointer data returned from decohack." -ForegroundColor Red
        exit 1
    }

    # Split into blocks starting at lines like "A_Whatever(...)"
    $blocks  = @()
    $current = @()

    foreach ($line in $lines) {
        if ($line -match '^\s*A_[A-Za-z0-9_]*\(') {
            if ($current.Count -gt 0) {
                $blocks += ,@($current)
                $current = @()
            }
        }
        $current += $line
    }
    if ($current.Count -gt 0) {
        $blocks += ,@($current)
    }

    if ($blocks.Count -eq 0) {
        Write-Host "No pointer blocks detected in output." -ForegroundColor Red
        exit 1
    }

    # Prepare search terms (comma-separated, optional)
    $terms = @()
    if ($pattern) {
        $terms = $pattern.Split(",") | Where-Object { $_.Trim() -ne "" }
    }

    $matchedBlockTexts = @()
    $matchesFound      = $false

    foreach ($block in $blocks) {
        $blockText = $block -join "`r`n"

        $blockMatches = $false

        if ($terms.Count -eq 0) {
            # No pattern -> everything matches
            $blockMatches = $true
        }
        else {
            foreach ($t in $terms) {
                $tTrim = $t.Trim()
                if ($tTrim -ne "" -and $blockText -imatch [regex]::Escape($tTrim)) {
                    $blockMatches = $true
                    break
                }
            }
        }

        if ($blockMatches) {
            $matchesFound = $true
            $matchedBlockTexts += $blockText

            # Always print to console
            Write-Host $blockText
            Write-Host ""
        }
    }

    if (-not $matchesFound) {
        if ($pattern) {
            Write-Host ("No pointer blocks matched pattern '{0}'." -f $pattern) -ForegroundColor Yellow
        }
        else {
            Write-Host "No pointer blocks found." -ForegroundColor Yellow
        }
    }

    # Save matched blocks (if requested)
    if ($saveBase) {
        $dumpDir  = "./src/decohack/_dump"
        $dumpFile = "$dumpDir/$saveBase.dump"

        if (-not (Test-Path $dumpDir)) {
            New-Item -ItemType Directory -Path $dumpDir -Force | Out-Null
        }

        if ($matchedBlockTexts.Count -eq 0) {
            "" | Out-File $dumpFile -Encoding UTF8
            Write-Host ("Saved empty pointers dump to " + (Get-RelativePath $dumpFile)) -ForegroundColor Cyan
        }
        else {
            ($matchedBlockTexts -join "`r`n`r`n") | Out-File $dumpFile -Encoding UTF8
            Write-Host ("Saved pointers dump to " + (Get-RelativePath $dumpFile)) -ForegroundColor Cyan
        }
    }

    exit 0
}

# -------------------------------------------------------------------------
# dump-pointers-html logic
# -------------------------------------------------------------------------

function Invoke-DumpPointersHtml {
    param([string[]]$TailArgs)

    $nameBase = $null

    if ($TailArgs.Count -gt 1) {
        Write-Host "ERROR: Too many arguments to dump-pointers-html" -ForegroundColor Red
        Write-Host "Usage: deco dump-pointers-html [name]" -ForegroundColor Yellow
        exit 1
    }

    if ($TailArgs.Count -eq 0) {
        $nameBase = "pointerDump"
    }
    else {
        $nameBase = $TailArgs[0]
    }

    # Save HTML output alongside other dumps
    $dumpDir  = "./src/decohack/_dump"
    $dumpFile = "$dumpDir/$nameBase.html"

    if (-not (Test-Path $dumpDir)) {
        New-Item -ItemType Directory -Path $dumpDir -Force | Out-Null
    }

    & decohack --dump-pointers-html | Out-File $dumpFile -Encoding UTF8
    Write-Host ("Saved pointers HTML dump to " + (Get-RelativePath $dumpFile)) -ForegroundColor Cyan
    exit 0
}

# -------------------------------------------------------------------------
# Dispatch
# -------------------------------------------------------------------------

# custom help
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq 'help') {
    Show-DecoHelp
    exit 0
}

# real decohack help
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq '--help') {
    & decohack --help
    exit $LASTEXITCODE
}

# dump-constants
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq 'dump-constants') {
    $tail = if ($Args.Count -gt 1) { $Args[1..($Args.Count-1)] } else { @() }
    Invoke-DumpConstants $tail
    exit $LASTEXITCODE
}

# dump-pointers
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq 'dump-pointers') {
    $tail = if ($Args.Count -gt 1) { $Args[1..($Args.Count-1)] } else { @() }
    Invoke-DumpPointers $tail
    exit $LASTEXITCODE
}

# dump-pointers-html
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq 'dump-pointers-html') {
    $tail = if ($Args.Count -gt 1) { $Args[1..($Args.Count-1)] } else { @() }
    Invoke-DumpPointersHtml $tail
    exit $LASTEXITCODE
}

# build
if ($Args.Count -gt 0 -and $Args[0].ToLower() -eq 'build') {
    Invoke-DecoBuild $(if ($Args.Count -ge 2) { $Args[1] } else { $null })
    exit $LASTEXITCODE
}

# no args == build main
if ($Args.Count -eq 0) {
    Invoke-DecoBuild $null
    exit $LASTEXITCODE
}

# single .dh file
if ($Args.Count -eq 1 -and $Args[0].ToLower().EndsWith(".dh")) {
    Invoke-DecoBuild $Args[0]
    exit $LASTEXITCODE
}

# passthrough
& decohack @Args
exit $LASTEXITCODE
