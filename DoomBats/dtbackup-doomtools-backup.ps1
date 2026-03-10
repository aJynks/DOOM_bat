#Requires -Version 5.1

param(
    [Parameter(Position=0)]
    [string]$action = "",
    
    [Parameter(Position=1)]
    [string]$restorepath = "",
    
    [Parameter()]
    [string]$path = "",
    
    [Parameter()]
    [string]$iwad = "",
    
    [Parameter()]
    [switch]$fresh,
    
    [Parameter()]
    [switch]$reset,
    
    [Parameter()]
    [switch]$local,
    
    [Parameter()]
    [switch]$server,
    
    [Parameter()]
    [switch]$v,
    
    [Parameter()]
    [switch]$h,
    
    [Parameter()]
    [switch]$helpfull
)

# ============================================================================
# IWAD CONFIGURATION
# ============================================================================
$IWAD_BASE_PATH = "d:\Projects\DoomProjects\_SourcePorts\_iwads"
$IWADS = @{
    "doom"     = "$IWAD_BASE_PATH\doom.wad"
    "doom2"    = "$IWAD_BASE_PATH\doom2.wad"
    "tnt"      = "$IWAD_BASE_PATH\tnt.wad"
    "plutonia" = "$IWAD_BASE_PATH\plutonia.wad"
    "heretic"  = "$IWAD_BASE_PATH\heretic.wad"
    "hexen"    = "$IWAD_BASE_PATH\hexen.wad"
    "free1"    = "$IWAD_BASE_PATH\freedoom1.wad"
    "free2"    = "$IWAD_BASE_PATH\freedoom2.wad"
}
$DEFAULT_IWAD = "doom2"
# ============================================================================

$CONFIG_FILE = ".doomProject_backup.conf"
$DOOMTOOLS_REQUIRED_FILES = @("doommake.properties", "doommake.project.properties", "doommake.script")

