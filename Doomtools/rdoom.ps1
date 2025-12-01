# rDoom.ps1
#-------------------------------------------------------------------------------------------------
# Editable Values
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

# Default resolved values
$defaultPort = $sourcePort_exes[$defaultPortKey]
$defaultIwad = $iwads[$defaultIwadKey]

# Default gameplay args
$defaultWarp      = "1"
$defaultSkill     = "4"

# Sound defaults
$defaultSoundOff  = $true   # TRUE  = adds -nosound
                             # FALSE = sound enabled

# Menu mode (no warp/skill)
$menuMode         = $false

# Help flag
$showHelp         = $false

#-------------------------------------------------------------------------------------------------
# Argument parsing
#-------------------------------------------------------------------------------------------------
$selectedPortKey = $defaultPortKey
$selectedIwadKey = $defaultIwadKey

$selectedPort = $defaultPort
$selectedIwad = $defaultIwad

# $extraArgs holds ALL other engine flags: -complevel, -file, -record, etc.
$extraArgs          = @()
$userWarpSpecified  = $false
$userSkillSpecified = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = $args[$i]

    # Help
    if ($arg -in @("-help", "--help", "help")) {
        $showHelp = $true
        continue
    }

    # Port key (nyan/dsda/woof/etc.)
    if ($sourcePort_exes.ContainsKey($arg)) {
        $selectedPortKey = $arg
        $selectedPort    = $sourcePort_exes[$selectedPortKey]
        continue
    }

    # IWAD key (doom/doom2/etc.)
    if ($iwads.ContainsKey($arg)) {
        $selectedIwadKey = $arg
        $selectedIwad    = $iwads[$selectedIwadKey]
        continue
    }

    # Menu flag: disables all warp/skill handling
    if ($arg -ieq "menu") {
        $menuMode = $true
        continue
    }

    # Warp handling
    if ($arg -ieq "-warp") {
        $userWarpSpecified = $true
        $extraArgs += $arg
        if ($i + 1 -lt $args.Count) {
            $i++
            $extraArgs += $args[$i]
        }
        continue
    }

    # Skill handling
    if ($arg -ieq "-skill") {
        $userSkillSpecified = $true
        $extraArgs += $arg
        if ($i + 1 -lt $args.Count) {
            $i++
            $extraArgs += $args[$i]
        }
        continue
    }

    # Sound toggles
    if ($arg -ieq "-sound") {
        # User explicitly wants sound ON
        $defaultSoundOff = $false
        continue
    }

    if ($arg -ieq "-nosound") {
        # User explicitly wants sound OFF
        $defaultSoundOff = $true
        continue
    }

    # Any other source-port argument (e.g. -complevel, -file, -record, etc.)
    $extraArgs += $arg
}

