# dmake.ps1 - DoomMake-aware launcher:
# - Choose source port + IWAD
# - Default -warp 1 -skill 4, overridable
# - menu => no warp/skill at all
# - Default -nosound, overridable with -sound
# - Auto-load ./build/<ProjectName>.wad from doommake.project.properties
# - Commands:
#     dmake             => doommake + runDoom
#     dmake run         => runDoom
#     dmake clean       => doommake clean
#     dmake fresh       => doommake clean + doommake + runDoom
#     dmake --targets   => doommake --targets (no run)
#     dmake all         => doommake all + runDoom
#     dmake assets      => doommake assets
#     dmake convert     => doommake convert
#     dmake converttextures => doommake converttextures
#     dmake editor      => doommake editor
#     dmake init        => doommake init
#     dmake make        => doommake
#     dmake maps        => doommake maps
#     dmake maptextures => doommake maptextures
#     dmake patch       => doommake patch
#     dmake rebuildtextures => doommake rebuildtextures
#     dmake release     => doommake release + runDoom
#     dmake textures    => doommake textures
#     dmake help / -help / --help / /? => show help


#-------------------------------------------------------------------------------------------------
# Editable Values
#-------------------------------------------------------------------------------------------------
$sourcePort_exes = @{
    "nyan"   = "d:\Projects\DOOM\_SourcePorts\Nyan-Doom\nyan-doom-1.4.0\nyan-doom.exe"
    "dsda"   = "d:\Projects\DOOM\_SourcePorts\dsda-Doom\dsda-doom-0.29.4\dsda-doom.exe"
    "kex"    = "d:\Games\Doom\_SourcePort\Kex-Doom\DOOM + DOOM II\doom_gog.exe"
    "uz"     = "d:\Projects\DOOM\_SourcePorts\UZ-Doom-4.14.3\uzdoom.exe"
    "helion" = "d:\Projects\DOOM\_SourcePorts\Helion-Doom\Helion-0.9.9.0\Helion.exe"
    "woof"   = "d:\Projects\DOOM\_SourcePorts\Woof-Doom\Woof-15.3.0\woof.exe"
    "cherry" = ""
    "choco"  = ""
    "crispy" = ""
    "nugget" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Nugget-Doom\Nugget-Doom-4.3.0\nugget-doom.exe"
}

$iwads = @{
    "doom"     = "d:\Projects\DOOM\_SourcePorts\_iwads\doom.wad"
    "doom2"    = "d:\Projects\DOOM\_SourcePorts\_iwads\doom2.wad"
    "tnt"      = "d:\Projects\DOOM\_SourcePorts\_iwads\tnt.wad"
    "plutonia" = "d:\Projects\DOOM\_SourcePorts\_iwads\plutonia.wad"
    "heretic"  = "d:\Projects\DOOM\_SourcePorts\_iwads\heretic.wad"
    "hexen"    = "d:\Projects\DOOM\_SourcePorts\_iwads\hexen.wad"
    "free1"    = "d:\Projects\DOOM\_SourcePorts\_iwads\freedoom1.wad"
    "free2"    = "d:\Projects\DOOM\_SourcePorts\_iwads\freedoom2.wad"
}

# Default keys
$defaultPortKey = "nyan"
$defaultIwadKey = "doom2"

# Default gameplay
$defaultWarp  = "1"
$defaultSkill = "4"


#-------------------------------------------------------------------------------------------------
# State
#-------------------------------------------------------------------------------------------------
$selectedPortKey = $defaultPortKey
$selectedIwadKey = $defaultIwadKey
$selectedPortExe = $sourcePort_exes[$selectedPortKey]
$selectedIwad    = $iwads[$selectedIwadKey]

$extraArgs = @()

$menuMode           = $false
$userWarpSpecified  = $false
$userSkillSpecified = $false
$useSound           = $false   # false => add -nosound

# build (default), run, clean, fresh, --targets, targets, help
$command  = $null
$showHelp = $false


#-------------------------------------------------------------------------------------------------
# Helper: pretty error
#-------------------------------------------------------------------------------------------------
function Show-Error {
    param(
        [string] $Title,
        [string[]] $Lines
    )
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ("  ERROR: {0}" -f $Title) -ForegroundColor Red
    if ($Lines -and $Lines.Count -gt 0) {
        Write-Host "----------------------------------------" -ForegroundColor Red
        foreach ($l in $Lines) {
            Write-Host ("  {0}" -f $l) -ForegroundColor Red
        }
    }
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
}