function Show-Help {
    Write-Host ""
    Write-Host "dtbackup v3 - Commands:" -ForegroundColor Cyan
    Write-Host "  dtbackup backup [-path <dir>] [-iwad <key>] [-reset] [-v]" -ForegroundColor White
    Write-Host "  dtbackup restore [-fresh] [<dir>]" -ForegroundColor White
    Write-Host "  dtbackup sync -local | -server" -ForegroundColor White
    Write-Host ""
    Write-Host "Use 'dtbackup -helpfull' for detailed options and examples" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

function Show-HelpFull {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Project Backup & Restore Utility v3" -ForegroundColor Cyan
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
    Write-Host "  sync                " -NoNewline -ForegroundColor Green
    Write-Host "Synchronize local and server (requires -local or -server)"
    Write-Host "  help                " -NoNewline -ForegroundColor Green
    Write-Host "Show this help message"
    Write-Host ""
    Write-Host "BACKUP OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -path <directory>   " -NoNewline -ForegroundColor Green
    Write-Host "Set backup directory (first-time backup only)"
    Write-Host "  -iwad <key>         " -NoNewline -ForegroundColor Green
    Write-Host "Select IWAD (doom, doom2, tnt, plutonia, heretic, hexen, free1, free2)"
    Write-Host "  -reset              " -NoNewline -ForegroundColor Green
    Write-Host "Delete backup directory contents before copying"
    Write-Host "  -v                  " -NoNewline -ForegroundColor Green
    Write-Host "Verbose mode - show all robocopy output"
    Write-Host ""
    Write-Host "RESTORE OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -fresh              " -NoNewline -ForegroundColor Green
    Write-Host "Clean directory, then restore from config path"
    Write-Host "  -fresh <directory>  " -NoNewline -ForegroundColor Green
    Write-Host "Clean directory, then restore from specified path"
    Write-Host "  <directory>         " -NoNewline -ForegroundColor Green
    Write-Host "Restore from path (empty directory only)"
    Write-Host ""
    Write-Host "SYNC OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -local              " -NoNewline -ForegroundColor Green
    Write-Host "Mirror local to server (backup)"
    Write-Host "  -server             " -NoNewline -ForegroundColor Green
    Write-Host "Mirror server to local (restore + clean)"
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  First-time backup:" -ForegroundColor Gray
    Write-Host "    dtbackup -path " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  First-time backup with TNT.WAD:" -ForegroundColor Gray
    Write-Host "    dtbackup -path " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -NoNewline -ForegroundColor Cyan
    Write-Host " -iwad tnt" -ForegroundColor White
    Write-Host ""
    Write-Host "  Subsequent backup (uses saved config):" -ForegroundColor Gray
    Write-Host "    dtbackup backup" -ForegroundColor White
    Write-Host ""
    Write-Host "  Backup with verbose output:" -ForegroundColor Gray
    Write-Host "    dtbackup backup -v" -ForegroundColor White
    Write-Host ""
    Write-Host "  Reset backup (delete and recopy everything):" -ForegroundColor Gray
    Write-Host "    dtbackup backup -reset" -ForegroundColor White
    Write-Host ""
    Write-Host "  Restore from saved config:" -ForegroundColor Gray
    Write-Host "    dtbackup restore -fresh" -ForegroundColor White
    Write-Host ""
    Write-Host "  Restore from specific path:" -ForegroundColor Gray
    Write-Host "    dtbackup restore -fresh " -NoNewline -ForegroundColor White
    Write-Host '"d:\Backups\MyProject"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Sync local to server (make backup match local):" -ForegroundColor Gray
    Write-Host "    dtbackup sync -local" -ForegroundColor White
    Write-Host ""
    Write-Host "  Sync server to local (make local match backup):" -ForegroundColor Gray
    Write-Host "    dtbackup sync -server" -ForegroundColor White
    Write-Host ""
    Write-Host "NOTES:" -ForegroundColor Yellow
    Write-Host "  - Backup mirrors source to destination (removes extra files)" -ForegroundColor Gray
    Write-Host "  - Empty directories are preserved" -ForegroundColor Gray
    Write-Host "  - IWAD paths automatically updated in DoomTools projects on restore" -ForegroundColor Gray
    Write-Host "  - Uses robocopy for reliable Windows file copying" -ForegroundColor Gray
    Write-Host "  - Excludes .git directories from backup/restore" -ForegroundColor Gray
    Write-Host ""
    Write-Host "CONFIG FILE:" -ForegroundColor Yellow
    Write-Host "  .doomProject_backup.conf" -ForegroundColor Cyan
    Write-Host "  - Stores backup path and IWAD selection" -ForegroundColor Gray
    Write-Host "  - Edit manually to change backup location permanently" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

function Read-Config {
    if (-not (Test-Path $CONFIG_FILE)) {
        return $null
    }
    
    $config = @{
        BackupPath = ""
        IwadKey = ""
    }
    
    $content = Get-Content $CONFIG_FILE -Raw
    $lines = $content -split "`r?`n"
    
    foreach ($line in $lines) {
        $line = $line.Trim()
        
        if ($line -eq "" -or $line.StartsWith("#")) {
            continue
        }
        
        if ($line.StartsWith("Path=")) {
            $config.BackupPath = $line.Substring(5).Trim()
        }
        elseif ($line.StartsWith("IwadKey=")) {
            $config.IwadKey = $line.Substring(8).Trim()
        }
    }
    
    return $config
}

function Write-Config {
    param(
        [string]$BackupPath,
        [string]$IwadKey
    )
    
    $content = @"
# Project Backup Configuration
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Path=$BackupPath
IwadKey=$IwadKey
"@
    
    Set-Content -Path $CONFIG_FILE -Value $content -Encoding UTF8
}

function Normalize-Path {
    param([string]$Path)
    
    $Path = $Path.Trim('"')
    
    # Convert UNC forward slashes to backslashes
    if ($Path -match "^//") {
        $Path = $Path -replace "^//", "\\"
        $Path = $Path -replace "/", "\"
    }
    
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
    param(
        [string[]]$ProjectPaths,
        [string]$IwadKey
    )
    
    if ($ProjectPaths.Count -eq 0) {
        return
    }
    
    if (-not $IWADS.ContainsKey($IwadKey)) {
        Write-Host ""
        Write-Host "WARNING: Invalid IWAD key '$IwadKey', using default" -ForegroundColor Yellow
        $IwadKey = $DEFAULT_IWAD
    }
    
    $iwadPath = $IWADS[$IwadKey]
    $iwadPathFormatted = $iwadPath -replace '\\', '/'
    
    Write-Host ""
    Write-Host "Updating IWAD paths in DoomTools projects..." -ForegroundColor Cyan
    Write-Host "  Using IWAD: $IwadKey ($iwadPathFormatted)" -ForegroundColor Gray
    
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

function Invoke-Sync {
    param(
        [bool]$SyncToLocal = $false,
        [bool]$SyncToServer = $false
    )
    
    if (-not $SyncToLocal -and -not $SyncToServer) {
        Write-Host ""
        Write-Host "ERROR: Must specify -local or -server for sync" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    if ($SyncToLocal -and $SyncToServer) {
        Write-Host ""
        Write-Host "ERROR: Cannot specify both -local and -server" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    $config = Read-Config
    if ($config -eq $null) {
        Write-Host ""
        Write-Host "ERROR: No backup configuration found ($CONFIG_FILE)" -ForegroundColor Red
        Write-Host "Run 'dtbackup backup -path <directory>' first" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    $backupPath = $config.BackupPath
    $currentDir = (Get-Location).Path
    
    if ($SyncToLocal) {
        Write-Host ""
        Write-Host "=== Sync to Local (Backup) ===" -ForegroundColor Green
        Write-Host "Mirroring: Local → Server" -ForegroundColor Cyan
        Write-Host "  Source: $currentDir" -ForegroundColor Gray
        Write-Host "  Destination: $backupPath" -ForegroundColor Gray
        Write-Host ""
        
        # This is the same as backup with /MIR
        & robocopy $currentDir $backupPath /MIR /E /COPY:DAT /R:3 /W:5 /XD .git
        $exitCode = $LASTEXITCODE
        
        if ($exitCode -ge 8) {
            Write-Host ""
            Write-Host "ERROR: Robocopy failed with exit code $exitCode" -ForegroundColor Red
            Write-Host ""
            exit 1
        }
        
        Write-Host ""
        Write-Host "Sync complete! Server now mirrors local." -ForegroundColor Green
        Write-Host ""
    }
    else {
        # Sync to server means: restore, then clean local
        Write-Host ""
        Write-Host "=== Sync to Server (Restore + Clean) ===" -ForegroundColor Green
        Write-Host "Step 1: Copying from server to local" -ForegroundColor Cyan
        Write-Host "  Source: $backupPath" -ForegroundColor Gray
        Write-Host "  Destination: $currentDir" -ForegroundColor Gray
        Write-Host ""
        
        # Restore files from server
        & robocopy $backupPath $currentDir /E /COPY:DAT /R:3 /W:5
        $exitCode = $LASTEXITCODE
        
        if ($exitCode -ge 8) {
            Write-Host ""
            Write-Host "ERROR: Robocopy failed with exit code $exitCode" -ForegroundColor Red
            Write-Host ""
            exit 1
        }
        
        Write-Host ""
        Write-Host "Step 2: Cleaning local (removing files not in server)" -ForegroundColor Yellow
        
        # Get all files/dirs in server
        $serverFiles = @{}
        $serverDirs = @()
        
        Get-ChildItem -LiteralPath $backupPath -Recurse -File -Force | ForEach-Object {
            $relativePath = $_.FullName.Substring($backupPath.Length + 1)
            $serverFiles[$relativePath] = $true
        }
        
        Get-ChildItem -LiteralPath $backupPath -Recurse -Directory -Force | ForEach-Object {
            $relativePath = $_.FullName.Substring($backupPath.Length + 1)
            $serverDirs += $relativePath
        }
        
        # Delete files in local not in server
        $deletedFiles = 0
        Get-ChildItem -Path $currentDir -Recurse -File -Force | ForEach-Object {
            $relativePath = $_.FullName.Substring($currentDir.Length + 1)
            if (-not $serverFiles.ContainsKey($relativePath)) {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-Host "  [DELETED FILE] $relativePath" -ForegroundColor Red
                $deletedFiles++
            }
        }
        
        # Delete directories in local not in server (bottom-up)
        $deletedDirs = 0
        Get-ChildItem -Path $currentDir -Recurse -Directory -Force | Sort-Object -Property FullName -Descending | ForEach-Object {
            $relativePath = $_.FullName.Substring($currentDir.Length + 1)
            if ($serverDirs -notcontains $relativePath) {
                if ((Get-ChildItem -LiteralPath $_.FullName -Force | Measure-Object).Count -eq 0) {
                    Remove-Item -LiteralPath $_.FullName -Force
                    Write-Host "  [DELETED DIR] $relativePath" -ForegroundColor Red
                    $deletedDirs++
                }
            }
        }
        
        Write-Host ""
        Write-Host "Cleanup complete:" -ForegroundColor Yellow
        Write-Host "  Files deleted: $deletedFiles" -ForegroundColor Red
        Write-Host "  Directories deleted: $deletedDirs" -ForegroundColor Red
        
        # Update IWAD paths
        if ($config.IwadKey -ne "") {
            $doomToolsProjects = Find-DoomToolsProjects -SearchPath $currentDir
            Update-DoomToolsIwadPaths -ProjectPaths $doomToolsProjects -IwadKey $config.IwadKey
        }
        
        Write-Host ""
        Write-Host "Sync complete! Local now mirrors server." -ForegroundColor Green
        Write-Host ""
    }
}

function Invoke-Backup {
    param(
        [string]$PathOverride = "",
        [string]$IwadSelection = "",
        [bool]$ShowVerbose = $false,
        [bool]$ResetBackup = $false
    )
    
    $config = Read-Config
    $backupPath = ""
    $iwadKey = ""
    
    # Determine IWAD
    if ($IwadSelection -ne "") {
        if ($IWADS.ContainsKey($IwadSelection.ToLower())) {
            $iwadKey = $IwadSelection.ToLower()
        }
        else {
            Write-Host ""
            Write-Host "ERROR: Unknown IWAD '$IwadSelection'" -ForegroundColor Red
            Write-Host "Valid options: $($IWADS.Keys -join ', ')" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
    }
    elseif ($config -ne $null -and $config.IwadKey -ne "") {
        $iwadKey = $config.IwadKey
    }
    else {
        $iwadKey = $DEFAULT_IWAD
    }
    
    # Determine backup path
    if ($config -eq $null) {
        if ($PathOverride -eq "") {
            Write-Host ""
            Write-Host "ERROR: No backup configuration found." -ForegroundColor Red
            Write-Host "You must specify a backup path using: dtbackup -path `"d:\path\to\backup`"" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        
        $backupPath = Normalize-Path $PathOverride
        Write-Host "Creating new backup configuration..." -ForegroundColor Cyan
        Write-Host "Using IWAD: $iwadKey" -ForegroundColor Cyan
    }
    else {
        $backupPath = $config.BackupPath
    }
    
    # Create backup directory if needed
    if (-not (Test-Path $backupPath)) {
        Write-Host "Creating backup directory: $backupPath" -ForegroundColor Cyan
        New-Item -Path $backupPath -ItemType Directory -Force | Out-Null
    }
    elseif ($ResetBackup) {
        Write-Host "Resetting backup directory (deleting all contents)..." -ForegroundColor Yellow
        Get-ChildItem -Path $backupPath -Force | Remove-Item -Recurse -Force
        Write-Host "Backup directory cleared." -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "=== Project Backup ===" -ForegroundColor Green
    Write-Host "Backup Location: $backupPath" -ForegroundColor Cyan
    if ($ResetBackup) {
        Write-Host "Mode: Reset (full clean and copy)" -ForegroundColor Yellow
    }
    Write-Host ""
    
    # Use robocopy to copy everything
    $currentDir = (Get-Location).Path
    
    Write-Host "Copying files with robocopy..." -ForegroundColor Cyan
    Write-Host "  Source: $currentDir" -ForegroundColor Gray
    Write-Host "  Destination: $backupPath" -ForegroundColor Gray
    Write-Host ""
    
    if ($ShowVerbose) {
        # Verbose mode - show all robocopy output
        & robocopy $currentDir $backupPath /MIR /E /COPY:DAT /R:3 /W:5 /XD .git
        $exitCode = $LASTEXITCODE
    }
    else {
        # Quiet mode - show progress bar
        $job = Start-Job -ScriptBlock {
            param($src, $dst)
            & robocopy $src $dst /MIR /E /COPY:DAT /R:3 /W:5 /XD .git /NFL /NDL /NJH /NJS
        } -ArgumentList $currentDir, $backupPath
        
        Write-Host "Copying files... " -NoNewline -ForegroundColor Cyan
        $spinner = @('|', '/', '-', '\')
        $i = 0
        
        while ($job.State -eq 'Running') {
            Write-Host "`r$($spinner[$i % 4]) Copying files... " -NoNewline -ForegroundColor Cyan
            Start-Sleep -Milliseconds 200
            $i++
        }
        
        $result = Receive-Job -Job $job
        $exitCode = $result | Select-Object -Last 1
        if ($exitCode -match "Exit Code : (\d+)") {
            $exitCode = [int]$matches[1]
        } else {
            # Try to get from job's output
            $exitCode = 0
        }
        
        Remove-Job -Job $job
        Write-Host "`rDone!                    " -ForegroundColor Green
    }
    
    # Robocopy exit codes: 0-7 are success, 8+ are errors
    if ($exitCode -ge 8) {
        Write-Host ""
        Write-Host "ERROR: Robocopy failed with exit code $exitCode" -ForegroundColor Red
        Write-Host "Exit code meanings:" -ForegroundColor Yellow
        Write-Host "  8  = Some files/dirs could not be copied" -ForegroundColor Yellow
        Write-Host "  16 = Serious error (no files copied)" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "Backup complete!" -ForegroundColor Green
    
    # Save config
    Write-Config -BackupPath $backupPath -IwadKey $iwadKey
    
    # Copy config file to backup
    $configSource = Join-Path "." $CONFIG_FILE
    $configDest = Join-Path $backupPath $CONFIG_FILE
    if (Test-Path -LiteralPath $configSource) {
        try {
            Copy-Item -LiteralPath $configSource -Destination $configDest -Force
            Write-Host "Copied configuration file to backup" -ForegroundColor Cyan
        }
        catch {
            Write-Host "WARNING: Failed to copy config file to backup" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
}

function Invoke-Restore {
    param(
        [string]$RestorePath = "",
        [bool]$UseFresh = $false
    )
    
    $hasContent = (Get-ChildItem -Path "." -Force | Measure-Object).Count -gt 0
    $backupPath = ""
    $config = $null
    
    # Determine restore path and mode
    if (-not $hasContent) {
        # Empty directory
        if ($RestorePath -eq "") {
            Write-Host ""
            Write-Host "ERROR: Current directory is empty." -ForegroundColor Red
            Write-Host "You must specify a backup path: dtbackup restore `"d:\path\to\backup`"" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        
        $backupPath = Normalize-Path $RestorePath
    }
    else {
        # Directory has content
        if ($UseFresh) {
            if ($RestorePath -ne "") {
                $backupPath = Normalize-Path $RestorePath
            }
            else {
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
            
            # Clean directory
            Write-Host ""
            Write-Host "Cleaning current directory..." -ForegroundColor Yellow
            Get-ChildItem -Path "." -Force | Remove-Item -Recurse -Force
        }
        else {
            Write-Host ""
            Write-Host "ERROR: Directory is not empty." -ForegroundColor Red
            Write-Host "Use -fresh to clean and restore:" -ForegroundColor Yellow
            Write-Host "  dtbackup restore -fresh" -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
    }
    
    if (-not (Test-Path $backupPath)) {
        Write-Host ""
        Write-Host "ERROR: Backup path does not exist: $backupPath" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "=== Project Restore ===" -ForegroundColor Green
    Write-Host "Restore Location: $backupPath" -ForegroundColor Cyan
    Write-Host ""
    
    # Use robocopy to restore everything
    $currentDir = (Get-Location).Path
    
    Write-Host "Restoring files with robocopy..." -ForegroundColor Cyan
    Write-Host ""
    
    # Run robocopy and let it output directly to console
    & robocopy $backupPath $currentDir /E /COPY:DAT /R:3 /W:5
    $exitCode = $LASTEXITCODE
    
    # Robocopy exit codes: 0-7 are success, 8+ are errors
    if ($exitCode -ge 8) {
        Write-Host ""
        Write-Host "ERROR: Robocopy failed with exit code $exitCode" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    
    Write-Host ""
    Write-Host "Restore complete!" -ForegroundColor Green
    
    # Update IWAD paths if config exists
    if ($config -eq $null) {
        $config = Read-Config
    }
    
    if ($config -ne $null -and $config.IwadKey -ne "") {
        $currentDir = (Get-Location).Path
        $doomToolsProjects = Find-DoomToolsProjects -SearchPath $currentDir
        Update-DoomToolsIwadPaths -ProjectPaths $doomToolsProjects -IwadKey $config.IwadKey
    }
    
    Write-Host ""
}

# Main script logic
if ($helpfull) {
    Show-HelpFull
}

if ($h) {
    Show-Help
}

if ($action -eq "") {
    Write-Host ""
    Write-Host "ERROR: No action specified." -ForegroundColor Red
    Write-Host "You must specify an action: backup, restore, sync, or help" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  dtbackup backup [-path <directory>] [-iwad <key>] [-reset] [-v]" -ForegroundColor White
    Write-Host "  dtbackup restore [-fresh] [<directory>]" -ForegroundColor White
    Write-Host "  dtbackup sync -local | -server" -ForegroundColor White
    Write-Host "  dtbackup help" -ForegroundColor White
    Write-Host ""
    Write-Host "Run 'dtbackup -h' for quick help or 'dtbackup -helpfull' for detailed help" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

switch ($action.ToLower()) {
    "backup" {
        Invoke-Backup -PathOverride $path -IwadSelection $iwad -ShowVerbose $v -ResetBackup $reset
    }
    "restore" {
        Invoke-Restore -RestorePath $restorepath -UseFresh $fresh
    }
    "sync" {
        Invoke-Sync -SyncToLocal $local -SyncToServer $server
    }
    "help" {
        Show-Help
    }
    default {
        Write-Host ""
        Write-Host "ERROR: Unknown action '$action'" -ForegroundColor Red
        Write-Host "Valid actions: backup, restore, sync, help" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}