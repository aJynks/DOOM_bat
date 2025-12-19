#-------------------------------------------------------------------------------------------------
# Editable Values

$sourcePort_exes = @{
    "cherry" = "d:\Games\Doom\_SourcePort\Cherry-Doom\cherry-doom.exe"
    "choco"  = "d:\Games\Doom\_SourcePort\Chocolate-Doom\chocolate-doom.exe"
    "crispy" = "d:\Games\Doom\_SourcePort\Crispy-Doom\crispy-doom.exe"
    "dsda"   = "d:\Games\Doom\_SourcePort\dsda-Doom\dsda-doom.exe"
    "edge"   = ""
    "helion" = "d:\Games\Doom\_SourcePort\Helion-Doom\Helion.exe"
    "kex"    = "d:\Games\Doom\_SourcePort\Kex-Doom\DOOM + DOOM II\doom_gog.exe"
    "nugget" = "d:\Games\Doom\_SourcePort\Nugget-Doom\nugget-doom.exe"
    "nyan"   = "d:\Games\Doom\_SourcePort\Nyan-Doom\nyan-doom.exe"
    "retro"  = "d:\Games\Doom\_SourcePort\Retro-Doom\missing.exe"
    "uz"     = "d:\Games\Doom\_SourcePort\uzDoom\uzdoom.exe"
    "woof"   = "d:\Games\Doom\_SourcePort\Woof-Doom\woof.exe"
}

$iwads = @{
    "doom"     = "d:\Games\Doom\_SourcePort\_iwads\doom.wad"
    "doom2"    = "d:\Games\Doom\_SourcePort\_iwads\doom2.wad"
    "tnt"      = "d:\Games\Doom\_SourcePort\_iwads\tnt.wad"
    "plutonia" = "d:\Games\Doom\_SourcePort\_iwads\plutonia.wad"
    "heretic"  = "d:\Games\Doom\_SourcePort\_iwads\heretic.wad"
    "hexen"    = "d:\Games\Doom\_SourcePort\_iwads\hexen.wad"
    "free1"    = "d:\Games\Doom\_SourcePort\_iwads\freedoom1.wad"
    "free2"    = "d:\Games\Doom\_SourcePort\_iwads\freedoom2.wad"
}

# Pak definitions (loaded BEFORE folder-selected WAD, and also BEFORE DoomMake release/dehacked WADs)
$pak = @{
    "pak1" = @(
        "d:\Games\Doom\Wads and Mods\_tweaks\dsda-nyan\Extended Hud - LevelInfo\Vertical\Time on Bar\extHUD_dsda-nyan_VERTICAL_MapName.wad",
        "d:\Games\Doom\Wads and Mods\_tweaks\All Ports\StatusBars\statusBar-GFXonly-Glasses.wad"
    )
    "pak2" = @(
        "d:\Games\Doom\Wads and Mods\_tweaks\dsda-nyan\Extended Hud - LevelInfo\Vertical\Time on Screen\extHUD_dsda-nyan_VERTICAL_Time.MapName.wad",
        "d:\Games\Doom\Wads and Mods\_tweaks\All Ports\StatusBars\statusBar-GFXonly-Helmet.wad"
    )
}

#-------------------------------------------------------------------------------------------------
# Defaults

$defaultPortName = "nyan"
$defaultIwadName = "doom2"
$command_raw = $args

#-------------------------------------------------------------------------------------------------
# Help output

function Write-HeaderLine {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Cyan
}

function Write-SectionHeader {
    param([string]$Title)
    Write-Host ""
    Write-Host ("== " + $Title + " ==") -ForegroundColor Yellow
}