#-------------------------------------------------------------------------------------------------
# Helper: help text
#-------------------------------------------------------------------------------------------------
function Show-Help {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  dmake.ps1 - DoomMake Project Wrapper"           -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  dmake [command/target] [flags] [port] [iwad] [engine-args...]" -ForegroundColor Gray
    Write-Host ""
    Write-Host "BASIC COMMANDS:" -ForegroundColor Yellow
    Write-Host "  dmake" -ForegroundColor Gray
    Write-Host "    doommake (default target) then run Doom." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  dmake run" -ForegroundColor Gray
    Write-Host "    Run Doom only (no doommake called)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  dmake clean" -ForegroundColor Gray
    Write-Host "    doommake clean (no run)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  dmake fresh" -ForegroundColor Gray
    Write-Host "    doommake clean + doommake + run Doom." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "DOOMMAKE TARGETS:" -ForegroundColor Yellow
    Write-Host "  dmake --targets     -> doommake --targets" -ForegroundColor Gray
    Write-Host "  dmake all           -> doommake all + run Doom" -ForegroundColor Gray
    Write-Host "  dmake assets        -> doommake assets" -ForegroundColor Gray
    Write-Host "  dmake convert       -> doommake convert" -ForegroundColor Gray
    Write-Host "  dmake converttextures -> doommake converttextures" -ForegroundColor Gray
    Write-Host "  dmake editor        -> doommake editor" -ForegroundColor Gray
    Write-Host "  dmake init          -> doommake init" -ForegroundColor Gray
    Write-Host "  dmake make          -> doommake (default target)" -ForegroundColor Gray
    Write-Host "  dmake maps          -> doommake maps" -ForegroundColor Gray
    Write-Host "  dmake maptextures   -> doommake maptextures" -ForegroundColor Gray
    Write-Host "  dmake patch         -> doommake patch" -ForegroundColor Gray
    Write-Host "  dmake rebuildtextures -> doommake rebuildtextures" -ForegroundColor Gray
    Write-Host "  dmake release       -> doommake release + run Doom" -ForegroundColor Gray
    Write-Host "  dmake textures      -> doommake textures" -ForegroundColor Gray
    Write-Host ""
    Write-Host "PORT / IWAD SELECTION:" -ForegroundColor Yellow
    Write-Host "  Ports (keys): nyan, dsda, kex, uz, helion, woof, cherry, choco, crispy, nugget" -ForegroundColor Gray
    Write-Host ("  Default port: {0}" -f $defaultPortKey) -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  IWADs (keys): doom, doom2, tnt, plutonia, heretic, hexen, free1, free2" -ForegroundColor Gray
    Write-Host ("  Default IWAD: {0}" -f $defaultIwadKey) -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor Yellow
    Write-Host "    dmake dsda doom        -> use dsda-doom with doom.wad" -ForegroundColor Gray
    Write-Host "    dmake nyan doom2       -> use nyan-doom with doom2.wad" -ForegroundColor Gray
    Write-Host ""
    Write-Host "GAMEPLAY FLAGS:" -ForegroundColor Yellow
    Write-Host "  -warp N    Default: -warp 1 (unless you specify your own -warp)." -ForegroundColor Gray
    Write-Host "  -skill N   Default: -skill 4 (unless you specify your own -skill)." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  menu       Disable all warp/skill from this script *and* user args." -ForegroundColor Gray
    Write-Host "             Example: dmake menu        -> build + run to menu." -ForegroundColor DarkGray
    Write-Host "                      dmake run menu    -> run only, to menu." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -sound     Enable sound (default is -nosound)." -ForegroundColor Gray
    Write-Host "             If you do NOT specify -sound, -nosound is added." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "PROJECT WAD:" -ForegroundColor Yellow
    Write-Host "  Must be run from a DoomMake project root containing:" -ForegroundColor Gray
    Write-Host "    doommake.project.properties" -ForegroundColor Gray
    Write-Host "  With a line:" -ForegroundColor Gray
    Write-Host "    doommake.project.name=<ProjectName>" -ForegroundColor Gray
    Write-Host "  The script uses:" -ForegroundColor Gray
    Write-Host "    ./build/<ProjectName>.wad" -ForegroundColor Gray
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  dmake" -ForegroundColor Gray
    Write-Host "    Build project + run Doom with defaults (-warp 1 -skill 4 -nosound)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  dmake run dsda doom -warp 5 -skill 2 -sound" -ForegroundColor Gray
    Write-Host "    Run dsda-doom with doom.wad, your warp/skill, sound on." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  dmake release nyan doom2 menu" -ForegroundColor Gray
    Write-Host "    doommake release, then run nyan-doom with doom2.wad to main menu" -ForegroundColor DarkGray
    Write-Host "    (no warp/skill, default -nosound)." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "HELP:" -ForegroundColor Yellow
    Write-Host "  dmake help" -ForegroundColor Gray
    Write-Host "  dmake -help" -ForegroundColor Gray
    Write-Host "  dmake --help" -ForegroundColor Gray
    Write-Host "  dmake /?" -ForegroundColor Gray
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
}


