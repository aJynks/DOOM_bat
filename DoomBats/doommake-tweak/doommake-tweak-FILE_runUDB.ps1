param(
    [string]$ArgString = "",
    [string]$RootDir   = ""
)

# ── Source port definitions ──────────────────────────────────────────────────
$sourcePort_exes = @{
    "cherry" = "d:\Projects\DoomProjects\_SourcePorts\Cherry-Doom\cherry-doom.exe"
    "choco"  = "d:\Projects\DoomProjects\_SourcePorts\Chocolate-Doom\chocolate-doom.exe"
    "crispy" = "d:\Projects\DoomProjects\_SourcePorts\Crispy-Doom\crispy-doom.exe"
    "dsda"   = "d:\Projects\DoomProjects\_SourcePorts\dsda-Doom\dsda-doom.exe"
    "edge"   = ""
    "helion" = "d:\Projects\DoomProjects\_SourcePorts\Helion-Doom\Helion.exe"
    "kex"    = "d:\Projects\DoomProjects\_SourcePorts\Kex-Doom\DOOM + DOOM II\doom_gog.exe"
    "nugget" = "d:\Projects\DoomProjects\_SourcePorts\Nugget-Doom\nugget-doom.exe"
    "nyan"   = "d:\Projects\DoomProjects\_SourcePorts\Nyan-Doom\nyan-doom.exe"
    "retro"  = ""
    "uz"     = "d:\Projects\DoomProjects\_SourcePorts\uzDoom\uzdoom.exe"
    "woof"   = "d:\Projects\DoomProjects\_SourcePorts\Woof-Doom\woof.exe"
}

$defaultPort = "nyan"

# ── Use the argument string directly ────────────────────────────────────────
$argString = $ArgString

# ── Detect and strip --dmake flag ────────────────────────────────────────────
$runDmake  = $false
$removed   = @()
if ($argString -match '(?i)(^|\s)--dmake(\s|$)') {
    $runDmake  = $true
    $argString = ($argString -replace '(?i)(^|\s)--dmake(\s|$)', ' ').Trim()
    $argString = $argString -replace '\s{2,}', ' '
    $removed  += "--dmake"
}

# ── Detect and strip any --<portname> flag ───────────────────────────────────
$selectedPort = $defaultPort

foreach ($portName in $sourcePort_exes.Keys) {
    $flag = "--$portName"
    if ($argString -match "(?i)(^|\s)$([regex]::Escape($flag))(\s|$)") {
        $selectedPort = $portName
        $before    = $argString
        $argString = ($argString -replace "(?i)(^|\s)$([regex]::Escape($flag))(\s|$)", ' ').Trim()
        $argString = $argString -replace '\s{2,}', ' '
        if ($argString -ne $before) { $removed += $flag }
        break
    }
}

# ── Strip -file <wads...> and extract temp wad ───────────────────────────────
# Ends at next -flag or --flag or end of string
$fileBlock = $null
$tempWad   = $null
if ($argString -match '(?i)((?:^|\s))-file\s+(.+?)(\s+--?\w|\s*$)') {
    $fileBlock = $Matches[2].Trim()
    $argString = ($argString -replace '(?i)((?:^|\s))-file\s+.+?(\s+--?\w|\s*$)', '$1$2').Trim()
    $argString = $argString -replace '\s{2,}', ' '
    $removed  += "-file <wads>"

    # Split fileBlock into individual wad tokens and find the one in Temp
    $wadTokens = $fileBlock -split '(?<=\.wad["]?)\s+(?=["A-Za-z])'
    $tempWad   = $wadTokens | Where-Object { $_ -match '(?i)\\Temp\\' } | Select-Object -First 1
    if ($tempWad) { $tempWad = $tempWad.Trim('"') }
}

# ── Read doom-loader.conf ────────────────────────────────────────────────────
$releaseWad = $null
$confPath   = Join-Path $RootDir.TrimEnd('\') "doom-loader.conf"
if (Test-Path $confPath) {
    $confContent = Get-Content $confPath
    $releaseLine = $confContent | Where-Object { $_ -match '^\s*release\s*=' }
    if ($releaseLine) {
        $releaseWad = ($releaseLine -split '=', 2)[1].Trim()
        $releaseWad = [System.IO.Path]::GetFullPath((Join-Path $RootDir.TrimEnd('\') $releaseWad))
    }
}

# ── Append release wad + temp wad to final command string ────────────────────
if ($releaseWad) {
    $argString = "$argString -file `"$releaseWad`""
    if ($tempWad) {
        $argString = "$argString `"$tempWad`""
    }
}

$portExe = $sourcePort_exes[$selectedPort]

# ── DEBUG (uncomment to enable) ──────────────────────────────────────────────
# Write-Host ""
# Write-Host "=== doomlaunch debug ===" -ForegroundColor Cyan
# Write-Host "Port             : $selectedPort"
# Write-Host "Exe              : $(if ($portExe) { $portExe } else { '(not set)' })"
# Write-Host "Run DoomMake     : $runDmake"
# Write-Host "Removed from str : $(if ($removed.Count) { $removed -join ', ' } else { '(nothing)' })"
# if ($fileBlock) {
#     Write-Host "Removed -file    :" -ForegroundColor DarkYellow
#     $fileBlock -split '(?<=\.wad["]?)\s+(?=["A-Za-z])' | ForEach-Object {
#         Write-Host "  $_" -ForegroundColor DarkYellow
#     }
# }
# Write-Host "Temp wad         : $(if ($tempWad) { $tempWad } else { '(none)' })"
# Write-Host "Final cmd string : $argString"
# Write-Host ""
# Write-Host "=== doom-loader.conf ===" -ForegroundColor Cyan
# Write-Host "WAD              : $(if ($releaseWad) { $releaseWad } else { '(not found)' })"
# Write-Host ""
# Write-Host "=== launching ===" -ForegroundColor Green
# if ($runDmake) { Write-Host "DoomMake         : running 'doommake make' in $RootDir" -ForegroundColor Magenta }
# Write-Host "CMD : `"$portExe`" $argString"
# Write-Host ""

# ── Launch ───────────────────────────────────────────────────────────────────
if ($portExe) {
    if ($runDmake) {
        Write-Host ">>> Running DoomMake..." -ForegroundColor Magenta
        Push-Location $RootDir
        cmd /c "doommake make"
        Pop-Location
        Write-Host ">>> DoomMake complete." -ForegroundColor Magenta
        Write-Host ""
    }
    cmd /c "`"$portExe`" $argString"
} else {
    Write-Host "ERROR: No exe defined for port '$selectedPort'" -ForegroundColor Red
}