function Show-Help {

    Write-Host ""
    Write-HeaderLine "===============================================================================" 
    Write-HeaderLine " DOOM RUNNER - doom_runDoomWad.ps1"
    Write-HeaderLine "==============================================================================="

    Write-SectionHeader "USAGE"
    Write-Host "  doom [PORT] [IWAD] [PAK...] [OPTIONS...]" -ForegroundColor White
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor Gray
    Write-Host "    doom" -ForegroundColor Gray
    Write-Host "    doom doom2" -ForegroundColor Gray
    Write-Host "    doom dsda doom2" -ForegroundColor Gray
    Write-Host "    doom pak1" -ForegroundColor Gray
    Write-Host "    doom dsda doom2 pak1 -warp 2 -skill 4" -ForegroundColor Gray
    Write-Host "    doom -warp 7                 (uses default skill from doom-loader.conf in project dirs)" -ForegroundColor Gray

    Write-SectionHeader "WHAT THIS SCRIPT DOES"
    Write-Host "  Launcher wrapper that:" -ForegroundColor White
    Write-Host "  - Selects a source port by keyword" -ForegroundColor White
    Write-Host "  - Selects an IWAD by keyword" -ForegroundColor White
    Write-Host "  - Expands pak sets (pak1, pak2, ...)" -ForegroundColor White
    Write-Host "  - In normal folders:" -ForegroundColor White
    Write-Host "      * 1 WAD in folder -> auto loads it" -ForegroundColor White
    Write-Host "      * >1 WADs -> ASCII menu to pick one" -ForegroundColor White
    Write-Host "      * 0 WADs -> launches port + IWAD only" -ForegroundColor White
    Write-Host "  - In DoomMake project folders:" -ForegroundColor White
    Write-Host "      * uses doom-loader.conf to load ./build/<project>.wad" -ForegroundColor White
    Write-Host "      * optionally loads ./build/dehacked.wad (skips if missing)" -ForegroundColor White
    Write-Host "      * reads default warp/skill from doom-loader.conf, CLI overrides them" -ForegroundColor White

    Write-SectionHeader "KEYWORDS"
    Write-Host "  SOURCE PORTS (edit in `$sourcePort_exes`):" -ForegroundColor White
    $ports = ($sourcePort_exes.Keys | Sort-Object) -join ", "
    Write-Host ("    " + $ports) -ForegroundColor Gray

    Write-Host ""
    Write-Host "  IWADS (edit in `$iwads`):" -ForegroundColor White
    $iw = ($iwads.Keys | Sort-Object) -join ", "
    Write-Host ("    " + $iw) -ForegroundColor Gray

    Write-Host ""
    Write-Host "  PAKS (edit in `$pak`):" -ForegroundColor White
    $paks = ($pak.Keys | Sort-Object) -join ", "
    if ([string]::IsNullOrWhiteSpace($paks)) { $paks = "(none defined)" }
    Write-Host ("    " + $paks) -ForegroundColor Gray

    Write-SectionHeader "PAK BEHAVIOUR"
    Write-Host "  Paks expand into a list of WAD paths that are loaded FIRST." -ForegroundColor White
    Write-Host "  Then the folder-selected WAD (normal mode) OR project release WAD (DoomMake mode)." -ForegroundColor White
    Write-Host ""
    Write-Host "  Example:" -ForegroundColor Gray
    Write-Host "    doom pak1" -ForegroundColor Gray
    Write-Host "  Conceptually becomes:" -ForegroundColor Gray
    Write-Host "    -file <pak1 wad #1> <pak1 wad #2> <auto/menu or project wad>" -ForegroundColor Gray

    Write-SectionHeader "DOOMMAKE PROJECT MODE"
    Write-Host "  A DoomMake project is detected when ALL of these exist in the current folder:" -ForegroundColor White
    Write-Host "    doommake.properties" -ForegroundColor Gray
    Write-Host "    doommake.script" -ForegroundColor Gray
    Write-Host "    doommake.project.properties" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  On first run, if doom-loader.conf does not exist, it is created." -ForegroundColor White
    Write-Host "  The release wad name is taken from doommake.project.properties:" -ForegroundColor White
    Write-Host "    doommake.project.name=MyProject" -ForegroundColor Gray
    Write-Host "  Which becomes:" -ForegroundColor White
    Write-Host "    release = ./build/MyProject.wad" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  doom-loader.conf format:" -ForegroundColor White
    Write-Host "    Wads:" -ForegroundColor Gray
    Write-Host "    release = ./build/MyProject.wad" -ForegroundColor Gray
    Write-Host "    dehacked = ./build/dehacked.wad" -ForegroundColor Gray
    Write-Host "    iwad = D:/.../doom2.wad" -ForegroundColor Gray
    Write-Host "" -ForegroundColor Gray
    Write-Host "    Default Warps" -ForegroundColor Gray
    Write-Host "    warp = 1" -ForegroundColor Gray
    Write-Host "    skill = 4" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Notes:" -ForegroundColor White
    Write-Host "  - release is REQUIRED (must exist)" -ForegroundColor White
    Write-Host "  - dehacked is OPTIONAL (if missing, it is ignored)" -ForegroundColor White
    Write-Host "  - warp/skill are DEFAULTS only; CLI overrides them if provided" -ForegroundColor White
    Write-Host "  - If you include the word 'menu' anywhere (project folders only), warp/skill are ignored." -ForegroundColor White

    Write-SectionHeader "OPTIONS PASS-THROUGH"
    Write-Host "  Any arguments not recognised as PORT/IWAD/PAK are passed to the port." -ForegroundColor White
    Write-Host "  Examples:" -ForegroundColor Gray
    Write-Host "    doom dsda doom2 -warp 1 -skill 4 -complevel 9" -ForegroundColor Gray
    Write-Host "    doom woof doom2 -record demo.lmp" -ForegroundColor Gray

    Write-SectionHeader "EDITING THE SCRIPT"
    Write-Host "  You normally only edit these blocks at the top:" -ForegroundColor White
    Write-Host "  1) `$sourcePort_exes : keyword -> exe path" -ForegroundColor White
    Write-Host "  2) `$iwads          : keyword -> iwad path" -ForegroundColor White
    Write-Host "  3) `$pak            : pakN -> array of WAD paths" -ForegroundColor White
    Write-Host ""
    Write-Host "  PowerShell pak syntax rules:" -ForegroundColor White
    Write-Host "    ""pak1"" = @(" -ForegroundColor Gray
    Write-Host "        ""path\one.wad""," -ForegroundColor Gray
    Write-Host "        ""path\two.wad""" -ForegroundColor Gray
    Write-Host "    )" -ForegroundColor Gray
    Write-Host "  Use commas between items, no trailing comma on the last item." -ForegroundColor White

    Write-SectionHeader "HELP"
    Write-Host "  doom --help" -ForegroundColor Gray
    Write-Host "  doom -h" -ForegroundColor Gray
    Write-Host "  doom /?" -ForegroundColor Gray

    Write-Host ""
    Write-HeaderLine "===============================================================================" 
    Write-Host ""
}

