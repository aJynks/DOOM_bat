#Requires -Version 5.1

param(
    [Parameter(Position=0)]
    [string]$action = "backup",
    
    [Parameter(Position=1)]
    [string]$restorepath = "",
    
    [Parameter()]
    [string]$path = "",
    
    [Parameter()]
    [string]$force = "",
    
    [Parameter()]
    [switch]$fresh,
    
    [Parameter()]
    [switch]$dumbcopy,
    
    [Parameter()]
    [switch]$clean,
    
    [Parameter()]
    [switch]$verify
)

# ============================================================================
# CONFIGURATION - Edit this path to point to your IWAD file
# You can use Windows-style backslashes or forward slashes
# ============================================================================
$IWAD_PATH = "d:\Project\DoomProjects\_SourcePorts\_iwads\doom2.wad"
# ============================================================================

$CONFIG_FILE = ".doomProject_backup.conf"
$DOOMTOOLS_REQUIRED_FILES = @("doommake.properties", "doommake.project.properties", "doommake.script")

function Show-Help {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Project Backup & Restore Utility" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  dtbackup [action] [options]" -ForegroundColor White
    Write-Host ""
    Write-Host "ACTIONS:" -ForegroundColor Yellow
    Write-Host "  backup              " -NoNewline -ForegroundColor Green
    Write-Host "Backup the current project directory"
    Write-Host "  restore             " -NoNewline -ForegroundColor Green
    Write-Host "Restore project from backup"
    Write-Host "  verify              " -NoNewline -ForegroundColor Green
    Write-Host "Verify local files against backup"
    Write-Host "  help                " -NoNewline -ForegroundColor Green
    Write-Host "Show this help message"
    Write-Host ""
    Write-Host "BACKUP OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -path <directory>   " -NoNewline -ForegroundColor Green
    Write-Host "Set backup directory (first-time backup only)"
    Write-Host "  -force <directory>  " -NoNewline -ForegroundColor Green
    Write-Host "Override backup path, dumb copy (ignore hashes)"
    Write-Host "  -dumbcopy           " -NoNewline -ForegroundColor Green
    Write-Host "Copy all files regardless of hash changes"
    Write-Host "  -clean              " -NoNewline -ForegroundColor Green
    Write-Host "Delete files/folders in backup that don't exist in source"
    Write-Host ""
    Write-Host "RESTORE OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -fresh              " -NoNewline -ForegroundColor Green
    Write-Host "Clean directory, copy all files from config path"
    Write-Host "  -fresh <directory>  " -NoNewline -ForegroundColor Green
    Write-Host "Clean directory, copy all files from specified path"
    Write-Host "  <directory>         " -NoNewline -ForegroundColor Green
    Write-Host "Restore from path (empty directory only)"
    Write-Host ""
    Write-Host "BACKUP EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  First-time backup (creates config file):" -ForegroundColor Gray
    Write-Host "    dtbackup -path " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Subsequent backups (uses saved config):" -ForegroundColor Gray
    Write-Host "    dtbackup" -ForegroundColor White
    Write-Host ""
    Write-Host "  Force backup to different location (dumb copy):" -ForegroundColor Gray
    Write-Host "    dtbackup -force " -NoNewline -ForegroundColor White
    Write-Host '"d:\TempBackup\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Backup everything regardless of changes:" -ForegroundColor Gray
    Write-Host "    dtbackup -dumbcopy" -ForegroundColor White
    Write-Host ""
    Write-Host "  Backup and remove files from backup not in source:" -ForegroundColor Gray
    Write-Host "    dtbackup -clean" -ForegroundColor White
    Write-Host ""
    Write-Host "RESTORE EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  Smart restore (skip unchanged files):" -ForegroundColor Gray
    Write-Host "    dtbackup restore" -ForegroundColor White
    Write-Host ""
    Write-Host "  Fresh restore from config (clean + copy all):" -ForegroundColor Gray
    Write-Host "    dtbackup restore -fresh" -ForegroundColor White
    Write-Host ""
    Write-Host "  Fresh restore from different location:" -ForegroundColor Gray
    Write-Host "    dtbackup restore -fresh " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Restore into empty directory:" -ForegroundColor Gray
    Write-Host "    dtbackup restore " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "VERIFY EXAMPLE:" -ForegroundColor Yellow
    Write-Host "  Compare local files with backup:" -ForegroundColor Gray
    Write-Host "    dtbackup verify" -ForegroundColor White
    Write-Host ""
    Write-Host "NOTES:" -ForegroundColor Yellow
    Write-Host "  - Hash-based change detection skips unchanged files" -ForegroundColor Gray
    Write-Host "  - Empty directories are preserved" -ForegroundColor Gray
    Write-Host "  - IWAD paths automatically updated in DoomTools projects" -ForegroundColor Gray
    Write-Host "  - doom-loader.conf and doommake.properties always copied" -ForegroundColor Gray
    Write-Host "  - Supports special characters in filenames" -ForegroundColor Gray
    Write-Host "  - Excludes .git directories from backup/restore" -ForegroundColor Gray
    Write-Host ""
    Write-Host "CONFIG FILE:" -ForegroundColor Yellow
    Write-Host "  .doomProject_backup.conf" -ForegroundColor Cyan
    Write-Host "  - Contains backup path and file hashes" -ForegroundColor Gray
    Write-Host "  - Edit manually to change backup location permanently" -ForegroundColor Gray
    Write-Host "  - Automatically backed up and restored" -ForegroundColor Gray
    Write-Host ""
    Write-Host "IWAD CONFIGURATION:" -ForegroundColor Yellow
    Write-Host "  Edit " -NoNewline -ForegroundColor Gray
    Write-Host "$" -NoNewline -ForegroundColor Cyan
    Write-Host "IWAD_PATH" -NoNewline -ForegroundColor Cyan
    Write-Host " at the top of doomtools-backup-v2.ps1" -ForegroundColor Gray
    Write-Host "  This path is updated in all DoomTools projects after restore" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

function Get-FileHashMD5 {
    param([string]$FilePath)
    try {
        $hash = Get-FileHash -LiteralPath $FilePath -Algorithm MD5
        return $hash.Hash
    }
    catch {
        return $null
    }
}

function Read-Config {
    if (-not (Test-Path $CONFIG_FILE)) {
        return $null
    }
    
    $config = @{
        BackupPath = ""
        FileHashes = @{}
    }
    
    $content = Get-Content $CONFIG_FILE -Raw
    $lines = $content -split "`r?`n"
    
    $inHashSection = $false
    foreach ($line in $lines) {
        $line = $line.Trim()
        
        if ($line -eq "" -or $line.StartsWith("#")) {
            continue
        }
        
        if ($line -eq "[BackupPath]") {
            continue
        }
        elseif ($line -eq "[FileHashes]") {
            $inHashSection = $true
            continue
        }
        
        if (-not $inHashSection) {
            if ($line.StartsWith("Path=")) {
                $config.BackupPath = $line.Substring(5).Trim()
            }
        }
        else {
            if ($line -match "^(.+?)=(.+)$") {
                $config.FileHashes[$matches[1]] = $matches[2]
            }
        }
    }
    
    return $config
}

function Write-Config {
    param(
        [string]$BackupPath,
        [hashtable]$FileHashes
    )
    
    $content = @"
# Project Backup Configuration
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

[BackupPath]
Path=$BackupPath

[FileHashes]
"@
    
    foreach ($file in ($FileHashes.Keys | Sort-Object)) {
        $content += "`n$file=$($FileHashes[$file])"
    }
    
    Set-Content -Path $CONFIG_FILE -Value $content -Encoding UTF8
}

function Get-ProjectFiles {
    $files = Get-ChildItem -Path "." -Recurse -File -Force | Where-Object {
        $_.FullName -notmatch "\\\.git\\"
    }
    
    $relativePaths = @()
    $currentDir = (Get-Location).Path
    
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($currentDir.Length + 1)
        $relativePaths += $relativePath
    }
    
    return $relativePaths
}