#-------------------------------------------------------------------------------------------------
# Argument parsing
#-------------------------------------------------------------------------------------------------
for ($i = 0; $i -lt $args.Count; $i++) {

    $arg = $args[$i]
    $key = $arg.ToLowerInvariant()

    # HELP -------------------------------------------------------------
    if ($key -in @("--help","-help","help","/?")) {
        if ($command -and $command -ne "help") { $command = "error"; break }
        $command  = "help"
        $showHelp = $true
        continue
    }

    # COMMANDS ---------------------------------------------------------
    if ($key -eq "run") {
        if ($command -and $command -ne "run") { $command = "error"; break }
        $command = "run"
        continue
    }
    if ($key -eq "clean") {
        if ($command -and $command -ne "clean") { $command = "error"; break }
        $command = "clean"
        continue
    }
    if ($key -eq "fresh") {
        if ($command -and $command -ne "fresh") { $command = "error"; break }
        $command = "fresh"
        continue
    }
    if ($key -eq "--targets") {
        if ($command -and $command -ne "--targets") { $command = "error"; break }
        $command = "--targets"
        continue
    }
    if ($key -eq "all") {
        if ($command -and $command -ne "all") { $command = "error"; break }
        $command = "all"
        continue
    }
    if ($key -eq "assets") {
        if ($command -and $command -ne "assets") { $command = "error"; break }
        $command = "assets"
        continue
    }
    if ($key -eq "convert") {
        if ($command -and $command -ne "convert") { $command = "error"; break }
        $command = "convert"
        continue
    }
    if ($key -eq "converttextures") {
        if ($command -and $command -ne "converttextures") { $command = "error"; break }
        $command = "converttextures"
        continue
    }
    if ($key -eq "editor") {
        if ($command -and $command -ne "editor") { $command = "error"; break }
        $command = "editor"
        continue
    }
    if ($key -eq "init") {
        if ($command -and $command -ne "init") { $command = "error"; break }
        $command = "init"
        continue
    }
    if ($key -eq "make") {
        if ($command -and $command -ne "make") { $command = "error"; break }
        $command = "make"
        continue
    }
    if ($key -eq "maps") {
        if ($command -and $command -ne "maps") { $command = "error"; break }
        $command = "maps"
        continue
    }
    if ($key -eq "maptextures") {
        if ($command -and $command -ne "maptextures") { $command = "error"; break }
        $command = "maptextures"
        continue
    }
    if ($key -eq "patch") {
        if ($command -and $command -ne "patch") { $command = "error"; break }
        $command = "patch"
        continue
    }
    if ($key -eq "rebuildtextures") {
        if ($command -and $command -ne "rebuildtextures") { $command = "error"; break }
        $command = "rebuildtextures"
        continue
    }
    if ($key -eq "release") {
        if ($command -and $command -ne "release") { $command = "error"; break }
        $command = "release"
        continue
    }
    if ($key -eq "textures") {
        if ($command -and $command -ne "textures") { $command = "error"; break }
        $command = "textures"
        continue
    }

    # PORT SELECTION ---------------------------------------------------
    if ($sourcePort_exes.ContainsKey($key)) {
        $selectedPortKey = $key
        $selectedPortExe = $sourcePort_exes[$selectedPortKey]
        continue
    }

    # IWAD SELECTION ---------------------------------------------------
    if ($iwads.ContainsKey($key)) {
        $selectedIwadKey = $key
        $selectedIwad    = $iwads[$selectedIwadKey]
        continue
    }

    # MENU MODE --------------------------------------------------------
    if ($key -eq "menu") {
        $menuMode = $true
        continue
    }

    # SOUND ENABLE -----------------------------------------------------
    if ($key -eq "-sound") {
        $useSound = $true
        continue
    }

    # -warp N ----------------------------------------------------------
    if ($key -eq "-warp") {
        $userWarpSpecified = $true
        $extraArgs += $arg
        if ($i + 1 -lt $args.Count) { $i++; $extraArgs += $args[$i] }
        continue
    }

    # -skill N ---------------------------------------------------------
    if ($key -eq "-skill") {
        $userSkillSpecified = $true
        $extraArgs += $arg
        if ($i + 1 -lt $args.Count) { $i++; $extraArgs += $args[$i] }
        continue
    }

    # EVERYTHING ELSE → pass through ----------------------------------
    $extraArgs += $arg
}