#-------------------------------------------------------------------------------------------------
# Help switch (early exit)

$helpTokens = @("--help", "-help", "/help", "help", "-h", "/?")
$wantsHelp = $false
foreach ($a in $command_raw) {
    if ($helpTokens -icontains $a) { $wantsHelp = $true; break }
}
if ($wantsHelp) {
    Show-Help
    exit
}

#-------------------------------------------------------------------------------------------------
# Error helpers

function Show-BoxedError {
    param ([string[]]$Lines)

    $maxLen = ($Lines | ForEach-Object { $_.Length } | Measure-Object -Maximum).Maximum
    $border = "-" * ($maxLen + 6)

    Write-Host $border -ForegroundColor Red
    foreach ($line in $Lines) {
        Write-Host ("|  " + $line.PadRight($maxLen) + "  |") -ForegroundColor Red
    }
    Write-Host $border -ForegroundColor Red
}

function Validate-Path {
    param (
        [string]$Path,
        [string]$Type,
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        Show-BoxedError @(
            "-- Error : $Type <$Name> is blank --"
        )
        exit 1
    }

    if (!(Test-Path -LiteralPath $Path)) {
        Show-BoxedError @(
            "-- Error : $Type <$Name> not found --"
        )
        exit 1
    }
}

function Has-Arg {
    param(
        [string[]]$ArgsList,
        [string]$Flag   # e.g. "-warp" or "-skill"
    )

    $flagLower = $Flag.ToLowerInvariant()

    foreach ($a in $ArgsList) {
        if ($null -eq $a) { continue }
        $s = $a.ToString().ToLowerInvariant()

        # exact match: -warp
        if ($s -eq $flagLower) { return $true }

        # merged forms: -warp7, -warp=7, -warp:7
        if ($s.StartsWith($flagLower) -and $s.Length -gt $flagLower.Length) {
            $next = $s.Substring($flagLower.Length, 1)
            if ($next -match '^[0-9=:\-]$') { return $true }
        }
    }

    return $false
}

