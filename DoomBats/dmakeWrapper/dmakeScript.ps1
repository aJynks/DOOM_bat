# ==============================================================================
# dmake.ps1
# ------------------------------------------------------------------------------
# Wrapper for doommake with optional post-run of doom.bat
#
# Called by dmake.bat (thin shim), or runnable directly from PowerShell.
#
# Behaviour:
#   - If ANY argument is "update":
#       Run doomtools --update && --update-cleanup && --update-shell && --update-docs
#       Ignore all other arguments
#   - If ANY argument is "create":    Enter create mode (standalone)
#   - If ANY argument is "explode":   Enter explode mode (standalone)
#   - If ANY argument is "watch":     Enter watch mode (standalone)
#   - If ANY argument is "texturex":  Enter texturex mode (standalone)
#   - If ANY argument is "editpatch": Enter editpatch mode (standalone)
#   - If ANY argument is "--targets": Show the targets help (standalone)
#   - Arguments before "--" are passed to doommake
#   - If "--" is present, doom.bat is run after doommake
#   - Arguments after "--" are passed to doom.bat
#   - If doommake returns non-zero, doom.bat will NOT run
#
# Notes vs the old dmake.bat:
#   - Paths/filenames containing spaces and parentheses ( ) now work correctly.
#     Files on disk are never renamed; only the DERIVED project name in explode
#     mode is sanitised (spaces -> underscores).
#   - Directory paths work with or without a trailing \ or /.
#   - When "create -d" changes directory, the change is propagated back to the
#     calling cmd shell via the DMAKE_CD_FILE env var (set by dmake.bat). When
#     run directly from PowerShell, Set-Location persists naturally.
# ==============================================================================

# ==============================================================================
# Editable IWAD paths
# ==============================================================================
$IWADS = @{
    doom     = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad'
    doom2    = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad'
    tnt      = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad'
    plutonia = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad'
    heretic  = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad'
    hexen    = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad'
    free1    = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad'
    free2    = 'D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad'
}

$IWAD_LIST = 'doom, doom2, tnt, plutonia, heretic, hexen, free1, free2'

# ==============================================================================
# Helpers
# ==============================================================================