if ($command -eq "error") {
    Show-Error "Conflicting commands" @(
        "Use only one primary command/target or help flag."
    )
    exit 1
}

# HELP: show and exit early (no validation needed)
if ($command -eq "help" -or $showHelp) {
    Show-Help
    exit 0
}

# Default behavior:
if (-not $command) {
    $command = "build"   # doommake + runDoom
}


#-------------------------------------------------------------------------------------------------
# Validate port + IWAD (only needed if we might run Doom)
#-------------------------------------------------------------------------------------------------
$needsRunDoom = $command -in @("build","run","fresh","all","release")

if ($needsRunDoom) {
    if ([string]::IsNullOrWhiteSpace($selectedPortExe) -or -not (Test-Path $selectedPortExe)) {
        Show-Error "Source Port Not Found" @(
            ("Key  : {0}" -f $selectedPortKey),
            "Path : (not configured or file missing)",
            "",
            "Please edit dmake.ps1 and set a valid",
            ("path for the [{0}] executable." -f $selectedPortKey)
        )
        exit 1
    }

    if ([string]::IsNullOrWhiteSpace($selectedIwad) -or -not (Test-Path $selectedIwad)) {
        Show-Error "IWAD Not Found" @(
            ("Key  : {0}" -f $selectedIwadKey),
            "Path : (not configured or file missing)",
            "",
            "Please edit dmake.ps1 and set a valid",
            ("path for the [{0}] IWAD file." -f $selectedIwadKey)
        )
        exit 1
    }
}


#-------------------------------------------------------------------------------------------------
# DoomMake project detection
#-------------------------------------------------------------------------------------------------
$projectRoot = (Get-Location).Path
$projectFile = Join-Path $projectRoot "doommake.project.properties"

if (-not (Test-Path $projectFile)) {
    Show-Error "DoomMake Project Not Found" @(
        "Could not find: doommake.project.properties",
        "",
        "You must run dmake inside the DoomMake project root directory."
    )
    exit 1
}

$projectNameLine = Select-String -Path $projectFile -Pattern '^\s*doommake\.project\.name=' | Select-Object -First 1

if (-not $projectNameLine) {
    Show-Error "Project Name Not Found" @(
        "No line starting with:",
        "  doommake.project.name=",
        "was found in doommake.project.properties."
    )
    exit 1
}

$projectName = $projectNameLine.Line.Split('=')[1].Trim()
$buildDir = Join-Path $projectRoot "build"
$projectWad = $projectName + ".wad"
$projectWadPath = Join-Path $buildDir $projectWad


#-------------------------------------------------------------------------------------------------
# Helper: build final arg list
#-------------------------------------------------------------------------------------------------
function Get-FinalArgs {
    param (
        [bool]   $MenuMode,
        [bool]   $UseSound,
        [bool]   $UserWarpSpecified,
        [bool]   $UserSkillSpecified,
        [string] $SelectedIwad,
        [string] $ProjectWadPath,
        [string] $DefaultWarp,
        [string] $DefaultSkill,
        [string[]] $ExtraArgs
    )

    $argsList = @(
        "-iwad", $SelectedIwad,
        "-file", $ProjectWadPath
    )

    if ($MenuMode) {
        $cleanExtra = @()
        for ($j = 0; $j -lt $ExtraArgs.Count; $j++) {
            $a = $ExtraArgs[$j].ToLowerInvariant()
            if ($a -eq "-warp" -or $a -eq "-skill") {
                if ($j + 1 -lt $ExtraArgs.Count) { $j++ }
                continue
            }
            $cleanExtra += $ExtraArgs[$j]
        }
        $argsList += $cleanExtra
    }
    else {
        if (-not $UserWarpSpecified) {
            $argsList += @("-warp", $DefaultWarp)
        }
        if (-not $UserSkillSpecified) {
            $argsList += @("-skill", $DefaultSkill)
        }
        $argsList += $ExtraArgs
    }

    if (-not $UseSound) {
        $argsList += "-nosound"
    }

    return ,$argsList
}