function Remove-FlagWithValue {
    param(
        [string[]]$ArgsList,
        [string]$Flag   # e.g. "-warp" or "-skill"
    )

    if ($null -eq $ArgsList) { return @() }

    $flagLower = $Flag.ToLowerInvariant()
    $out = @()

    for ($i = 0; $i -lt $ArgsList.Count; $i++) {
        $a = $ArgsList[$i]
        if ($null -eq $a) { continue }

        $s = $a.ToString()
        $sl = $s.ToLowerInvariant()

        # exact match: -warp (drop it and its next arg)
        if ($sl -eq $flagLower) {
            if ($i -lt ($ArgsList.Count - 1)) { $i++ }
            continue
        }

        # merged forms: -warp7, -warp=7, -warp:7 (drop)
        if ($sl.StartsWith($flagLower) -and $sl.Length -gt $flagLower.Length) {
            $next = $sl.Substring($flagLower.Length, 1)
            if ($next -match '^[0-9=:\-]$') { continue }
        }

        $out += $s
    }

    return ,$out
}

#-------------------------------------------------------------------------------------------------
# ASCII menu selector (Clear-Host redraw, stable)

function Select-FromListAscii {
    param(
        [string]$Title,
        [object[]]$Items,
        [string]$DisplayProperty = "Name"
    )

    if ($Items.Count -lt 1) { return $null }
    if ($Items.Count -eq 1) { return $Items[0] }

    $bg       = "DarkBlue"
    $borderFg = "Cyan"
    $textFg   = "White"
    $hintFg   = "Gray"
    $selFg    = "Black"
    $selBg    = "Gray"

    $rows = foreach ($it in $Items) { [string]$it.$DisplayProperty }
    $maxItemLen = ($rows | ForEach-Object Length | Measure-Object -Maximum).Maximum
    $innerW = [Math]::Max($maxItemLen + 4, $Title.Length + 2)

    $top    = "+" + ("-" * $innerW) + "+"
    $sep    = "|" + ("-" * $innerW) + "|"
    $bottom = "+" + ("-" * $innerW) + "+"

    function Write-FillLine {
        param([string]$content, [string]$fg, [string]$bgColor)
        $pad = $content.PadRight($innerW)
        Write-Host ("|" + $pad + "|") -ForegroundColor $fg -BackgroundColor $bgColor
    }

    $oldCursor = $Host.UI.RawUI.CursorSize
    $Host.UI.RawUI.CursorSize = 0

    try {
        $idx = 0
        while ($true) {
            Clear-Host

            Write-Host $top -ForegroundColor $borderFg -BackgroundColor $bg
            Write-Host ("|" + (" " + $Title).PadRight($innerW) + "|") -ForegroundColor $textFg -BackgroundColor $bg
            Write-Host $sep -ForegroundColor $borderFg -BackgroundColor $bg

            for ($i=0; $i -lt $rows.Count; $i++) {
                $label = "  " + $rows[$i]
                if ($i -eq $idx) {
                    Write-FillLine $label $selFg $selBg
                } else {
                    Write-FillLine $label $textFg $bg
                }
            }

            Write-FillLine "" $textFg $bg
            Write-FillLine "  Up/Down: move   Enter: select   Esc: cancel" $hintFg $bg
            Write-Host $bottom -ForegroundColor $borderFg -BackgroundColor $bg

            $key = [Console]::ReadKey($true)
            switch ($key.Key) {
                "UpArrow"   { if ($idx -gt 0) { $idx-- } }
                "DownArrow" { if ($idx -lt ($rows.Count - 1)) { $idx++ } }
                "Enter"     { return $Items[$idx] }
                "Escape"    { return $null }
            }
        }
    }
    finally {
        $Host.UI.RawUI.CursorSize = $oldCursor
        Clear-Host
    }
}