# Trim trailing \ or / from a directory path, but never strip a drive root
# ("D:\" stays "D:\"). Makes "d:\tmp\" and "d:\tmp" behave identically.
function Normalize-DirPath([string]$Path) {
    if ([string]::IsNullOrEmpty($Path)) { return $Path }
    $p = $Path.TrimEnd('\', '/')
    if ($p -match '^[A-Za-z]:$') { $p += '\' }   # restore drive root
    return $p
}

# Sanitise a derived project name: spaces become underscores.
# Parentheses are legal in directory names and are left untouched.
function Sanitize-ProjectName([string]$Name) {
    return ($Name -replace ' ', '_')
}

# Locate a script on PATH using where.exe (NOT the PowerShell 'where' alias).
function Find-OnPath([string]$Name) {
    $found = & where.exe $Name 2>$null
    if ($found) { return ($found | Select-Object -First 1) }
    return $null
}

# Propagate a directory change back to the calling cmd shell (via dmake.bat).
# When run directly from PowerShell this is a no-op; Set-Location already
# persists in the session.
function Publish-CdOut([string]$Dir) {
    if ($env:DMAKE_CD_FILE) {
        Set-Content -LiteralPath $env:DMAKE_CD_FILE -Value $Dir -NoNewline -Encoding Default
    }
}

# ==============================================================================
# Mode: update  (standalone; ignores all other args)
# ==============================================================================
function Invoke-UpdateMode {
    & doomtools --update
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & doomtools --update-cleanup
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & doomtools --update-shell
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & doomtools --update-docs
    exit $LASTEXITCODE
}

# ==============================================================================
# Mode: create  (standalone)
#   dmake create ProjectName [-i iwad] [-d folder]
# ==============================================================================
function Invoke-CreateMode([string[]]$Rest) {
    $ProjectName = $null
    $IwadName    = 'doom2'
    $DirName     = $null

    if ($Rest.Count -eq 0 -or [string]::IsNullOrEmpty($Rest[0])) {
        Write-Host 'Error: Project name required'
        Write-Host 'Usage: dmake create ProjectName [-i iwad] [-d folder]'
        exit 2
    }

    $ProjectName = $Rest[0]
    $i = 1
    while ($i -lt $Rest.Count) {
        switch -Regex ($Rest[$i]) {
            '^(?i)-i$' {
                if ($i + 1 -ge $Rest.Count) { Write-Host 'Error: -i requires an IWAD name'; exit 2 }
                $IwadName = $Rest[$i + 1]
                $i += 2
            }
            '^(?i)-d$' {
                if ($i + 1 -ge $Rest.Count) { Write-Host 'Error: -d requires a directory name'; exit 2 }
                $DirName = Normalize-DirPath $Rest[$i + 1]
                $i += 2
            }
            default { $i++ }   # Unknown argument - skip it
        }
    }

    $IwadPath = $IWADS[$IwadName]

    Write-Host 'I am in create mode'
    Write-Host ''
    Write-Host "Project Name : $ProjectName"
    Write-Host "IWAD Path    : $IwadPath"
    Write-Host "Directory    : $DirName"
    Write-Host ''

    if ([string]::IsNullOrEmpty($IwadPath)) {
        Write-Host "Error: IWAD path not found for: $IwadName"
        Write-Host "Available IWADs: $IWAD_LIST"
        exit 2
    }

    if ($DirName) {
        if (-not (Test-Path -LiteralPath $DirName)) {
            New-Item -ItemType Directory -Path $DirName | Out-Null
        }
        Set-Location -LiteralPath $DirName
    }

    # Feed the interactive prompts (name, IWAD, patch type) via stdin
    $ProjectName, $IwadPath, 'dsdhacked' |
        & doommake --project-type wad './' -n assets maps decohack texturesboom
    $createErr = $LASTEXITCODE

    & doommake-tweak -IwadPath $IwadPath

    if ($DirName) {
        # Leave the calling shell inside the new directory (matches old dmake.bat)
        Publish-CdOut (Get-Location).Path
    }

    exit $createErr
}

# ==============================================================================
# Mode: explode  (standalone)
#   dmake explode filename.wad [-i iwad] [-p]
# ==============================================================================
function Invoke-ExplodeMode([string[]]$Rest) {
    $ExplodeWad = $null
    $IwadName   = 'doom2'
    $UseWadPal  = $false

    if ($Rest.Count -eq 0 -or [string]::IsNullOrEmpty($Rest[0])) {
        Write-Host 'Error: WAD filename required'
        Write-Host 'Usage: dmake explode filename.wad [-i iwad]'
        exit 2
    }

    $ExplodeWad = $Rest[0]
    $i = 1
    while ($i -lt $Rest.Count) {
        switch -Regex ($Rest[$i]) {
            '^(?i)-i$' {
                if ($i + 1 -ge $Rest.Count) { Write-Host 'Error: -i requires an IWAD name'; exit 2 }
                $IwadName = $Rest[$i + 1]
                $i += 2
            }
            '^(?i)-p$' {
                $UseWadPal = $true
                $i++
            }
            default { $i++ }   # Unknown argument - skip it
        }
    }

    $IwadPath = $IWADS[$IwadName]

    # Derive project name from the WAD filename.
    # The file on disk is NEVER renamed - spaces and ( ) in the real path are
    # fine now. Only the derived name is sanitised: spaces -> underscores.
    $stem        = [System.IO.Path]::GetFileNameWithoutExtension($ExplodeWad)
    $cleanStem   = Sanitize-ProjectName $stem
    $ProjectName = "_$cleanStem"

    Write-Host 'I am in explode mode'
    Write-Host ''
    Write-Host "WAD File     : $ExplodeWad"
    Write-Host "Project Name : $ProjectName"
    if ($UseWadPal) {
        Write-Host "PLAYPAL      : $ExplodeWad (from input WAD)"
    } else {
        Write-Host "IWAD Path    : $IwadPath"
    }
    Write-Host ''

    if ([string]::IsNullOrEmpty($IwadPath)) {
        Write-Host "Error: IWAD path not found for: $IwadName"
        Write-Host "Available IWADs: $IWAD_LIST"
        exit 2
    }

    $palette = if ($UseWadPal) { $ExplodeWad } else { $IwadPath }

    # Feed the interactive prompts (name, IWAD, patch type) via stdin
    $cleanStem, $IwadPath, 'dsdhacked' |
        & doommake $ProjectName --convert-palette $palette --convert --explode $ExplodeWad

    exit $LASTEXITCODE
}

# ==============================================================================
# Mode: watch  (standalone; ignores all other args)
# ==============================================================================
function Invoke-WatchMode {
    Assert-ProjectRoot 'dmake watch'

    Write-Host "Watching project in: $((Get-Location).Path)"
    Write-Host ''

    $watchScript = Find-OnPath 'dmake_watch.py'
    if (-not $watchScript) {
        Write-Host 'Error: dmake_watch.py not found on PATH.'
        exit 2
    }

    & py $watchScript
    exit $LASTEXITCODE
}

# ==============================================================================
# Mode: texturex  (standalone; wadtex TEXTURE1/TEXTURE2 extraction wrapper)
#   dmake texturex [-x1 | -x2] [-file wad.wad] [-output name.txt]
#
#     -x1 / -x2     Which lump to export (TEXTURE1 / TEXTURE2).
#                   If NEITHER is given, BOTH lumps are extracted.
#     -file <wad>   Source WAD. If omitted, falls back to .\build\textures.wad.
#     -output <f>   Output filename (single-lump only). Defaults to
#                   texture1.txt / texture2.txt. Ignored when extracting both.
#
#   Output location:
#     -file given    -> current directory
#     -file omitted  -> the directory ABOVE the current one
#
#   No DoomTools project-root check is performed.
# ==============================================================================
function Invoke-TexturexMode([string[]]$AllArgs) {
    $extract = $null      # 'TEXTURE1' | 'TEXTURE2' | $null (= both)
    $wadFile = $null      # explicit wad via -file
    $outName = $null      # explicit filename via -output

    $i = 0
    while ($i -lt $AllArgs.Count) {
        switch -Regex ($AllArgs[$i]) {
            '^(?i)-x1$' { $extract = 'TEXTURE1'; $i++ }
            '^(?i)-x2$' { $extract = 'TEXTURE2'; $i++ }
            '^(?i)-file$' {
                if ($i + 1 -ge $AllArgs.Count) { Write-Host 'Error: -file requires a WAD path'; exit 2 }
                $wadFile = $AllArgs[$i + 1]; $i += 2
            }
            '^(?i)-output$' {
                if ($i + 1 -ge $AllArgs.Count) { Write-Host 'Error: -output requires a filename'; exit 2 }
                $outName = $AllArgs[$i + 1]; $i += 2
            }
            default { $i++ }   # includes the 'texturex' keyword itself
        }
    }

    # Resolve source WAD and output directory
    if ($wadFile) {
        if (-not (Test-Path -LiteralPath $wadFile)) {
            Write-Host "Error: WAD not found: $wadFile"
            exit 2
        }
        $outDir = (Get-Location).Path                              # explicit wad -> current dir
    } else {
        $wadFile = Join-Path (Get-Location).Path 'build\textures.wad'
        if (-not (Test-Path -LiteralPath $wadFile)) {
            Write-Host 'Error: .\build\textures.wad not found.'
            Write-Host 'Run this from a DoomTools project root, or specify a WAD with -file.'
            exit 2
        }
        $outDir = Split-Path -Parent (Get-Location).Path           # fallback -> one dir up
        if ([string]::IsNullOrEmpty($outDir)) { $outDir = (Get-Location).Path }
    }

    # Export one lump to a filename within $outDir (absolute names honoured as-is)
    function Export-Lump([string]$Lump, [string]$FileName) {
        if ([System.IO.Path]::IsPathRooted($FileName)) { $p = $FileName } else { $p = Join-Path $outDir $FileName }
        Write-Host "  $Lump -> $p"
        & wadtex $wadFile --export $p --entry-name $Lump
        # No 'return' - caller reads $LASTEXITCODE. Returning it would also
        # capture wadtex's stdout into the function's output stream.
    }

    Write-Host 'dmake texturex - wadtex extraction'
    Write-Host "  Source WAD : $wadFile"
    Write-Host ''

    if (-not $extract) {
        # No lump chosen -> extract BOTH (wadtex writes a template if a lump is absent)
        if ($outName) { Write-Host 'Note: -output ignored when extracting both lumps.'; Write-Host '' }
        Export-Lump 'TEXTURE1' 'texture1.txt'
        Export-Lump 'TEXTURE2' 'texture2.txt'
        exit $LASTEXITCODE
    }

    # Single lump
    if (-not $outName) {
        $outName = if ($extract -eq 'TEXTURE1') { 'texture1.txt' } else { 'texture2.txt' }
    }
    Export-Lump $extract $outName
    exit $LASTEXITCODE
}

# ==============================================================================
# Mode: editpatch  (standalone)
# ==============================================================================
function Invoke-EditpatchMode([string[]]$AllArgs) {
    $useTxt = $false
    foreach ($a in $AllArgs) {
        if ($a -ieq '-txt') { $useTxt = $true }
    }
    if ($useTxt) {
        & wadtex --gui
    } else {
        & wadtex --gui-editor
    }
    exit $LASTEXITCODE
}

# ==============================================================================
# Shared: verify we are in a DoomTools project root
# ==============================================================================
function Assert-ProjectRoot([string]$CmdName) {
    foreach ($f in 'doommake.script', 'doommake.project.properties', 'doommake.properties') {
        if (-not (Test-Path -LiteralPath $f)) {
            Write-Host "Error: $f not found in current directory."
            Write-Host "$CmdName must be run from the root of a DoomTools project."
            exit 2
        }
    }
}

# ==============================================================================
# Main mode: split args at "--", run doommake, optionally run doom.bat
# ==============================================================================
function Invoke-MainMode([string[]]$ArgList) {
    $dmArgs       = @()
    $doomArgs     = @()
    $seenDashDash = $false

    foreach ($a in $ArgList) {
        if (-not $seenDashDash -and $a -eq '--') {
            $seenDashDash = $true
        } elseif ($seenDashDash) {
            $doomArgs += $a
        } else {
            $dmArgs += $a
        }
    }

    # ---- Run doommake ----------------------------------------------------------
    & doommake @dmArgs
    $dmErr = $LASTEXITCODE

    if ($dmErr -ne 0) { exit $dmErr }

    # ---- Run doom.bat if requested ----------------------------------------------
    if ($seenDashDash) {
        & doom.bat @doomArgs
        exit $LASTEXITCODE
    }

    exit 0
}

# ==============================================================================
# Dispatcher
# ==============================================================================
function Invoke-Dmake([string[]]$ArgList) {
    if ($null -eq $ArgList) { $ArgList = @() }

    # ---- Scan ALL arguments for special commands ---------------------------------
    foreach ($a in $ArgList) {
        switch -Regex ($a) {
            '^(?i)update$'    { Invoke-UpdateMode }
            '^(?i)create$'    { Invoke-CreateMode    (Get-RestAfterKeyword $ArgList 'create') }
            '^(?i)explode$'   { Invoke-ExplodeMode   (Get-RestAfterKeyword $ArgList 'explode') }
            '^(?i)watch$'     { Invoke-WatchMode }
            '^(?i)texturex$'  { Invoke-TexturexMode  $ArgList }
            '^(?i)editpatch$' { Invoke-EditpatchMode $ArgList }
            '^(?i)--targets$' { Show-TargetsHelp; exit 0 }
        }
    }

    # ---- Help triggers ------------------------------------------------------------
    if ($ArgList.Count -gt 0) {
        switch -Regex ($ArgList[0]) {
            '^(?i)(--help|-h|/h|/\?|help)$' { Show-DmakeHelp; exit 0 }
        }
    }

    Invoke-MainMode $ArgList
}

# Return everything after the first occurrence of a keyword (case-insensitive)
function Get-RestAfterKeyword([string[]]$ArgList, [string]$Keyword) {
    for ($i = 0; $i -lt $ArgList.Count; $i++) {
        if ($ArgList[$i] -ieq $Keyword) {
            if ($i + 1 -lt $ArgList.Count) {
                return [string[]]($ArgList[($i + 1)..($ArgList.Count - 1)])
            }
            return [string[]]@()
        }
    }
    return [string[]]@()
}


# ##############################################################################
# ##############################################################################
# ##                                                                          ##
# ##   HELP TEXT - EDIT BELOW                                                 ##
# ##                                                                          ##
# ##   Both help screens live here so they are easy to find and update.      ##
# ##   They are plain Write-Host blocks - change wording/colours freely.     ##
# ##                                                                          ##
# ##############################################################################
# ##############################################################################

# ==============================================================================
# HELP: dmake --help / -h / /h / /? / help
# ==============================================================================
function Show-DmakeHelp {
    Write-Host ""
    Write-Host "==============================================================================" -ForegroundColor DarkCyan
    Write-Host "  DMAKE  -  doommake wrapper with optional doom.bat launch" -ForegroundColor White
    Write-Host "==============================================================================" -ForegroundColor DarkCyan
    Write-Host ""
    Write-Host "  dmake forwards arguments to doommake. If " -NoNewline; Write-Host """--""" -ForegroundColor Yellow -NoNewline
    Write-Host " is present, doom.bat is run"
    Write-Host "  after doommake finishes, receiving any arguments after the " -NoNewline; Write-Host """--""" -ForegroundColor Yellow -NoNewline; Write-Host "."
    Write-Host ""

    Write-Host "USAGE" -ForegroundColor White
    Write-Host "  dmake [doommake_args...]              - Run doommake" -ForegroundColor Gray
    Write-Host "  dmake [doommake_args...] -- [args...] - Run doommake then doom.bat" -ForegroundColor Gray
    Write-Host "  dmake <command> [options]             - Run a special dmake command" -ForegroundColor Gray
    Write-Host ""

    Write-Host "SPECIAL COMMANDS" -ForegroundColor White
    Write-Host "  create    " -ForegroundColor Cyan -NoNewline; Write-Host "ProjectName [-i iwad] [-d folder]  - Create a new tweaked DoomMake project"
    Write-Host "  explode   " -ForegroundColor Cyan -NoNewline; Write-Host "filename.wad [-i iwad] [-p]        - Explode a WAD into a DoomMake project"
    Write-Host "  watch     " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Watch project, rebuild on file changes"
    Write-Host "  texturex  " -ForegroundColor Cyan -NoNewline; Write-Host "[-x1|-x2] [-file wad] [-output txt] - Extract TEXTURE1/TEXTURE2 (both if neither)"
    Write-Host "  editpatch " -ForegroundColor Cyan -NoNewline; Write-Host "[-txt]                             - Open DECOHack patch editor GUI"
    Write-Host "  update    " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Update DoomTools to the latest version"
    Write-Host "  --targets " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Show all available doommake targets"
    Write-Host "  --help    " -ForegroundColor Cyan -NoNewline; Write-Host "                                   - Show this help"
    Write-Host ""

    Write-Host "CREATE OPTIONS" -ForegroundColor White
    Write-Host "  -i iwad    " -ForegroundColor Yellow -NoNewline; Write-Host "IWAD to use (default: doom2)"
    Write-Host "             " -NoNewline; Write-Host "Options: " -ForegroundColor Gray -NoNewline; Write-Host "doom, doom2, tnt, plutonia, heretic, hexen, free1, free2" -ForegroundColor DarkGray
    Write-Host "  -d folder  " -ForegroundColor Yellow -NoNewline; Write-Host "Directory to create the project in (optional)"
    Write-Host ""

    Write-Host "EXPLODE OPTIONS" -ForegroundColor White
    Write-Host "  -i iwad    " -ForegroundColor Yellow -NoNewline; Write-Host "IWAD to use (default: doom2)"
    Write-Host "             " -NoNewline; Write-Host "Options: " -ForegroundColor Gray -NoNewline; Write-Host "doom, doom2, tnt, plutonia, heretic, hexen, free1, free2" -ForegroundColor DarkGray
    Write-Host "  -p         " -ForegroundColor Yellow -NoNewline; Write-Host "Use the input WAD's own PLAYPAL instead of the IWAD"
    Write-Host "             " -NoNewline; Write-Host "(use for WADs with custom palettes)" -ForegroundColor DarkGray
    Write-Host ""

    Write-Host "TEXTUREX OPTIONS" -ForegroundColor White
    Write-Host "  -x1        " -ForegroundColor Yellow -NoNewline; Write-Host "Extract the TEXTURE1 lump"
    Write-Host "  -x2        " -ForegroundColor Yellow -NoNewline; Write-Host "Extract the TEXTURE2 lump"
    Write-Host "             " -NoNewline; Write-Host "(omit both -x1 and -x2 to extract BOTH lumps)" -ForegroundColor DarkGray
    Write-Host "  -file wad  " -ForegroundColor Yellow -NoNewline; Write-Host "Source WAD (default: .\build\textures.wad)"
    Write-Host "  -output f  " -ForegroundColor Yellow -NoNewline; Write-Host "Output filename, single lump only (default: texture1.txt / texture2.txt)"
    Write-Host "             " -NoNewline; Write-Host "With -file: saved in current dir. Without: saved one dir up." -ForegroundColor DarkGray
    Write-Host ""

    Write-Host "EDITPATCH OPTIONS" -ForegroundColor White
    Write-Host "  -txt       " -ForegroundColor Yellow -NoNewline; Write-Host "Open the text file viewer instead of the patch editor"
    Write-Host ""

    Write-Host "EXAMPLES" -ForegroundColor White
    Write-Host "  dmake create MyWAD                   " -ForegroundColor Gray -NoNewline; Write-Host "- New doom2 project in current dir" -ForegroundColor DarkGray
    Write-Host "  dmake create MyWAD -i doom -d MyDir  " -ForegroundColor Gray -NoNewline; Write-Host "- New doom project in MyDir folder" -ForegroundColor DarkGray
    Write-Host "  dmake explode summoner.wad            " -ForegroundColor Gray -NoNewline; Write-Host "- Explode WAD using doom2 palette" -ForegroundColor DarkGray
    Write-Host "  dmake explode summoner.wad -p         " -ForegroundColor Gray -NoNewline; Write-Host "- Explode WAD using its own palette" -ForegroundColor DarkGray
    Write-Host "  dmake explode summoner.wad -i tnt -p  " -ForegroundColor Gray -NoNewline; Write-Host "- Explode with TNT IWAD, own palette" -ForegroundColor DarkGray
    Write-Host "  dmake texturex                       " -ForegroundColor Gray -NoNewline; Write-Host "- Extract BOTH lumps from .\build\textures.wad" -ForegroundColor DarkGray
    Write-Host "  dmake texturex -x1                    " -ForegroundColor Gray -NoNewline; Write-Host "- Extract only TEXTURE1 from .\build\textures.wad" -ForegroundColor DarkGray
    Write-Host "  dmake texturex -x2 -file mod.wad      " -ForegroundColor Gray -NoNewline; Write-Host "- Extract TEXTURE2 from mod.wad to current dir" -ForegroundColor DarkGray
    Write-Host "  dmake -- -skill 4 -warp 1             " -ForegroundColor Gray -NoNewline; Write-Host "- Build then launch with doom.bat" -ForegroundColor DarkGray
    Write-Host "  dmake make -- -skill 4 -warp 1        " -ForegroundColor Gray -NoNewline; Write-Host "- Run make then launch with doom.bat" -ForegroundColor DarkGray
    Write-Host "  dmake update                          " -ForegroundColor Gray -NoNewline; Write-Host "- Update DoomTools" -ForegroundColor DarkGray
    Write-Host ""
}

# ==============================================================================
# HELP: dmake --targets
# ==============================================================================
function Show-TargetsHelp {
    Write-Host ""
    Write-Host ""
    Write-Host "DMAKE-ONLY commands:" -ForegroundColor White
    Write-Host "  dmake --targets            - Show this target list" -ForegroundColor Cyan
    Write-Host "  dmake create ProjectName   - Create a new tweaked DoomMake project" -ForegroundColor Cyan
    Write-Host "  dmake explode file.wad     - Explode a WAD into a DoomMake project" -ForegroundColor Cyan
    Write-Host "  dmake watch                - Watch project and rebuild on file changes" -ForegroundColor Cyan
    Write-Host "  dmake texturex             - Extract TEXTURE1/TEXTURE2 from a WAD" -ForegroundColor Cyan
    Write-Host "  dmake editpatch            - Open DECOHack patch editor GUI" -ForegroundColor Cyan
    Write-Host "  dmake update               - Update DoomTools to the latest version" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "DEFAULT targets:" -ForegroundColor White
    Write-Host "  doommake all               - Full build + editor/texture WADs + release WAD (no zip)" -ForegroundColor Gray
    Write-Host "  doommake assets            - Convert and merge assets WAD" -ForegroundColor Gray
    Write-Host "  doommake clean             - Delete the build directory" -ForegroundColor Gray
    Write-Host "  doommake convert           - Convert graphics, sprites, sounds and palettes" -ForegroundColor Gray
    Write-Host "  doommake converttextures   - Convert texture flats and patches to Doom format" -ForegroundColor Gray
    Write-Host "  doommake editor            - Rebuild the editor WAD" -ForegroundColor Gray
    Write-Host "  doommake init              - Initialise the build directory" -ForegroundColor Gray
    Write-Host "  doommake make              - Full build, create release WAD and zip for distribution" -ForegroundColor Gray
    Write-Host "  doommake maps              - Merge the maps WAD" -ForegroundColor Gray
    Write-Host "  doommake maptextures       - Export a WAD of only textures used in maps" -ForegroundColor Gray
    Write-Host "  doommake patch             - Compile the DeHackEd patch and show budget" -ForegroundColor Gray
    Write-Host "  doommake rebuildpalettes   - Rebuild primary palettes and colormaps" -ForegroundColor Gray
    Write-Host "  doommake rebuildtextures   - Rebuild texture listings in src/textures" -ForegroundColor Gray
    Write-Host "  doommake textures          - Convert and merge textures WAD" -ForegroundColor Gray
    Write-Host ""
    Write-Host "TWEAK targets:" -ForegroundColor White
    Write-Host "  doommake deco              - Compile DECOHack and build a DEHACKED-only WAD" -ForegroundColor Yellow
    Write-Host "  doommake editorall         - Editor-asset WAD with ALL textures" -ForegroundColor Yellow
    Write-Host "  doommake editorrestricted  - Editor-asset WAD with RESTRICTED textures" -ForegroundColor Yellow
    Write-Host "  doommake fresh             - Clean build dir, then full build and create release WAD" -ForegroundColor Yellow
    Write-Host "  doommake nopatch           - Full build without DECOHack/DeHackEd" -ForegroundColor Yellow
    Write-Host "  doommake playpal           - Convert palettes and colormaps into a palette-only WAD" -ForegroundColor Yellow
    Write-Host "  doommake release           - Full build, create release WAD (no zip)" -ForegroundColor Yellow
    Write-Host "  doommake releasenopatch    - Full build without DECOHack/DeHackEd , create release WAD and zip for distribution" -ForegroundColor Yellow
    Write-Host "  doommake texall            - Build texture WAD with ALL textures (for UDB)" -ForegroundColor Yellow
    Write-Host "  doommake texrestricted     - Build texture WAD with RESTRICTED textures" -ForegroundColor Yellow
    Write-Host "  doommake udb               - Builds UDB editor resources" -ForegroundColor Yellow
    Write-Host ""
}


# ==============================================================================
# ENTRY POINT
# ==============================================================================
Invoke-Dmake $args