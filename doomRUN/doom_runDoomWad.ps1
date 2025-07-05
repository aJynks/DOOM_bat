#-------------------------------------------------------------------------------------------------
# Editable Values
$sourcePort_exes = @{
    "nyan"   = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\nyan-Doom\nyan-doom.exe"
    "dsda"   = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\dsda-Doom\dsda-doom.exe"
    "kex"    = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\DOOM + DOOM II\doom_gog.exe"
    "cherry" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\cherry-Doom\Cherry-Doom-2.0.0\cherry-doom.exe"
    "gz"     = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\gz-Doom\gz-4.14.2\gzdoom.exe"
    "choco"  = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Cocolate-Doom\chocolate-doom-3.1.0\chocolate-doom.exe"
    "crispy" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Crispy-Doom\crispy-doom-7.0.0\crispy-doom.exe"
    "helion" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Helion\Helion-0.9.7.0_(SelfContained)\Helion.exe"
    "nugget" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Nugget-Doom\Nugget-Doom-4.3.0\nugget-doom.exe"
    "woof"   = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\Woof-Doom\Woof-15.2.0\woof.exe"
}

$iwads = @{
    "doom"     = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\doom.wad"
    "doom2"    = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\doom2.wad"
    "tnt"      = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Final Doom 1 - TNT - Evilution (tnt).wad"
    "plutonia" = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Final Doom 2 - Plutonia Experimen﻿t, The - (plutonia) .wad"
    "heretic"  = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Hexen 2 (HERETIC).WAD"
    "hexen"    = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Hexen 1 (HEXEN).WAD"
    "free1"    = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Freedoom 1.wad"
    "free2"    = "d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\Freedoom 2.wad"
}

# Default values
$defaultPort = $sourcePort_exes["nyan"]
$defaultIwad = $iwads["doom2"]

# Parse Arguments
$command_raw = $args
$usedPort = $defaultPort
$usediWad = $defaultIwad

# Validate Paths
function Validate-Path ($path) {
    if (!(Test-Path $path)) {
        Write-Error "Path not found: $path"
        exit
    }
}

Validate-Path $usedPort
Validate-Path $usediWad

# Process Arguments
$filteredArgs = @()
foreach ($arg in $command_raw) {
    # Check if the argument is an IWAD
    if ($iwads.ContainsKey($arg)) {
        $usediWad = $iwads[$arg]
    }
    # Check if the argument is a Source Port
    elseif ($sourcePort_exes.ContainsKey($arg)) {
        $usedPort = $sourcePort_exes[$arg]
    }
    else {
        $filteredArgs += $arg  # Keep the argument if it's not a source port or IWAD
    }
}

# Validate selected paths
Validate-Path $usedPort
Validate-Path $usediWad

# Launch the game with the modified IWAD and source port
# If no arguments are passed, use defaults


#& $usedPort -iwad $usediWad @filteredArgs

# Get the current directory and save the full path into $wadPath
$wadPath = Get-Location

# Get all files with the .wad extension in the current directory
$wadFiles = Get-ChildItem -Path $wadPath -Filter "*.wad" -ErrorAction SilentlyContinue

# Check the number of .wad files found
if ($wadFiles.Count -eq 1) {
    # If exactly one .wad file is found, save the filename into $wadName
    $wadName = $wadFiles[0].Name
    $UseWadFile = $true  # Set $UseWadFile to $true if exactly one .wad file is found
} else {
    # If no .wad files or more than one .wad file is found, set $UseWadFile to $null
    $UseWadFile = $null
}

if ($UseWadFile -ne $null) {
    Write-Host "A wad file was found and $UseWadFile is set to true."
    Write-Host "Wad Path: $wadPath"
	Write-Host "Use Wad File: $UseWadFile"
	Write-Host "Wad Name: $wadName"
	if ($args.Count -eq 0) {
		& $usedPort -iwad $usediWad -file "$wadPath/$wadName"
		exit
	} else {
		& $usedPort -iwad $usediWad -file "$wadPath/$wadName" @filteredArgs
		exit
	}
} else {
    if ($args.Count -eq 0) {
		& $usedPort -iwad $usediWad
		exit
	} else {
		& $usedPort -iwad $usediWad @filteredArgs
		exit
	}
}