#-------------------------------------------------------------------------------------------------
# DoomMake helpers

function Get-DoomMakeProjectName {
    param([string]$ProjectPropsPath)

    if (!(Test-Path -LiteralPath $ProjectPropsPath)) {
        Show-BoxedError @(
            "-- Error : DoomMake file <doommake.project.properties> not found --"
        )
        exit 1
    }

    $line = Get-Content -LiteralPath $ProjectPropsPath -ErrorAction Stop |
        Where-Object { $_ -match '^\s*doommake\.project\.name\s*=' } |
        Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($line)) {
        Show-BoxedError @(
            "-- Error : doommake.project.name not found in project properties --"
        )
        exit 1
    }

    $name = ($line -split '=', 2)[1].Trim()

    if ([string]::IsNullOrWhiteSpace($name)) {
        Show-BoxedError @(
            "-- Error : doommake.project.name is blank in project properties --"
        )
        exit 1
    }

    return $name
}

function Get-DoomMakeIwadPath {
    param([string]$DoomMakePropsPath)

    if (!(Test-Path -LiteralPath $DoomMakePropsPath)) { return $null }

    $line = Get-Content -LiteralPath $DoomMakePropsPath -ErrorAction SilentlyContinue |
        Where-Object { $_ -match '^\s*doommake\.iwad\s*=' } |
        Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($line)) { return $null }
    return ($line -split '=', 2)[1].Trim()
}

function Ensure-DoomLoaderConf {
    param(
        [string]$ConfPath,
        [string]$ReleaseWadRelPath
    )

    if (Test-Path -LiteralPath $ConfPath) {
        return
    }

    $doommakePropsPath = Join-Path (Get-Location) "doommake.properties"
    $iwadPath = Get-DoomMakeIwadPath -DoomMakePropsPath $doommakePropsPath

    # NEW: If IWAD filename indicates Doom1-style episodes, default warp should be "1 1"
    $warpDefault = "1"
    if (-not [string]::IsNullOrWhiteSpace($iwadPath)) {
        $iwadFile = [System.IO.Path]::GetFileName($iwadPath).ToLowerInvariant()
        if ($iwadFile -in @("doom.wad", "doom1.wad", "free1.wad", "freedoom1.wad")) {
            $warpDefault = "1 1"
        }
    }

    $content = @(
        "Wads:",
        "release = $ReleaseWadRelPath",
        "dehacked = ./build/dehacked.wad",
        ("iwad = " + $iwadPath),
        "",
        "Default Warps",
        ("warp = " + $warpDefault),
        "skill = 4",
        ""
    )

    Set-Content -LiteralPath $ConfPath -Value $content -Encoding UTF8
}

function Read-DoomLoaderConf {
    param([string]$ConfPath)

    if (!(Test-Path -LiteralPath $ConfPath)) {
        Show-BoxedError @(
            "-- Error : doom-loader.conf not found --"
        )
        exit 1
    }

    $cfg = [ordered]@{
        release  = $null
        dehacked = $null
        iwad     = $null
        warp     = $null
        skill    = $null
    }

    $lines = Get-Content -LiteralPath $ConfPath -ErrorAction Stop

    foreach ($raw in $lines) {
        $line = $raw.Trim()

        if ($line -eq "") { continue }
        if ($line.StartsWith("#")) { continue }

        if ($line -match '^\s*Wads\s*:\s*$') { continue }
        if ($line -match '^\s*Default\s+Warps\s*:?\s*$') { continue }

        if ($line -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.+)\s*$') {
            $k = $matches[1].Trim().ToLowerInvariant()
            $v = $matches[2].Trim()

            switch ($k) {
                "release"  { $cfg.release  = $v }
                "dehacked" { $cfg.dehacked = $v }
                "iwad"     { $cfg.iwad     = $v }
                "warp"     { $cfg.warp     = $v }
                "skill"    { $cfg.skill    = $v }
            }
        }
    }

    return $cfg
}

