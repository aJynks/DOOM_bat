# ============================================================================
# FILE DOWNLOAD TABLE - Edit this section to add/remove files
# ============================================================================
# Each entry can have:
#   - A single URL (as a string)
#   - Multiple URLs (as an array)
#   - A GitHub directory URL (uses GitHub API to fetch all files recursively)
#     Format: https://github.com/owner/repo/tree/branch/path
$fileTable = @{
<#
    "playpal" = @(
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_genColourMap.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_genPlayPalPNG.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_playpalpng2Slade.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal_expandPal0.py",
        "https://raw.githubusercontent.com/aJynks/DOOM_bat/refs/heads/main/Python/playpal-colorMap/playpal.bat"
    )
#>
    "doomtools" = "https://github.com/aJynks/DOOM_bat/tree/main/Doomtools"
    "doomrun" = "https://github.com/aJynks/DOOM_bat/tree/main/doomRUN"
    "doomcube" = "https://github.com/aJynks/DOOM_bat/tree/main/ImageEditor%20Scripts/DoomCube"
    "krita" = "https://github.com/aJynks/DOOM_bat/tree/main/ImageEditor%20Scripts/Kirta"
    "photoshop" = "https://github.com/aJynks/DOOM_bat/tree/main/ImageEditor%20Scripts/Photoshop"
    "drawmapsfromwad" = "https://github.com/aJynks/DOOM_bat/tree/main/Python/DrawMapsFromWAD"
    "playpal-ColorMaps" = "https://github.com/aJynks/DOOM_bat/tree/main/Python/playpal-colorMap"
    "png2cube" = "https://github.com/aJynks/DOOM_bat/tree/main/Python/png2Cube"
}

# ============================================================================
# GROUP TABLE - Define groups of files to download together
# ============================================================================
$groupTable = @{
    "doom" = @("doomtools", "doomrun", "playpal-ColorMaps", "doomcube", "doomrun", "drawmapsfromwad")
    "gfxapps" = @("krita", "photoshop")
}

# ============================================================================
# SCRIPT LOGIC - Do not edit below unless you know what you are doing
# ============================================================================

# Load System.Web for URL decoding
Add-Type -AssemblyName System.Web

# Get the target parameter
$Target = $args[0]

# Get current directory where script was called from
$downloadPath = Get-Location

# Function to fetch all files from a GitHub directory recursively
function Get-GitHubDirectoryFiles {
    param(
        [string]$GitHubUrl
    )
    
    # Parse GitHub URL: https://github.com/owner/repo/tree/branch/path
    if ($GitHubUrl -match 'github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)') {
        $owner = $matches[1]
        $repo = $matches[2]
        $branch = $matches[3]
        $path = [System.Web.HttpUtility]::UrlDecode($matches[4])
    } elseif ($GitHubUrl -match 'github\.com/([^/]+)/([^/]+)/tree/([^/]+)/?$') {
        $owner = $matches[1]
        $repo = $matches[2]
        $branch = $matches[3]
        $path = ""
    } else {
        Write-Host "Error: Invalid GitHub URL format. Expected: https://github.com/owner/repo/tree/branch/path" -ForegroundColor Red
        return @()
    }
    
    Write-Host "Looking for files in: $path" -ForegroundColor Gray
    
    # Use GitHub API to get the tree recursively
    $apiUrl = "https://api.github.com/repos/$owner/$repo/git/trees/$branch`?recursive=1"
    
    try {
        Write-Host "Fetching file list from GitHub API..." -ForegroundColor Gray
        $response = Invoke-RestMethod -Uri $apiUrl -ErrorAction Stop
        
        # Filter files that start with the specified path and exclude README files
        $files = $response.tree | Where-Object { 
            $_.type -eq "blob" -and 
            ($path -eq "" -or $_.path -like "$path/*" -or $_.path -eq $path) -and
            $_.name -notlike "readme.md" -and
            $_.name -notlike "README.md" -and
            $_.name -notlike "README.MD" -and
            $_.name -notlike "Readme.md"
        }
        
        Write-Host "Path filter: $path" -ForegroundColor Gray
        Write-Host "Total files in repo: $($response.tree.Count)" -ForegroundColor Gray
        Write-Host "Filtered to: $($files.Count) files" -ForegroundColor Gray
        
        # Convert to raw GitHub URLs
        $rawUrls = @()
        foreach ($file in $files) {
            $rawUrl = "https://raw.githubusercontent.com/$owner/$repo/$branch/$($file.path)"
            $rawUrls += $rawUrl
        }
        
        Write-Host "Found $($rawUrls.Count) files in directory" -ForegroundColor Gray
        return $rawUrls
    }
    catch {
        Write-Host "Error fetching from GitHub API: $($_.Exception.Message)" -ForegroundColor Red
        return @()
    }
}

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
    Write-Host "  updateBats doomtools            Download all files from doomtools directory"
    Write-Host "  updateBats doom-scripts         Download the doom-scripts group"
    Write-Host "  updateBats all                  Download everything"
    Write-Host "  updateBats list                 Show all available files and groups"
    Write-Host ""
    Write-Host "NOTES:" -ForegroundColor Yellow
    Write-Host "  - Files are downloaded to the current directory"
    Write-Host "  - Subdirectories are created automatically from URL paths"
    Write-Host "  - GitHub directory URLs fetch all files recursively via API"
    Write-Host "  - Existing files will be overwritten"
    Write-Host "  - Groups are checked before individual files"
    Write-Host "  - README files are automatically excluded"
    Write-Host ""
}

