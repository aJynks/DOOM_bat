param(
    [Alias("n")]
    [int]$NumOptions
)

function Show-Help {
    Write-Output "usage: cascadeChange.ps1 [-n] NUM_OPTIONS"
    Write-Output "example : powershell -ExecutionPolicy Bypass -File .\cascadeChange.ps1 -n 12"
}

function Build-CascadeValues {
    param(
        [int]$n
    )

    if ($n -lt 2) {
        throw "n must be at least 2"
    }

    $values = @()

    for ($remainingOptions = $n; $remainingOptions -gt 1; $remainingOptions--) {
        $value = [math]::Round(256 / $remainingOptions)
        $values += [int]$value
    }

    return $values
}

if ($args -contains "-h" -or $args -contains "--help") {
    Show-Help
    exit
}

if (-not $PSBoundParameters.ContainsKey("NumOptions")) {
    Show-Help
    exit 1
}

$values = Build-CascadeValues -n $NumOptions

Write-Output "Spawn:"
for ($i = 0; $i -lt $values.Count; $i++) {
    $optionNumber = $i + 1
    Write-Output "    TNT1 A 0 A_RandomJump(""Option$optionNumber"", $($values[$i]))"
}
Write-Output "    Goto Option$NumOptions"
Write-Output "--------------------"
Write-Output "Options: $NumOptions"
Write-Output "A_RandomJump values:"
Write-Output ($values -join ", ")