#-------------------------------------------------------------------------------------------------
# Detect DoomMake project in current directory

$cwd = Get-Location

$doommakeRequiredFiles = @(
    "doommake.properties",
    "doommake.script",
    "doommake.project.properties"
)

$hasDoomMakeProject = $true
foreach ($f in $doommakeRequiredFiles) {
    if (!(Test-Path -LiteralPath (Join-Path $cwd $f))) {
        $hasDoomMakeProject = $false
        break
    }
}

#-------------------------------------------------------------------------------------------------
# DoomMake mode: ensure/read doom-loader.conf and run using its values

if ($hasDoomMakeProject) {

    $projectPropsPath = Join-Path $cwd "doommake.project.properties"
    $projectName = Get-DoomMakeProjectName -ProjectPropsPath $projectPropsPath

    $confPath = Join-Path $cwd "doom-loader.conf"
    $releaseRel = "./build/$projectName.wad"

    Ensure-DoomLoaderConf -ConfPath $confPath -ReleaseWadRelPath $releaseRel
    $loader = Read-DoomLoaderConf -ConfPath $confPath

    # menu mode (project only): if 'menu' is anywhere, ignore ALL -warp/-skill (CLI + conf)
    $menuMode = $false
    foreach ($a in $command_raw) {
        if ($null -ne $a -and $a.ToString().ToLowerInvariant() -eq "menu") { $menuMode = $true; break }
    }

    # Parse args for port/iwad/pak and passthrough flags
    $usedPortName = $defaultPortName
    $usedIwadName = $defaultIwadName

    $usedPort = $sourcePort_exes[$usedPortName]
    $usediWad = $iwads[$usedIwadName]

    $filteredArgs = @()
    $pakWads = @()
    $usedPakNames = @()

    foreach ($arg in $command_raw) {

        # swallow 'menu' token so ports never see it as a filename/arg
        if ($null -ne $arg -and $arg.ToString().ToLowerInvariant() -eq "menu") {
            continue
        }

        if ($iwads.ContainsKey($arg)) {
            $usediWad = $iwads[$arg]
            $usedIwadName = $arg
            continue
        }

        if ($sourcePort_exes.ContainsKey($arg)) {
            $usedPort = $sourcePort_exes[$arg]
            $usedPortName = $arg
            continue
        }

        if ($pak.ContainsKey($arg)) {
            $usedPakNames += $arg
            if ($pak[$arg].Count -eq 0) {
                Show-BoxedError @(
                    "-- Error : Pak <$arg> contains no WADs --"
                )
                exit 1
            }
            foreach ($p in $pak[$arg]) { $pakWads += $p }
            continue
        }

        $filteredArgs += $arg
    }

    # In DoomMake mode, IWAD comes from doom-loader.conf (override whatever the defaults were)
    if (-not [string]::IsNullOrWhiteSpace($loader.iwad)) {
        $usediWad = $loader.iwad
        $usedIwadName = "conf"
    }

    # Validate selected port/iwad + pak wad paths
    Validate-Path $usedPort "Source Port" $usedPortName
    Validate-Path $usediWad "IWAD"        $usedIwadName

    for ($i = 0; $i -lt $pakWads.Count; $i++) {
        $name = ("{0}#{1}" -f ($usedPakNames -join "+"), ($i + 1))
        Validate-Path $pakWads[$i] "Pak WAD" $name
    }

    # Resolve loader paths relative to current directory
    if ([string]::IsNullOrWhiteSpace($loader.release)) {
        Show-BoxedError @(
            "-- Error : doom-loader.conf missing key <release> --"
        )
        exit 1
    }

    $releasePath = Join-Path $cwd $loader.release

    # release is REQUIRED
    Validate-Path $releasePath "Project WAD" "release"

    # dehacked is OPTIONAL: only use it if it exists
    $dehackedPath = $null
    if (-not [string]::IsNullOrWhiteSpace($loader.dehacked)) {
        $candidate = Join-Path $cwd $loader.dehacked
        if (Test-Path -LiteralPath $candidate) {
            $dehackedPath = $candidate
        }
    }

    # Build -file list: pak(s) first, then release, then (optional) dehacked
    $fileList = @()
    if ($pakWads.Count -gt 0) { $fileList += $pakWads }
    $fileList += $releasePath
    if ($dehackedPath -ne $null) { $fileList += $dehackedPath }

    if ($menuMode) {
        # strip any CLI warp/skill if present
        $filteredArgs = Remove-FlagWithValue -ArgsList $filteredArgs -Flag "-warp"
        $filteredArgs = Remove-FlagWithValue -ArgsList $filteredArgs -Flag "-skill"
    }
    else {
        # Add defaults from doom-loader.conf ONLY if user didn't supply them
        if (-not (Has-Arg -ArgsList $filteredArgs -Flag "-warp")) {
            if (-not [string]::IsNullOrWhiteSpace($loader.warp)) {
                # NEW: allow "1 1" to become "-warp 1 1"
                $warpParts = @($loader.warp -split '\s+' | Where-Object { $_ -ne "" })
                if ($warpParts.Count -gt 0) {
                    $filteredArgs += @("-warp") + $warpParts
                }
            }
        }
        if (-not (Has-Arg -ArgsList $filteredArgs -Flag "-skill")) {
            if (-not [string]::IsNullOrWhiteSpace($loader.skill)) {
                $filteredArgs += @("-skill", $loader.skill)
            }
        }
    }

    & $usedPort -iwad $usediWad -file @fileList @filteredArgs
    exit
}

