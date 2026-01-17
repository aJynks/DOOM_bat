# ============================================================================
# FILE DOWNLOAD TABLE - Edit this section to add/remove files
# ============================================================================
# Each entry can have a single URL (as a string) or multiple URLs (as an array)
$fileTable = @{
    "doommake-tweak" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Doomtools/doommake-tweak.ps1",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Doomtools/doommake-tweak.bat",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Doomtools/dmake.bat"
    )
    "doomrun" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/doomRUN/doom_runDoomWad.ps1",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/doomRUN/doom.bat"
    )
    "drawmaps" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/DrawMapsFromWAD/drawmaps.bat",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/DrawMapsFromWAD/drawmaps.py"
    )
    "playpal" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_genColourMap.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_genPlayPalPNG.py",
		"https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_playpalpng2Slade.py"
    )
    "doomcube" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/png2Cube/png2cube.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/ImageEditor%20Scripts/DoomCube/doomCube.bat"
    )
}

# ============================================================================
# GROUP TABLE - Define groups of files to download together
# ============================================================================
# Each group contains an array of file names from $fileTable
# Make sure group names are unique and don't conflict with file names
# Example:
# $groupTable = @{
#     "doomtools" = @("doommake-tweak", "dmake.bat")
# }
$groupTable = @{}

# ============================================================================
# SCRIPT LOGIC - Don't edit below unless you know what you're doing
# ============================================================================

# Get the target parameter
$Target = $args[0]

# Get current directory where script was called from
$downloadPath = Get-Location

# Function to display help
function Show-Help {
    Write-Host ""
    Write-Host "UpdateBats - GitHub File Downloader" -ForegroundColor Cyan
    Write-Host "====================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  updateBats [filename]           Download a specific file or group"
    Write-Host "  updateBats all [-a, --all]      Download all files in the file table"
    Write-Host "  updateBats list [-l, --list]    List all available files and groups"
    Write-Host "  updateBats help                 Show this help message"
    Write-Host "  updateBats -f [--listFiles]     List all available files"
    Write-Host "  updateBats -g [--listGroups]    List all available groups"
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  updateBats doommake-tweak       Download the doommake-tweak file(s)"
    Write-Host "  updateBats doomtools            Download all files in the doomtools group"
    Write-Host "  updateBats all                  Download everything"
    Write-Host "  updateBats list                 Show all available files and groups"
    Write-Host ""
    Write-Host "NOTES:" -ForegroundColor Yellow
    Write-Host "  - Files are downloaded to the current directory"
    Write-Host "  - Existing files will be overwritten"
    Write-Host "  - Groups are checked before individual files"
    Write-Host ""
}

# Function to download a single file
function Download-File {
    param(
        [string]$Url
    )
    
    # Extract actual filename from URL
    $actualFileName = Split-Path $Url -Leaf
    $destinationPath = Join-Path $downloadPath $actualFileName
    
    try {
        # Check if file already exists BEFORE downloading
        $fileExists = Test-Path $destinationPath
        
        if ($fileExists) {
            Write-Host "Downloading $actualFileName (overwriting existing file)..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $Url -OutFile $destinationPath -ErrorAction Stop
            Write-Host "Successfully overwritten: $destinationPath" -ForegroundColor Green
        } else {
            Write-Host "Downloading $actualFileName..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $Url -OutFile $destinationPath -ErrorAction Stop
            Write-Host "Successfully downloaded to: $destinationPath" -ForegroundColor Green
        }
        
        return @{
            Success = $true
            Overwritten = $fileExists
        }
    }
    catch {
        Write-Host "Failed to download $actualFileName" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        return @{
            Success = $false
            Overwritten = $false
        }
    }
}

# Function to download all URLs for a given entry
function Download-Entry {
    param(
        [string]$EntryName,
        $Urls
    )
    
    # Convert single URL to array for consistent handling
    if ($Urls -is [string]) {
        $Urls = @($Urls)
    }
    
    $entrySuccess = 0
    $entryFail = 0
    $entryOverwritten = 0
    
    foreach ($url in $Urls) {
        $result = Download-File -Url $url
        if ($result.Success) {
            $entrySuccess++
            if ($result.Overwritten) {
                $entryOverwritten++
            }
        } else {
            $entryFail++
        }
    }
    
    return @{
        Success = $entrySuccess
        Failed = $entryFail
        Overwritten = $entryOverwritten
    }
}

# Handle no parameter
if ([string]::IsNullOrWhiteSpace($Target)) {
    Write-Host "Error: No target specified" -ForegroundColor Red
    Show-Help
    exit 1
}

# Handle help
if ($Target -eq "help" -or $Target -eq "-h" -or $Target -eq "--help") {
    Show-Help
    exit 0
}

