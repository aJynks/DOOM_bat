$command = $args[0]

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  doomogg -normilise"
    Write-Host "  doomogg -adjust +3"
    Write-Host "  doomogg -adjust -2.5"
}

function Get-MaxVolume {
    param(
        [string]$InputFile
    )

    $result = & ffmpeg -hide_banner -i "$InputFile" -map 0:a:0 -af volumedetect -f null NUL 2>&1 | Out-String

    if ($result -match "max_volume:\s*(-?\d+(\.\d+)?) dB") {
        return [double]$matches[1]
    }

    return $null
}

function Convert-Ogg {
    param(
        [string]$InputFile,
        [string]$OutputFile,
        [string]$AudioFilter
    )

    ffmpeg -y `
        -i "$InputFile" `
        -map 0:a:0 `
        -vn -sn -dn `
        -af "$AudioFilter" `
        -ac 2 `
        -ar 44100 `
        -c:a libvorbis `
        -q:a 5 `
        -map_metadata -1 `
        "$OutputFile"
}

if ($null -eq $command) {
    Show-Usage
    exit 1
}

# ------------------------------------------------------------
# doomogg -normilise
# Converts common audio files in the current folder to normalised OGG.
# ------------------------------------------------------------
if ($command -eq "-normilise") {
    $outDir = "ogg"

    if (!(Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }

    $audioExts = @(
        ".wav", ".mp3", ".flac", ".ogg", ".opus",
        ".m4a", ".aac", ".wma", ".aiff", ".aif"
    )

    $files = Get-ChildItem -File | Where-Object {
        $audioExts -contains $_.Extension.ToLower()
    }

    if ($files.Count -eq 0) {
        Write-Host "No audio files found."
        exit 0
    }

    foreach ($file in $files) {
        $output = Join-Path $outDir ($file.BaseName + ".ogg")

        Write-Host "Normalising: $($file.Name)"

        Convert-Ogg `
            -InputFile $file.FullName `
            -OutputFile $output `
            -AudioFilter "loudnorm=I=-14:LRA=11:TP=-1.5"
    }

    Write-Host "Done."
    exit 0
}

# ------------------------------------------------------------
# doomogg -adjust +/-x
# Adjusts existing OGG files in the current folder.
# Positive gain is clamped to avoid clipping.
# Negative gain is applied directly.
# ------------------------------------------------------------
if ($command -eq "-adjust") {
    $amount = $args[1]

    if ($null -eq $amount -or $amount -notmatch '^[+-]?\d+(\.\d+)?$') {
        Write-Host "Invalid adjust amount."
        Write-Host "Examples:"
        Write-Host "  doomogg -adjust +3"
        Write-Host "  doomogg -adjust -2.5"
        exit 1
    }

    $requestedGain = [double]$amount
    $targetPeak = -1.0
    $outDir = "adjusted"

    if (!(Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }

    $files = Get-ChildItem -File -Filter "*.ogg"

    if ($files.Count -eq 0) {
        Write-Host "No OGG files found."
        exit 0
    }

    foreach ($file in $files) {
        $output = Join-Path $outDir ($file.BaseName + ".ogg")
        $actualGain = $requestedGain

        Write-Host "Adjusting: $($file.Name)"

        if ($requestedGain -gt 0) {
            $maxVolume = Get-MaxVolume -InputFile $file.FullName

            if ($null -eq $maxVolume) {
                Write-Host "  Could not read peak volume. Skipping."
                continue
            }

            $safeGain = $targetPeak - $maxVolume

            if ($safeGain -le 0) {
                Write-Host "  Already near peak. Copying unchanged."
                Copy-Item $file.FullName $output -Force
                continue
            }

            if ($requestedGain -gt $safeGain) {
                $actualGain = $safeGain
            }
        }

        $gainText = "{0:0.###}" -f $actualGain

        Write-Host "  Applying $gainText dB"

        Convert-Ogg `
            -InputFile $file.FullName `
            -OutputFile $output `
            -AudioFilter "volume=${gainText}dB"
    }

    Write-Host "Done."
    exit 0
}

Show-Usage
exit 1