# Function to download a single file
function Download-File {
    param(
        [string]$Url
    )
    
    # Extract actual filename from URL
    $actualFileName = Split-Path $Url -Leaf
    
    # Try to extract subdirectory structure from URL
    # Pattern: look for everything after the branch name
    $pattern = 'raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/(.+)$'
    if ($Url -match $pattern) {
        $fullPath = $matches[1]
        $subdirPath = Split-Path $fullPath -Parent
        
        # URL-decode directory names (handles %20 spaces, etc.)
        $subdirPath = [System.Web.HttpUtility]::UrlDecode($subdirPath)
        
        if (-not [string]::IsNullOrWhiteSpace($subdirPath)) {
            $fullDirectory = Join-Path $downloadPath $subdirPath
            
            # Create directory if it does not exist
            if (-not (Test-Path $fullDirectory)) {
                Write-Host "Creating directory: $subdirPath" -ForegroundColor Gray
                New-Item -ItemType Directory -Path $fullDirectory -Force | Out-Null
            }
            
            $destinationPath = Join-Path $fullDirectory $actualFileName
        } else {
            $destinationPath = Join-Path $downloadPath $actualFileName
        }
    } else {
        $destinationPath = Join-Path $downloadPath $actualFileName
    }
    
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
    
    # Check if this is a GitHub directory URL and fetch files if so
    $githubPattern = 'github\.com/.+/tree/'
    if ($Urls -is [string] -and $Urls -match $githubPattern) {
        Write-Host "Detected GitHub directory URL, fetching file list..." -ForegroundColor Cyan
        $Urls = Get-GitHubDirectoryFiles -GitHubUrl $Urls
        if ($Urls.Count -eq 0) {
            Write-Host "No files found or error occurred" -ForegroundColor Red
            return @{
                Success = 0
                Failed = 1
                Overwritten = 0
            }
        }
    }
    
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
        Write-Host "Processing $($entry.Key)..." -ForegroundColor Yellow
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
    Write-Host "Downloading group $Target..." -ForegroundColor Yellow
    Write-Host ""
    
    $successCount = 0
    $failCount = 0
    $overwriteCount = 0
    
    foreach ($fileName in $groupTable[$Target]) {
        if (-not $fileTable.ContainsKey($fileName)) {
            Write-Host "Warning: $fileName in group $Target not found in file table, skipping..." -ForegroundColor Yellow
            continue
        }
        
        Write-Host "Processing $fileName..." -ForegroundColor Yellow
        $result = Download-Entry -EntryName $fileName -Urls $fileTable[$fileName]
        $successCount += $result.Success
        $failCount += $result.Failed
        $overwriteCount += $result.Overwritten
        Write-Host ""
    }
    
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Download Summary for group $Target" -ForegroundColor Cyan
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
        Write-Host "Summary for $Target" -ForegroundColor Cyan
        Write-Host "  Successful: $($result.Success)" -ForegroundColor Green
        if ($result.Overwritten -gt 0) {
            Write-Host "  Overwritten: $($result.Overwritten)" -ForegroundColor Yellow
        }
        Write-Host "  Failed: $($result.Failed)" -ForegroundColor $(if ($result.Failed -gt 0) { "Red" } else { "Green" })
    }
    
    exit $(if ($result.Failed -gt 0) { 1 } else { 0 })
}

# Not found in either table
Write-Host "Error: $Target not found in file table or group table" -ForegroundColor Red
Show-Help
exit 1