# Handle list (shows both files and groups)
if ($Target -eq "list" -or $Target -eq "-l" -or $Target -eq "--list") {
    Write-Host ""
    Write-Host "Available files:" -ForegroundColor Cyan
    Write-Host ""
    foreach ($key in $fileTable.Keys | Sort-Object) {
        $urls = $fileTable[$key]
        if ($urls -is [string]) {
            $urls = @($urls)
        }
        $fileCount = $urls.Count
        if ($fileCount -eq 1) {
            Write-Host "  $key" -ForegroundColor Yellow
        } else {
            Write-Host "  $key ($fileCount files)" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    Write-Host "Available groups:" -ForegroundColor Cyan
    Write-Host ""
    if ($groupTable.Count -eq 0) {
        Write-Host "  (No groups defined)" -ForegroundColor Gray
    } else {
        foreach ($key in $groupTable.Keys | Sort-Object) {
            $fileList = $groupTable[$key] -join ", "
            Write-Host "  $key" -ForegroundColor Yellow
            Write-Host "    Contains: $fileList" -ForegroundColor Gray
        }
    }
    Write-Host ""
    exit 0
}

# Handle list files
if ($Target -eq "-f" -or $Target -eq "--listFiles") {
    Write-Host ""
    Write-Host "Available files:" -ForegroundColor Cyan
    Write-Host ""
    foreach ($key in $fileTable.Keys | Sort-Object) {
        $urls = $fileTable[$key]
        if ($urls -is [string]) {
            $urls = @($urls)
        }
        $fileCount = $urls.Count
        if ($fileCount -eq 1) {
            Write-Host "  $key" -ForegroundColor Yellow
        } else {
            Write-Host "  $key ($fileCount files)" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    exit 0
}

# Handle list groups
if ($Target -eq "-g" -or $Target -eq "--listGroups") {
    Write-Host ""
    Write-Host "Available groups:" -ForegroundColor Cyan
    Write-Host ""
    foreach ($key in $groupTable.Keys | Sort-Object) {
        $fileList = $groupTable[$key] -join ", "
        Write-Host "  $key" -ForegroundColor Yellow
        Write-Host "    Contains: $fileList" -ForegroundColor Gray
    }
    Write-Host ""
    exit 0
}

# Handle --all or -a
if ($Target -eq "--all" -or $Target -eq "-a" -or $Target -eq "all") {
    Write-Host "Downloading all files..." -ForegroundColor Yellow
    Write-Host ""
    
    $successCount = 0
    $failCount = 0
    $overwriteCount = 0
    
    foreach ($entry in $fileTable.GetEnumerator()) {
        Write-Host "Processing '$($entry.Key)'..." -ForegroundColor Yellow
        $result = Download-Entry -EntryName $entry.Key -Urls $entry.Value
        $successCount += $result.Success
        $failCount += $result.Failed
        $overwriteCount += $result.Overwritten
        Write-Host ""
    }
    
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Download Summary:" -ForegroundColor Cyan
    Write-Host "  Successful: $successCount" -ForegroundColor Green
    if ($overwriteCount -gt 0) {
        Write-Host "  Overwritten: $overwriteCount" -ForegroundColor Yellow
    }
    Write-Host "  Failed: $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })
    Write-Host "========================================" -ForegroundColor Cyan
    
    exit $(if ($failCount -gt 0) { 1 } else { 0 })
}

# Check if target is a group first
if ($groupTable.ContainsKey($Target)) {
    Write-Host "Downloading group '$Target'..." -ForegroundColor Yellow
    Write-Host ""
    
    $successCount = 0
    $failCount = 0
    $overwriteCount = 0
    
    foreach ($fileName in $groupTable[$Target]) {
        if (-not $fileTable.ContainsKey($fileName)) {
            Write-Host "Warning: '$fileName' in group '$Target' not found in file table, skipping..." -ForegroundColor Yellow
            continue
        }
        
        Write-Host "Processing '$fileName'..." -ForegroundColor Yellow
        $result = Download-Entry -EntryName $fileName -Urls $fileTable[$fileName]
        $successCount += $result.Success
        $failCount += $result.Failed
        $overwriteCount += $result.Overwritten
        Write-Host ""
    }
    
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Download Summary for group '$Target':" -ForegroundColor Cyan
    Write-Host "  Successful: $successCount" -ForegroundColor Green
    if ($overwriteCount -gt 0) {
        Write-Host "  Overwritten: $overwriteCount" -ForegroundColor Yellow
    }
    Write-Host "  Failed: $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })
    Write-Host "========================================" -ForegroundColor Cyan
    
    exit $(if ($failCount -gt 0) { 1 } else { 0 })
}

# Check if target is a specific file
if ($fileTable.ContainsKey($Target)) {
    $result = Download-Entry -EntryName $Target -Urls $fileTable[$Target]
    
    $totalFiles = $result.Success + $result.Failed
    if ($totalFiles -gt 1) {
        Write-Host ""
        Write-Host "Summary for '$Target':" -ForegroundColor Cyan
        Write-Host "  Successful: $($result.Success)" -ForegroundColor Green
        if ($result.Overwritten -gt 0) {
            Write-Host "  Overwritten: $($result.Overwritten)" -ForegroundColor Yellow
        }
        Write-Host "  Failed: $($result.Failed)" -ForegroundColor $(if ($result.Failed -gt 0) { "Red" } else { "Green" })
    }
    
    exit $(if ($result.Failed -gt 0) { 1 } else { 0 })
}

# Not found in either table
Write-Host "Error: '$Target' not found in file table or group table" -ForegroundColor Red
Show-Help
exit 1