#-------------------------------------------------------------------------------------------------
# Help output
#-------------------------------------------------------------------------------------------------
if ($showHelp) {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  rDoom.ps1 - DoomMake Project Launcher"           -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  rdoom [port] [iwad] [menu] [options...]" -ForegroundColor Gray
    Write-Host ""
    Write-Host "WHERE:" -ForegroundColor Yellow
    Write-Host "  port:" -ForegroundColor Yellow
    Write-Host "    nyan    dsda    kex    uz    helion    woof    cherry    choco    crispy    nugget" -ForegroundColor Gray
    Write-Host "    (see rDoom.ps1 for exact paths; empty entries are not configured)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  iwad:" -ForegroundColor Yellow
    Write-Host "    doom    doom2    tnt    plutonia    heretic    hexen    free1    free2" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  menu:" -ForegroundColor Yellow
    Write-Host "    When present, the game starts at the main menu." -ForegroundColor Gray
    Write-Host "    All -warp / -skill defaults and overrides are DISABLED." -ForegroundColor Gray
    Write-Host ""
    Write-Host "DEFAULTS:" -ForegroundColor Yellow
    Write-Host "  Source port : nyan" -ForegroundColor Gray
    Write-Host "  IWAD        : doom2" -ForegroundColor Gray
    Write-Host "  Warp        : -warp 1  (unless you specify -warp #)" -ForegroundColor Gray
    Write-Host "  Skill       : -skill 4 (unless you specify -skill #)" -ForegroundColor Gray
    Write-Host "  Sound       : -nosound (use -sound to enable audio)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "DOOMMAKE PROJECT:" -ForegroundColor Yellow
    Write-Host "  This script MUST be run from the root of a DoomMake project." -ForegroundColor Gray
    Write-Host "  It expects a file:" -ForegroundColor Gray
    Write-Host "    doommake.project.properties" -ForegroundColor Gray
    Write-Host "  containing a line:" -ForegroundColor Gray
    Write-Host "    doommake.project.name=<ProjectName>" -ForegroundColor Gray
    Write-Host "  It will then load:" -ForegroundColor Gray
    Write-Host "    ./build/<ProjectName>.wad" -ForegroundColor Gray
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  rdoom" -ForegroundColor Gray
    Write-Host "    Use defaults: nyan + doom2, ./build/<project>.wad, -warp 1 -skill 4 -nosound" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  rdoom dsda doom" -ForegroundColor Gray
    Write-Host "    Use dsda-doom with doom.wad, project WAD, default warp/skill and -nosound." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  rdoom dsda -warp 5 -skill 2 -sound" -ForegroundColor Gray
    Write-Host "    dsda-doom, doom2.wad, project WAD, -warp 5 -skill 2, sound ON." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  rdoom menu" -ForegroundColor Gray
    Write-Host "    Start at menu: no -warp / -skill is applied, project WAD is still loaded." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  rdoom dsda doom2 -complevel 2 -file extra.wad" -ForegroundColor Gray
    Write-Host "    All extra flags (-complevel, -file, etc.) are passed directly to the port." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "NOTES:" -ForegroundColor Yellow
    Write-Host "  * Any unknown options are forwarded straight to the source port." -ForegroundColor Gray
    Write-Host "  * Ports with empty paths (e.g. cherry, choco, crispy) will error until configured." -ForegroundColor Gray
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

#-------------------------------------------------------------------------------------------------
# Validation: source port + IWAD
#-------------------------------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($selectedPort) -or -not (Test-Path $selectedPort)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: Source Port Not Found"          -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host ("  Key  : {0}" -f $selectedPortKey)      -ForegroundColor Red

    if ([string]::IsNullOrWhiteSpace($selectedPort)) {
        Write-Host "  Path : (not configured in script)"   -ForegroundColor Red
    } else {
        Write-Host ("  Path : {0}" -f $selectedPort)       -ForegroundColor Red
        Write-Host "         (file does not exist)"        -ForegroundColor Red
    }

    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host ("  Please edit rDoom.ps1 and set a valid") -ForegroundColor Red
    Write-Host ("  path to the [{0}] executable." -f $selectedPortKey) -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

if ([string]::IsNullOrWhiteSpace($selectedIwad) -or -not (Test-Path $selectedIwad)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: IWAD Not Found"                 -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host ("  Key  : {0}" -f $selectedIwadKey)      -ForegroundColor Red

    if ([string]::IsNullOrWhiteSpace($selectedIwad)) {
        Write-Host "  Path : (not configured in script)"   -ForegroundColor Red
    } else {
        Write-Host ("  Path : {0}" -f $selectedIwad)      -ForegroundColor Red
        Write-Host "         (file does not exist)"       -ForegroundColor Red
    }

    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host ("  Please edit rDoom.ps1 and set a valid") -ForegroundColor Red
    Write-Host ("  path to the [{0}] IWAD file." -f $selectedIwadKey) -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

#-------------------------------------------------------------------------------------------------
# DoomMake project detection & WAD from doommake.project.properties
#-------------------------------------------------------------------------------------------------
$projectRoot  = (Get-Location).Path
$projectFile  = Join-Path $projectRoot "doommake.project.properties"

if (-not (Test-Path $projectFile)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: DoomMake Project Not Found"     -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host "  Could not find: doommake.project.properties" -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host "  This script must be run from the root" -ForegroundColor Red
    Write-Host "  of the doom-tool project directory."   -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

$projectNameLine = Select-String -Path $projectFile -Pattern '^doommake\.project\.name=' -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $projectNameLine) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: Project Name Not Found"         -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host "  No line starting with:"                -ForegroundColor Red
    Write-Host "    doommake.project.name="              -ForegroundColor Red
    Write-Host "  was found in doommake.project.properties." -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

$projectName = $projectNameLine.Line.Split('=')[1].Trim()

if ([string]::IsNullOrWhiteSpace($projectName)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: Project Name Empty"             -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host "  doommake.project.name= has no value in" -ForegroundColor Red
    Write-Host "  doommake.project.properties."          -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

$buildDir        = Join-Path $projectRoot "build"
$projectWad      = $projectName + ".wad"
$projectWadPath  = Join-Path $buildDir $projectWad

if (-not (Test-Path $projectWadPath)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: Project WAD Not Found"          -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host ("  Expected WAD : {0}" -f $projectWad)   -ForegroundColor Red
    Write-Host ("  Location      : {0}" -f $buildDir)    -ForegroundColor Red
    Write-Host "----------------------------------------" -ForegroundColor Red
    Write-Host "  Make sure the project is built and"    -ForegroundColor Red
    Write-Host "  the WAD exists in the ./build folder." -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}

#-------------------------------------------------------------------------------------------------
# Menu mode: remove any user-specified -warp/-skill from extraArgs
#-------------------------------------------------------------------------------------------------
$finalExtraArgs = @()

if ($menuMode) {
    for ($i = 0; $i -lt $extraArgs.Count; $i++) {
        $a = $extraArgs[$i]
        if ($a -ieq "-warp" -or $a -ieq "-skill") {
            # Skip the flag and its value (if present)
            if ($i + 1 -lt $extraArgs.Count) { $i++ }
            continue
        }
        $finalExtraArgs += $a
    }
} else {
    $finalExtraArgs = $extraArgs
}

#-------------------------------------------------------------------------------------------------
# Build runtime argument list (shared by print + actual call)
#-------------------------------------------------------------------------------------------------
$runtimeArgs = @()

if (-not $menuMode) {
    if (-not $userWarpSpecified)  { $runtimeArgs += @("-warp",  $defaultWarp) }
    if (-not $userSkillSpecified) { $runtimeArgs += @("-skill", $defaultSkill) }
}

if ($defaultSoundOff) { $runtimeArgs += "-nosound" }

$runtimeArgs += $finalExtraArgs

#-------------------------------------------------------------------------------------------------
# Build and print final command line
#-------------------------------------------------------------------------------------------------
$parts = @(
    '"' + $selectedPort + '"'
    "-iwad"
    '"' + $selectedIwad + '"'
    "-file"
    '"' + $projectWadPath + '"'
) + $runtimeArgs

$commandLine = $parts -join ' '

Write-Host "----------------------------------------"
Write-Host "Source Port : $selectedPortKey"
Write-Host "IWAD        : $selectedIwadKey"
Write-Host "Project WAD : $projectWad"
Write-Host ("Menu Mode   : {0}" -f ($(if ($menuMode) { "ON" } else { "OFF" })))
Write-Host ""
Write-Host "Launching Doom with:"
Write-Host $commandLine
Write-Host "----------------------------------------"
Write-Host ""

# Actually execute it
& $selectedPort -iwad $selectedIwad -file $projectWadPath @runtimeArgs