#-------------------------------------------------------------------------------------------------
# Normal mode (NOT a DoomMake project): existing behaviour

$usedPortName = $defaultPortName
$usedIwadName = $defaultIwadName

$usedPort = $sourcePort_exes[$usedPortName]
$usediWad = $iwads[$usedIwadName]

$filteredArgs = @()
$pakWads = @()
$usedPakNames = @()

foreach ($arg in $command_raw) {

    if ($iwads.ContainsKey($arg)) {
        $usediWad = $iwads[$arg]
        $usedIwadName = $arg
        continue
    }

    if ($sourcePort_exes.ContainsKey($arg)) {
        $usedPort = $sourcePort_exes[$arg]
        $usedPortName = $arg
        continue
    }

    if ($pak.ContainsKey($arg)) {
        $usedPakNames += $arg
        if ($pak[$arg].Count -eq 0) {
            Show-BoxedError @(
                "-- Error : Pak <$arg> contains no WADs --"
            )
            exit 1
        }
        foreach ($p in $pak[$arg]) { $pakWads += $p }
        continue
    }

    $filteredArgs += $arg
}

# Validate selections
Validate-Path $usedPort "Source Port" $usedPortName
Validate-Path $usediWad "IWAD"        $usedIwadName

for ($i = 0; $i -lt $pakWads.Count; $i++) {
    $name = ("{0}#{1}" -f ($usedPakNames -join "+"), ($i + 1))
    Validate-Path $pakWads[$i] "Pak WAD" $name
}

# WAD detection / selection (current directory)
$wadPath  = Get-Location
$wadFiles = Get-ChildItem -Path $wadPath -Filter "*.wad" -ErrorAction SilentlyContinue
$wadFullPath = $null

if ($wadFiles.Count -eq 1) {
    $wadFullPath = $wadFiles[0].FullName
}
elseif ($wadFiles.Count -gt 1) {
    $selected = Select-FromListAscii `
        -Title "Select a WAD to run ( $wadPath )" `
        -Items $wadFiles `
        -DisplayProperty "Name"

    if ($null -eq $selected) { exit }
    $wadFullPath = $selected.FullName
}

# Launch
if ($pakWads.Count -gt 0 -or $null -ne $wadFullPath) {
    $fileList = @()
    if ($pakWads.Count -gt 0) { $fileList += $pakWads }
    if ($null -ne $wadFullPath) { $fileList += $wadFullPath }
    & $usedPort -iwad $usediWad -file @fileList @filteredArgs
}
else {
    & $usedPort -iwad $usediWad @filteredArgs
}

exit