function Normalize-Path {
    param([string]$Path)
    
    # Remove any quotes that might have been escaped
    $Path = $Path.Trim('"')
    
    # Convert UNC forward slashes to backslashes
    if ($Path -match "^//(.+)") {
        $Path = "\\$($matches[1])"
    }
    
    # Remove trailing slashes/backslashes
    $Path = $Path.TrimEnd('\', '/')
    
    return $Path
}

function Find-DoomToolsProjects {
    param([string]$SearchPath)
    
    $projects = @()
    $directories = Get-ChildItem -Path $SearchPath -Recurse -Directory -ErrorAction SilentlyContinue
    
    foreach ($dir in $directories) {
        $hasAllFiles = $true
        foreach ($requiredFile in $DOOMTOOLS_REQUIRED_FILES) {
            $filePath = Join-Path $dir.FullName $requiredFile
            if (-not (Test-Path $filePath)) {
                $hasAllFiles = $false
                break
            }
        }
        
        if ($hasAllFiles) {
            $projects += $dir.FullName
        }
    }
    
    return $projects
}

function Update-DoomToolsIwadPaths {
    param([string[]]$ProjectPaths)
    
    if ($ProjectPaths.Count -eq 0) {
        return
    }
    
    Write-Host ""
    Write-Host "Updating IWAD paths in DoomTools projects..." -ForegroundColor Cyan
    
    $iwadPathFormatted = $IWAD_PATH -replace '\\', '/'
    
    foreach ($projectPath in $ProjectPaths) {
        $relativePath = $projectPath.Substring((Get-Location).Path.Length + 1)
        Write-Host "  Found DoomTools project: $relativePath" -ForegroundColor Gray
        
        $doomLoaderConf = Join-Path $projectPath "doom-loader.conf"
        if (Test-Path $doomLoaderConf) {
            try {
                $content = Get-Content $doomLoaderConf -Raw
                $content = $content -replace '(?m)^iwad\s*=\s*.+$', "iwad = $iwadPathFormatted"
                Set-Content -Path $doomLoaderConf -Value $content -NoNewline
                Write-Host "    Updated doom-loader.conf" -ForegroundColor Green
            }
            catch {
                Write-Host "    [ERROR] Failed to update doom-loader.conf" -ForegroundColor Red
            }
        }
        
        $doommakeProperties = Join-Path $projectPath "doommake.properties"
        if (Test-Path $doommakeProperties) {
            try {
                $content = Get-Content $doommakeProperties -Raw
                $content = $content -replace '(?m)^doommake\.iwad\s*=\s*.+$', "doommake.iwad=$iwadPathFormatted"
                Set-Content -Path $doommakeProperties -Value $content -NoNewline
                Write-Host "    Updated doommake.properties" -ForegroundColor Green
            }
            catch {
                Write-Host "    [ERROR] Failed to update doommake.properties" -ForegroundColor Red
            }
        }
    }
}

function Invoke-Backup {
    param(
        [string]$PathOverride = "",
        [string]$ForceOverride = "",
        [bool]$DumbCopy = $false,
        [bool]$CleanBackup = $false
    )
    
    $config = Read-Config
    $backupPath = ""
    $useDumbCopy = $DumbCopy
    
    # Determine backup path and mode
    if ($ForceOverride -ne "") {
        # -force specified: use it, enable dumb copy, ignore config
        $backupPath = Normalize-Path $ForceOverride
        $useDumbCopy = $true
        Write-Host "Using forced backup path (dumb copy mode): $backupPath" -ForegroundColor Yellow
    }
    elseif ($config -eq $null) {
        # No config exists
        if ($PathOverride -eq "") {
            Write-Host ""
            Write-Host "ERROR: No backup configuration found." -ForegroundColor Red
            Write-Host "You must specify a backup path using: dtbackup -path `"d:\path\to\backup`"" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        
        # -path specified: create config, do smart backup
        $backupPath = Normalize-Path $PathOverride
        Write-Host "Creating new backup configuration..." -ForegroundColor Cyan
    }
    else {
        # Config exists
        if ($PathOverride -ne "") {
            Write-Host ""
            Write-Host "ERROR: Backup path is already configured in $CONFIG_FILE" -ForegroundColor Red
            Write-Host "To use a different path, use: dtbackup -force `"d:\path\to\backup`"" -ForegroundColor Yellow
            Write-Host "To permanently change the path, edit or delete $CONFIG_FILE" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        
        $backupPath = $config.BackupPath
    }
    
    # Create backup directory if needed
    try {
        if (-not (Test-Path $backupPath)) {
            Write-Host "Creating backup directory: $backupPath" -ForegroundColor Cyan
            New-Item -Path $backupPath -ItemType Directory -Force | Out-Null
        }
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to create backup directory: $backupPath" -ForegroundColor Red
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "=== Project Backup ===" -ForegroundColor Green
    Write-Host "Backup Location: $backupPath" -ForegroundColor Cyan
    if ($useDumbCopy) {
        Write-Host "Mode: Dumb Copy (copy all files, update hashes)" -ForegroundColor Yellow
    }
    else {
        Write-Host "Mode: Smart Copy (skip unchanged files)" -ForegroundColor Cyan
    }
    Write-Host ""
    
    # Get all files
    $projectFiles = Get-ProjectFiles
    Write-Host "Found $($projectFiles.Count) files to process..." -ForegroundColor Cyan
    
    # Get empty directories
    $emptyDirs = Get-ChildItem -Path "." -Recurse -Directory -Force | Where-Object {
        $_.FullName -notmatch "\\\.git\\" -and (Get-ChildItem -Path $_.FullName -Force | Measure-Object).Count -eq 0
    }
    
    if ($emptyDirs.Count -gt 0) {
        Write-Host "Found $($emptyDirs.Count) empty directories to preserve..." -ForegroundColor Cyan
    }
    
    # Load existing hashes if doing smart copy
    $existingHashes = @{}
    if (-not $useDumbCopy -and $config -ne $null) {
        $existingHashes = $config.FileHashes
    }
    
    $newHashes = @{}
    $copiedCount = 0
    $skippedCount = 0
    $errorCount = 0
    $dirCount = 0
    
    # Create empty directories
    $currentDir = (Get-Location).Path
    foreach ($dir in $emptyDirs) {
        $relativePath = $dir.FullName.Substring($currentDir.Length + 1)
        $destDir = Join-Path $backupPath $relativePath
        
        if (-not (Test-Path $destDir)) {
            try {
                New-Item -Path $destDir -ItemType Directory -Force | Out-Null
                Write-Host "  [CREATED DIR] $relativePath" -ForegroundColor Cyan
                $dirCount++
            }
            catch {
                Write-Host "  [ERROR] Failed to create directory: $relativePath" -ForegroundColor Red
            }
        }
    }
    
    # Copy files
    foreach ($file in $projectFiles) {
        $sourcePath = Join-Path "." $file
        $destPath = Join-Path $backupPath $file
        
        # Calculate hash
        $currentHash = Get-FileHashMD5 -FilePath $sourcePath
        
        if ($currentHash -eq $null) {
            Write-Host "WARNING: Could not hash file: $file" -ForegroundColor Yellow
            $errorCount++
            continue
        }
        
        # Store hash for config update
        $newHashes[$file] = $currentHash
        
        # Determine if file needs copying
        $needsCopy = $true
        if (-not $useDumbCopy) {
            if ($existingHashes.ContainsKey($file)) {
                if ($existingHashes[$file] -eq $currentHash) {
                    $needsCopy = $false
                }
            }
        }
        
        if ($needsCopy) {
            # Ensure destination directory exists
            $destDir = Split-Path $destPath -Parent
            if ($destDir) {
                if (-not (Test-Path -LiteralPath $destDir)) {
                    try {
                        # Create directory using absolute path
                        $null = New-Item -ItemType Directory -Path $destDir -Force -ErrorAction Stop
                    }
                    catch {
                        Write-Host "  [ERROR] Failed to create directory for: $file" -ForegroundColor Red
                        Write-Host "          Directory: $destDir" -ForegroundColor Red
                        Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
                        $errorCount++
                        continue
                    }
                }
            }
            
            try {
                Copy-Item -LiteralPath $sourcePath -Destination $destPath -Force
                Write-Host "  [COPIED] $file" -ForegroundColor Green
                $copiedCount++
            }
            catch {
                Write-Host "  [ERROR] Failed to copy: $file" -ForegroundColor Red
                Write-Host "          Source: $sourcePath" -ForegroundColor Red
                Write-Host "          Dest: $destPath" -ForegroundColor Red
                Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
                $errorCount++
            }
        }
        else {
            Write-Host "  [SKIP] $file (unchanged)" -ForegroundColor DarkGray
            $skippedCount++
        }
    }
    
    # Update config file
    Write-Host ""
    Write-Host "Updating configuration file..." -ForegroundColor Cyan
    Write-Config -BackupPath $backupPath -FileHashes $newHashes
    
    # Clean backup directory if -clean flag is set
    if ($CleanBackup) {
        Write-Host ""
        Write-Host "Cleaning backup directory..." -ForegroundColor Yellow
        
        # Build list of source directories (including empty ones)
        $sourceDirs = @()
        $allSourceDirs = Get-ChildItem -Path "." -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
            $_.FullName -notmatch "\\\.git\\"
        }
        $currentDir = (Get-Location).Path
        foreach ($dir in $allSourceDirs) {
            $relativePath = $dir.FullName.Substring($currentDir.Length + 1)
            $sourceDirs += $relativePath
        }
        
        # Get all files in backup and delete those not in source
        $backupFiles = Get-ChildItem -LiteralPath $backupPath -Recurse -File -Force -ErrorAction SilentlyContinue
        $deletedCount = 0
        
        foreach ($file in $backupFiles) {
            $relativePath = $file.FullName.Substring($backupPath.Length + 1)
            
            # Check if this file exists in source
            if (-not $newHashes.ContainsKey($relativePath)) {
                try {
                    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                    Write-Host "  [DELETED] $relativePath" -ForegroundColor Red
                    $deletedCount++
                }
                catch {
                    Write-Host "  [ERROR] Failed to delete: $relativePath" -ForegroundColor Red
                    Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
                }
            }
        }
        
        # Get all directories in backup and delete those not in source
        $backupDirs = Get-ChildItem -LiteralPath $backupPath -Recurse -Directory -Force -ErrorAction SilentlyContinue | Sort-Object -Property FullName -Descending
        $deletedDirCount = 0
        
        foreach ($dir in $backupDirs) {
            $relativePath = $dir.FullName.Substring($backupPath.Length + 1)
            
            # Check if this directory exists in source
            if ($sourceDirs -notcontains $relativePath) {
                try {
                    Remove-Item -LiteralPath $dir.FullName -Recurse -Force -ErrorAction Stop
                    Write-Host "  [DELETED DIR] $relativePath" -ForegroundColor Red
                    $deletedDirCount++
                }
                catch {
                    Write-Host "  [ERROR] Failed to delete directory: $relativePath" -ForegroundColor Red
                }
            }
        }
        
        Write-Host ""
        Write-Host "Cleanup complete:" -ForegroundColor Yellow
        Write-Host "  Files deleted: $deletedCount" -ForegroundColor Red
        Write-Host "  Directories deleted: $deletedDirCount" -ForegroundColor Red
    }
    
    # Summary
    Write-Host ""
    Write-Host "=== Backup Complete ===" -ForegroundColor Green
    Write-Host "  Directories created: $dirCount" -ForegroundColor Cyan
    Write-Host "  Files copied: $copiedCount" -ForegroundColor Green
    Write-Host "  Files skipped: $skippedCount" -ForegroundColor Cyan
    if ($errorCount -gt 0) {
        Write-Host "  Errors: $errorCount" -ForegroundColor Red
    }
    Write-Host ""
}

function Invoke-Restore {
    param(
        [string]$RestorePath = "",
        [bool]$UseFresh = $false
    )
    
    # Check if current directory has content
    $currentFiles = Get-ChildItem -Path "." -File -ErrorAction SilentlyContinue
    $currentDirs = Get-ChildItem -Path "." -Directory -ErrorAction SilentlyContinue
    $hasContent = ($currentFiles.Count -gt 0) -or ($currentDirs.Count -gt 0)
    
    $backupPath = ""
    $doFreshRestore = $UseFresh
    
    if (-not $hasContent) {
        # Empty directory - must provide a path
        if ($RestorePath -eq "") {
            Write-Host ""
            Write-Host "ERROR: Current directory is empty." -ForegroundColor Red
            Write-Host "You must specify a backup path: dtbackup restore `"d:\path\to\backup`"" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        
        $backupPath = Normalize-Path $RestorePath
        $doFreshRestore = $true
    }
    else {
        # Directory has content
        if ($UseFresh) {
            # -fresh flag used
            if ($RestorePath -ne "") {
                # -fresh with path: clean + copy from specified path
                $backupPath = Normalize-Path $RestorePath
            }
            else {
                # -fresh without path: clean + copy from config
                $config = Read-Config
                if ($config -eq $null) {
                    Write-Host ""
                    Write-Host "ERROR: No backup configuration found ($CONFIG_FILE)" -ForegroundColor Red
                    Write-Host "Cannot use -fresh without path when no config exists." -ForegroundColor Yellow
                    Write-Host ""
                    exit 1
                }
                $backupPath = $config.BackupPath
            }
            $doFreshRestore = $true
        }
        else {
            # No -fresh: smart restore from config
            $config = Read-Config
            if ($config -eq $null) {
                Write-Host ""
                Write-Host "ERROR: No backup configuration found ($CONFIG_FILE)" -ForegroundColor Red
                Write-Host "Use -fresh to restore from a directory:" -ForegroundColor Yellow
                Write-Host "  dtbackup restore -fresh `"d:\path\to\backup`"" -ForegroundColor Yellow
                Write-Host ""
                exit 1
            }
            $backupPath = $config.BackupPath
            $doFreshRestore = $false
        }
    }
    
    # Verify backup directory exists
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Write-Host ""
        Write-Host "ERROR: Backup directory does not exist: $backupPath" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "=== Project Restore ===" -ForegroundColor Green
    Write-Host "Restore From: $backupPath" -ForegroundColor Cyan
    if ($doFreshRestore) {
        Write-Host "Mode: Fresh Restore (clean directory, copy all files)" -ForegroundColor Yellow
    }
    else {
        Write-Host "Mode: Smart Restore (skip unchanged files)" -ForegroundColor Cyan
    }
    Write-Host ""
    
    # Clean directory if using fresh mode
    if ($doFreshRestore -and $hasContent) {
        Write-Host "Cleaning current directory..." -ForegroundColor Yellow
        
        $itemsToDelete = Get-ChildItem -Path "." -Force | Where-Object { 
            $_.Name -ne "." -and $_.Name -ne ".." 
        }
        
        foreach ($item in $itemsToDelete) {
            try {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop
                Write-Host "  [DELETED] $($item.Name)" -ForegroundColor DarkGray
            }
            catch {
                Write-Host "  [ERROR] Failed to delete: $($item.Name)" -ForegroundColor Red
                Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        Write-Host ""
    }
    
    # Get backup files
    $backupFiles = Get-ChildItem -LiteralPath $backupPath -Recurse -File -Force -ErrorAction SilentlyContinue
    Write-Host "Found $($backupFiles.Count) files in backup..." -ForegroundColor Cyan
    
    # Get empty directories from backup
    $emptyDirs = Get-ChildItem -LiteralPath $backupPath -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
        (Get-ChildItem -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0
    }
    
    if ($emptyDirs.Count -gt 0) {
        Write-Host "Found $($emptyDirs.Count) empty directories in backup..." -ForegroundColor Cyan
    }
    
    # Calculate current file hashes if doing smart restore
    $currentHashes = @{}
    if (-not $doFreshRestore -and $hasContent) {
        Write-Host "Calculating hashes for current files..." -ForegroundColor Cyan
        $existingFiles = Get-ChildItem -Path "." -Recurse -File -Force -ErrorAction SilentlyContinue
        foreach ($file in $existingFiles) {
            $relativePath = $file.FullName.Substring((Get-Location).Path.Length + 1)
            $hash = Get-FileHashMD5 -FilePath $file.FullName
            if ($hash -ne $null) {
                $currentHashes[$relativePath] = $hash
            }
        }
    }
    
    $copiedCount = 0
    $skippedCount = 0
    $errorCount = 0
    $dirCount = 0
    
    # Create empty directories
    foreach ($dir in $emptyDirs) {
        $relativePath = $dir.FullName.Substring($backupPath.Length + 1)
        $destDir = Join-Path "." $relativePath
        
        if (-not (Test-Path -LiteralPath $destDir)) {
            try {
                New-Item -ItemType Directory -Path $destDir -Force -ErrorAction Stop | Out-Null
                Write-Host "  [CREATED DIR] $relativePath" -ForegroundColor Cyan
                $dirCount++
            }
            catch {
                Write-Host "  [ERROR] Failed to create directory: $relativePath" -ForegroundColor Red
            }
        }
    }
    
    # Copy files
    $ignoredFiles = @("doom-loader.conf", "doommake.properties")
    
    foreach ($file in $backupFiles) {
        $relativePath = $file.FullName.Substring($backupPath.Length + 1)
        $destPath = Join-Path "." $relativePath
        
        # Check if this is a file we should ignore hash differences for
        $fileName = Split-Path $relativePath -Leaf
        $ignoreHash = $ignoredFiles -contains $fileName
        
        # Determine if file needs copying
        $needsCopy = $true
        if (-not $doFreshRestore -and -not $ignoreHash) {
            # Smart restore - check hash (unless it's an ignored file)
            $backupHash = Get-FileHashMD5 -FilePath $file.FullName
            
            if ($backupHash -ne $null -and $currentHashes.ContainsKey($relativePath)) {
                if ($currentHashes[$relativePath] -eq $backupHash) {
                    $needsCopy = $false
                }
            }
        }
        
        if ($needsCopy) {
            # Ensure destination directory exists
            $destDir = Split-Path $destPath -Parent
            if ($destDir) {
                if (-not (Test-Path -LiteralPath $destDir)) {
                    try {
                        $null = New-Item -ItemType Directory -Path $destDir -Force -ErrorAction Stop
                    }
                    catch {
                        Write-Host "  [ERROR] Failed to create directory for: $relativePath" -ForegroundColor Red
                        Write-Host "          Directory: $destDir" -ForegroundColor Red
                        Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
                        $errorCount++
                        continue
                    }
                }
            }
            
            try {
                Copy-Item -LiteralPath $file.FullName -Destination $destPath -Force
                Write-Host "  [COPIED] $relativePath" -ForegroundColor Green
                $copiedCount++
            }
            catch {
                Write-Host "  [ERROR] Failed to copy: $relativePath" -ForegroundColor Red
                Write-Host "          $($_.Exception.Message)" -ForegroundColor Red
                $errorCount++
            }
        }
        else {
            Write-Host "  [SKIP] $relativePath (unchanged)" -ForegroundColor DarkGray
            $skippedCount++
        }
    }
    
    # Search for DoomTools projects and update IWAD paths
    $currentDir = (Get-Location).Path
    $doomToolsProjects = Find-DoomToolsProjects -SearchPath $currentDir
    Update-DoomToolsIwadPaths -ProjectPaths $doomToolsProjects
    
    # Summary
    Write-Host ""
    Write-Host "=== Restore Complete ===" -ForegroundColor Green
    Write-Host "  Directories created: $dirCount" -ForegroundColor Cyan
    Write-Host "  Files copied: $copiedCount" -ForegroundColor Green
    Write-Host "  Files skipped: $skippedCount" -ForegroundColor Cyan
    if ($doomToolsProjects.Count -gt 0) {
        Write-Host "  DoomTools projects updated: $($doomToolsProjects.Count)" -ForegroundColor Magenta
    }
    if ($errorCount -gt 0) {
        Write-Host "  Errors: $errorCount" -ForegroundColor Red
    }
    Write-Host ""
}

function Invoke-Verify {
    # Check for config file
    $config = Read-Config
    if ($config -eq $null) {
        Write-Host ""
        Write-Host "ERROR: No backup configuration found ($CONFIG_FILE)" -ForegroundColor Red
        Write-Host "Cannot verify without a backup configuration." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    $backupPath = $config.BackupPath
    
    # Check if backup directory exists
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Write-Host ""
        Write-Host "ERROR: Backup directory does not exist: $backupPath" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "=== Backup Verification ===" -ForegroundColor Green
    Write-Host "Local Directory: $(Get-Location)" -ForegroundColor Cyan
    Write-Host "Backup Directory: $backupPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Comparing files..." -ForegroundColor Cyan
    Write-Host ""
    
    # Get local files
    $localFiles = Get-ProjectFiles
    $localHashes = @{}
    
    Write-Host "Calculating hashes for local files..." -ForegroundColor Gray
    $fileCount = 0
    foreach ($file in $localFiles) {
        $fileCount++
        if ($fileCount % 50 -eq 0) {
            Write-Host "  Processed $fileCount / $($localFiles.Count) files..." -ForegroundColor DarkGray
        }
        $sourcePath = Join-Path "." $file
        $hash = Get-FileHashMD5 -FilePath $sourcePath
        if ($hash -ne $null) {
            $localHashes[$file] = $hash
        }
    }
    Write-Host "  Complete: $($localFiles.Count) files processed" -ForegroundColor DarkGray
    
    # Get backup files
    $backupFiles = @()
    $backupHashes = @{}
    
    Write-Host "Calculating hashes for backup files..." -ForegroundColor Gray
    $allBackupFiles = Get-ChildItem -LiteralPath $backupPath -Recurse -File -Force -ErrorAction SilentlyContinue
    $fileCount = 0
    foreach ($file in $allBackupFiles) {
        $fileCount++
        if ($fileCount % 50 -eq 0) {
            Write-Host "  Processed $fileCount files..." -ForegroundColor DarkGray
        }
        $relativePath = $file.FullName.Substring($backupPath.Length + 1)
        $backupFiles += $relativePath
        $hash = Get-FileHashMD5 -FilePath $file.FullName
        if ($hash -ne $null) {
            $backupHashes[$relativePath] = $hash
        }
    }
    Write-Host "  Complete: $fileCount files processed" -ForegroundColor DarkGray
    
    Write-Host ""
    
    # Compare files
    $matchCount = 0
    $mismatchCount = 0
    $localOnlyCount = 0
    $backupOnlyCount = 0
    $ignoredFiles = @("doom-loader.conf", "doommake.properties")
    
    # Check files in local
    foreach ($file in $localFiles) {
        # Check if this is a file we should ignore hash differences for
        $fileName = Split-Path $file -Leaf
        $ignoreHash = $ignoredFiles -contains $fileName
        
        if ($backupHashes.ContainsKey($file)) {
            if ($ignoreHash) {
                # Always count as matching for ignored files
                $matchCount++
            }
            elseif ($localHashes[$file] -eq $backupHashes[$file]) {
                $matchCount++
            }
            else {
                Write-Host "  [DIFFERENT] $file" -ForegroundColor Yellow
                $mismatchCount++
            }
        }
        else {
            Write-Host "  [LOCAL ONLY] $file" -ForegroundColor Cyan
            $localOnlyCount++
        }
    }
    
    # Check files only in backup
    foreach ($file in $backupFiles) {
        if (-not $localHashes.ContainsKey($file)) {
            Write-Host "  [BACKUP ONLY] $file" -ForegroundColor Magenta
            $backupOnlyCount++
        }
    }
    
    # Summary
    Write-Host ""
    Write-Host "=== Verification Summary ===" -ForegroundColor Green
    Write-Host "  Files matching: $matchCount" -ForegroundColor Green
    Write-Host "  Files different: $mismatchCount" -ForegroundColor Yellow
    Write-Host "  Files only in local: $localOnlyCount" -ForegroundColor Cyan
    Write-Host "  Files only in backup: $backupOnlyCount" -ForegroundColor Magenta
    Write-Host ""
    
    if ($mismatchCount -eq 0 -and $localOnlyCount -eq 0 -and $backupOnlyCount -eq 0) {
        Write-Host "Backup is synchronized!" -ForegroundColor Green
    }
    else {
        Write-Host "Backup is out of sync." -ForegroundColor Yellow
    }
    Write-Host ""
}

# Main entry point
if ($action -eq "help" -or $action -eq "-h" -or $action -eq "-help" -or $action -eq "--help") {
    Show-Help
}

switch ($action.ToLower()) {
    "backup" {
        Invoke-Backup -PathOverride $path -ForceOverride $force -DumbCopy $dumbcopy -CleanBackup $clean
    }
    "restore" {
        Invoke-Restore -RestorePath $restorepath -UseFresh $fresh
    }
    "verify" {
        Invoke-Verify
    }
    default {
        Write-Host "ERROR: Unknown action '$action'" -ForegroundColor Red
        Write-Host "Valid actions: backup, restore, verify, help" -ForegroundColor Yellow
        exit 1
    }
}