#-------------------------------------------------------------------------------------------------
# Helper: runDoom
#-------------------------------------------------------------------------------------------------
function Invoke-RunDoom {
    param(
        [string] $PortExe,
        [string] $PortKey,
        [string] $IwadKey,
        [string] $ProjectName,
        [string] $ProjectWadPath,
        [bool]   $MenuMode,
        [bool]   $UseSound,
        [bool]   $UserWarpSpecified,
        [bool]   $UserSkillSpecified,
        [string] $SelectedIwad,
        [string] $DefaultWarp,
        [string] $DefaultSkill,
        [string[]] $ExtraArgs
    )

    if (-not (Test-Path $ProjectWadPath)) {
        Show-Error "Project WAD Missing" @(
            ("Expected: {0}" -f $ProjectWadPath),
            "",
            "Make sure the project is built and the WAD exists in ./build."
        )
        exit 1
    }

    $finalArgs = Get-FinalArgs `
        -MenuMode $MenuMode `
        -UseSound $UseSound `
        -UserWarpSpecified $UserWarpSpecified `
        -UserSkillSpecified $UserSkillSpecified `
        -SelectedIwad $SelectedIwad `
        -ProjectWadPath $ProjectWadPath `
        -DefaultWarp $DefaultWarp `
        -DefaultSkill $DefaultSkill `
        -ExtraArgs $ExtraArgs

    $cmd = '"' + $PortExe + '" ' + ($finalArgs -join ' ')

    Write-Host "----------------------------------------" -ForegroundColor DarkCyan
    Write-Host ("Source Port : {0}" -f $PortKey) -ForegroundColor Cyan
    Write-Host ("IWAD        : {0}" -f $IwadKey) -ForegroundColor Cyan
    Write-Host ("Project WAD : {0}" -f $ProjectName) -ForegroundColor Cyan
    Write-Host ("Menu Mode   : {0}" -f ($(if ($MenuMode){"ON"}else{"OFF"}))) -ForegroundColor Cyan
    Write-Host ("Sound       : {0}" -f ($(if ($UseSound){"ON"}else{"OFF (nosound)"}))) -ForegroundColor Cyan
    Write-Host "" -ForegroundColor Cyan
    Write-Host "Launching with:" -ForegroundColor Yellow
    Write-Host $cmd -ForegroundColor Gray
    Write-Host "----------------------------------------" -ForegroundColor DarkCyan

    & $PortExe @finalArgs
    exit $LASTEXITCODE
}


#-------------------------------------------------------------------------------------------------
# High-Level Command Execution
#-------------------------------------------------------------------------------------------------
switch ($command) {

    "--targets" {
        Write-Host "---=== DoomMake Targets ===---" -ForegroundColor Yellow
        & doommake --targets
        exit $LASTEXITCODE
    }

    "clean" {
        Write-Host "---=== CLEANING build dir ===---" -ForegroundColor Yellow
        & doommake clean
        exit $LASTEXITCODE
    }

    "assets" {
        Write-Host "---=== BUILDING ASSETS ===---" -ForegroundColor Yellow
        & doommake assets
        exit $LASTEXITCODE
    }

    "convert" {
        Write-Host "---=== CONVERTING ===---" -ForegroundColor Yellow
        & doommake convert
        exit $LASTEXITCODE
    }

    "converttextures" {
        Write-Host "---=== CONVERTING TEXTURES ===---" -ForegroundColor Yellow
        & doommake converttextures
        exit $LASTEXITCODE
    }

    "editor" {
        Write-Host "---=== LAUNCHING EDITOR ===---" -ForegroundColor Yellow
        & doommake editor
        exit $LASTEXITCODE
    }

    "init" {
        Write-Host "---=== INIT PROJECT ===---" -ForegroundColor Yellow
        & doommake init
        exit $LASTEXITCODE
    }

    "make" {
        Write-Host "---=== DOOMMAKE (DEFAULT TARGET) ===---" -ForegroundColor Yellow
        & doommake
        exit $LASTEXITCODE
    }

    "maps" {
        Write-Host "---=== BUILDING MAPS ===---" -ForegroundColor Yellow
        & doommake maps
        exit $LASTEXITCODE
    }

    "maptextures" {
        Write-Host "---=== BUILDING MAP TEXTURES ===---" -ForegroundColor Yellow
        & doommake maptextures
        exit $LASTEXITCODE
    }

    "patch" {
        Write-Host "---=== PATCHING ===---" -ForegroundColor Yellow
        & doommake patch
        exit $LASTEXITCODE
    }

    "rebuildtextures" {
        Write-Host "---=== REBUILDING TEXTURES ===---" -ForegroundColor Yellow
        & doommake rebuildtextures
        exit $LASTEXITCODE
    }

    "textures" {
        Write-Host "---=== BUILDING TEXTURES ===---" -ForegroundColor Yellow
        & doommake textures
        exit $LASTEXITCODE
    }

    "all" {
        Write-Host "---=== DOOMMAKE ALL ===---" -ForegroundColor Yellow
        & doommake all

        Invoke-RunDoom `
            -PortExe $selectedPortExe `
            -PortKey $selectedPortKey `
            -IwadKey $selectedIwadKey `
            -ProjectName $projectName `
            -ProjectWadPath $projectWadPath `
            -MenuMode $menuMode `
            -UseSound $useSound `
            -UserWarpSpecified $userWarpSpecified `
            -UserSkillSpecified $userSkillSpecified `
            -SelectedIwad $selectedIwad `
            -DefaultWarp $defaultWarp `
            -DefaultSkill $defaultSkill `
            -ExtraArgs $extraArgs
    }

    "release" {
        Write-Host "---=== DOOMMAKE RELEASE ===---" -ForegroundColor Yellow
        & doommake release

        Invoke-RunDoom `
            -PortExe $selectedPortExe `
            -PortKey $selectedPortKey `
            -IwadKey $selectedIwadKey `
            -ProjectName $projectName `
            -ProjectWadPath $projectWadPath `
            -MenuMode $menuMode `
            -UseSound $useSound `
            -UserWarpSpecified $userWarpSpecified `
            -UserSkillSpecified $userSkillSpecified `
            -SelectedIwad $selectedIwad `
            -DefaultWarp $defaultWarp `
            -DefaultSkill $defaultSkill `
            -ExtraArgs $extraArgs
    }

    "run" {
        Invoke-RunDoom `
            -PortExe $selectedPortExe `
            -PortKey $selectedPortKey `
            -IwadKey $selectedIwadKey `
            -ProjectName $projectName `
            -ProjectWadPath $projectWadPath `
            -MenuMode $menuMode `
            -UseSound $useSound `
            -UserWarpSpecified $userWarpSpecified `
            -UserSkillSpecified $userSkillSpecified `
            -SelectedIwad $selectedIwad `
            -DefaultWarp $defaultWarp `
            -DefaultSkill $defaultSkill `
            -ExtraArgs $extraArgs
    }

    "fresh" {
        Write-Host "---=== CLEANING build dir ===---" -ForegroundColor Yellow
        & doommake clean

        Write-Host "" -ForegroundColor Yellow
        Write-Host "---=== BUILDING ===---" -ForegroundColor Yellow
        & doommake

        Invoke-RunDoom `
            -PortExe $selectedPortExe `
            -PortKey $selectedPortKey `
            -IwadKey $selectedIwadKey `
            -ProjectName $projectName `
            -ProjectWadPath $projectWadPath `
            -MenuMode $menuMode `
            -UseSound $useSound `
            -UserWarpSpecified $userWarpSpecified `
            -UserSkillSpecified $userSkillSpecified `
            -SelectedIwad $selectedIwad `
            -DefaultWarp $defaultWarp `
            -DefaultSkill $defaultSkill `
            -ExtraArgs $extraArgs
    }

    "build" {
        Write-Host "---=== BUILDING ===---" -ForegroundColor Yellow
        & doommake

        Invoke-RunDoom `
            -PortExe $selectedPortExe `
            -PortKey $selectedPortKey `
            -IwadKey $selectedIwadKey `
            -ProjectName $projectName `
            -ProjectWadPath $projectWadPath `
            -MenuMode $menuMode `
            -UseSound $useSound `
            -UserWarpSpecified $userWarpSpecified `
            -UserSkillSpecified $userSkillSpecified `
            -SelectedIwad $selectedIwad `
            -DefaultWarp $defaultWarp `
            -DefaultSkill $defaultSkill `
            -ExtraArgs $extraArgs
    }

    default {
        Show-Error "Unknown command" @(
            ("Command: {0}" -f $command),
            "",
            "Use 'dmake help' for usage."
        )
        exit 1
    }
}
