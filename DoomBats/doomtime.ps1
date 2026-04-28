# doomtime.ps1 - Doom Floor/Ceiling Movement Calculator
param(
    [string]$ArgString = ""
)
$parts = $ArgString.Trim().Trim('"') -split '\s+'
$Mode  = if ($parts.Count -ge 1) { $parts[0] } else { "" }
$Value = if ($parts.Count -ge 2) { $parts[1] } else { "" }
$TICS = 35
$Speeds = [ordered]@{
    slow   = 1
    normal = 2
    fast   = 4
    turbo  = 8
}
function Show-Help {
    Write-Host ""
    Write-Host "  DOOMTIME" -ForegroundColor Red -NoNewline
    Write-Host " - Doom Floor/Ceiling Movement Calculator" -ForegroundColor White
    Write-Host "  A tool for calculating Doom floor and ceiling movement distances and times." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Doom runs at 35 tics per second." -ForegroundColor DarkGray
    Write-Host "  Floor/Ceiling speeds " -ForegroundColor DarkGray -NoNewline
    Write-Host "(map units per tic)" -ForegroundColor DarkGray
    Write-Host "    slow   " -ForegroundColor Yellow -NoNewline
    Write-Host "= 1 u/tic" -ForegroundColor DarkGray
    Write-Host "    normal " -ForegroundColor Yellow -NoNewline
    Write-Host "= 2 u/tic" -ForegroundColor DarkGray
    Write-Host "    fast   " -ForegroundColor Yellow -NoNewline
    Write-Host "= 4 u/tic" -ForegroundColor DarkGray
    Write-Host "    turbo  " -ForegroundColor Yellow -NoNewline
    Write-Host "= 8 u/tic" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  USAGE" -ForegroundColor White
    Write-Host "    doomtime " -ForegroundColor Yellow -NoNewline
    Write-Host "<command> <value>" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  COMMANDS" -ForegroundColor White
    Write-Host "    --help                " -ForegroundColor Yellow -NoNewline
    Write-Host "Show this help text" -ForegroundColor DarkGray
    Write-Host "    -time,    -t          " -ForegroundColor Yellow -NoNewline
    Write-Host "Calculate distance moved in a given time (seconds)" -ForegroundColor DarkGray
    Write-Host "    -minutes, -mins, -m   " -ForegroundColor Yellow -NoNewline
    Write-Host "Calculate distance moved in a given time (minutes)" -ForegroundColor DarkGray
    Write-Host "    -distance, -d         " -ForegroundColor Yellow -NoNewline
    Write-Host "Calculate time to move a given distance" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  EXAMPLES" -ForegroundColor White
    Write-Host "    doomtime -time 30     " -ForegroundColor Yellow -NoNewline
    Write-Host "Floor moving for 30 seconds - how far does it travel?" -ForegroundColor DarkGray
    Write-Host "    doomtime -t 30        " -ForegroundColor Yellow -NoNewline
    Write-Host "Same as above (short form)" -ForegroundColor DarkGray
    Write-Host "    doomtime -minutes 2   " -ForegroundColor Yellow -NoNewline
    Write-Host "Floor moving for 2 minutes - how far does it travel?" -ForegroundColor DarkGray
    Write-Host "    doomtime -m 2         " -ForegroundColor Yellow -NoNewline
    Write-Host "Same as above (short form)" -ForegroundColor DarkGray
    Write-Host "    doomtime -distance 1050  " -ForegroundColor Yellow -NoNewline
    Write-Host "Floor moving 1050 units - how long does it take?" -ForegroundColor DarkGray
    Write-Host "    doomtime -d 1050      " -ForegroundColor Yellow -NoNewline
    Write-Host "Same as above (short form)" -ForegroundColor DarkGray
    Write-Host ""
}
function Show-Time($seconds, $label) {
    Write-Host ""
    Write-Host "  Time" -ForegroundColor Cyan -NoNewline
    Write-Host "    : " -ForegroundColor DarkGray -NoNewline
    Write-Host $label -ForegroundColor Cyan
    foreach ($name in $Speeds.Keys) {
        $spd  = $Speeds[$name]
        $dist = [int]($seconds * $spd * $TICS)
        Write-Host ("  {0,-8}: " -f $name) -ForegroundColor DarkGray -NoNewline
        Write-Host ("{0} * {1} * {2} = " -f $seconds, $spd, $TICS) -ForegroundColor Yellow -NoNewline
        Write-Host ("{0} units" -f $dist) -ForegroundColor Green
    }
    Write-Host ""
}
function Show-Distance($units) {
    Write-Host ""
    Write-Host "  Distance" -ForegroundColor Cyan -NoNewline
    Write-Host " : " -ForegroundColor DarkGray -NoNewline
    Write-Host "${units} units" -ForegroundColor Cyan
    foreach ($name in $Speeds.Keys) {
        $spd     = $Speeds[$name]
        $rawTime = $units / $spd / $TICS
        Write-Host ("  {0,-8} : " -f $name) -ForegroundColor DarkGray -NoNewline
        Write-Host ("{0} / {1} / {2} = " -f $units, $spd, $TICS) -ForegroundColor Yellow -NoNewline
        if ($rawTime -eq [math]::Floor($rawTime)) {
            Write-Host ("{0}s" -f [int]$rawTime) -ForegroundColor Green
        } else {
            $rounded      = [math]::Round($rawTime)
            $adjustedDist = $rounded * $spd * $TICS
            Write-Host ("{0:F1}s " -f $rawTime) -ForegroundColor Green -NoNewline
            Write-Host ("({0}s : {1} units)" -f $rounded, $adjustedDist) -ForegroundColor DarkYellow
        }
    }
    Write-Host ""
}
# --- Dispatch ---
switch ($Mode.ToLower()) {
    { $_ -in "-time",    "-t"    } { Show-Time ([double]$Value) "${Value}s" }
    { $_ -in "-minutes", "-mins", "-m" } { Show-Time ([double]$Value * 60) "${Value}m" }
    { $_ -in "-distance","-d"    } { Show-Distance ([double]$Value) }
    { $_ -in "--help"            } { Show-Help }
    default                        { Show-Help }
}