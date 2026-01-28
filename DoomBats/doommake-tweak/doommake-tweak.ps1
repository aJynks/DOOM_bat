# ============================================================================
# doommake-tweak.ps1
# ============================================================================
# Tweaks a fresh DoomMake project to add custom build targets and functions
# ============================================================================

$ErrorActionPreference = "Stop"
$base = Get-Location

Write-Host ""
Write-Host "==============================================="
Write-Host "=== DoomMake Project Tweaker for MBF21 Wads ==="
Write-Host "==============================================="
Write-Host ""

# Validate we're in a DoomMake project
if (!(Test-Path "doommake.script")) {
    Write-Host "ERROR: doommake.script not found. Are you in a DoomMake project root?" -ForegroundColor Red
    exit 1
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ============================================================================
# STEP 1: Create Directories
# ============================================================================

Write-Host "STEP 1: Creating directories..." -ForegroundColor Cyan

# Create textureX directory
$textureXDir = ".\scripts\textureX"
if (!(Test-Path $textureXDir)) {
    New-Item -ItemType Directory -Path $textureXDir -Force | Out-Null
    Write-Host "  [Created Dir] $textureXDir" -ForegroundColor Green
} else {
    Write-Host "  [Dir Exists]  $textureXDir" -ForegroundColor Yellow
}

# ============================================================================
# STEP 2: Copy File Templates
# ============================================================================

Write-Host ""
Write-Host "STEP 2: Creating files from templates..." -ForegroundColor Cyan

# Function to copy file templates
function Copy-FileTemplate {
    param(
        [string]$SourceFile,
        [string]$DestPath,
        [string]$Prefix
    )
    
    $DestFilename = $SourceFile -replace "doommake-tweak-$Prefix", ""
    $SourcePath = Join-Path $PSScriptRoot $SourceFile
    $DestFullPath = Join-Path $DestPath $DestFilename
    
    if (Test-Path $SourcePath) {
        Copy-Item $SourcePath $DestFullPath -Force
        if (Test-Path $DestFullPath) {
            Write-Host "  [File Created] $DestFullPath" -ForegroundColor Green
        }
    } else {
        Write-Host "  [WARNING] Template not found: $SourceFile" -ForegroundColor Red
    }
}

# ----------------------------------------------------------------------------
# WADMERGE Scripts - Copy to .\scripts\
# ----------------------------------------------------------------------------
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-dehonly.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-release-nopatch.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-textures-All.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-textures-Restricted.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"

# ----------------------------------------------------------------------------
# FILE Templates - Copy to various locations
# ----------------------------------------------------------------------------
Copy-FileTemplate -SourceFile "doommake-tweak-FILE_COMPLVL.txt" -DestPath ".\src\assets\_global" -Prefix "FILE_"
Copy-FileTemplate -SourceFile "doommake-tweak-FILE_UMAPINFO.txt" -DestPath ".\src\assets\_global" -Prefix "FILE_"

# ----------------------------------------------------------------------------
# DECO Templates - Copy to .\src\decohack\
# ----------------------------------------------------------------------------
Copy-FileTemplate -SourceFile "doommake-tweak-DECO_main.dh" -DestPath ".\src\decohack" -Prefix "DECO_"
Copy-FileTemplate -SourceFile "doommake-tweak-DECO_strings.dh" -DestPath ".\src\decohack" -Prefix "DECO_"

# ============================================================================
# STEP 3: Create Texture Variants
# ============================================================================

Write-Host ""
Write-Host "STEP 3: Creating All / Restricted UDB Texture WADs..." -ForegroundColor Cyan

$sourceTexture1 = ".\src\textures\texture1.txt"
$restrictedBackup = ".\scripts\textureX\texture1-Restricted.txt"
$allBackup = ".\scripts\textureX\texture1-All.txt"
$doom2DefaultBackup = ".\scripts\textureX\texture1-doom2Default.txt"

if (Test-Path $sourceTexture1) {
    # Backup original as Restricted
    if (!(Test-Path $restrictedBackup)) {
        Copy-Item $sourceTexture1 $restrictedBackup -Force
        Write-Host "  [File Created] texture1-Restricted.txt" -ForegroundColor Green
    } else {
        Write-Host "  [File Exists]  texture1-Restricted.txt" -ForegroundColor Yellow
    }
    
    # Delete original
    Remove-Item $sourceTexture1
    
    # Run rebuildtextures if All doesn't exist
    if (!(Test-Path $allBackup)) {
        Write-Host "  [Running] doommake rebuildtextures..." -ForegroundColor Cyan
        & doommake rebuildtextures | Out-Null
        
        if (Test-Path $sourceTexture1) {
            # Copy rebuilt to All
            Copy-Item $sourceTexture1 $allBackup -Force
            Write-Host "  [File Created] texture1-All.txt" -ForegroundColor Green
            
            # Copy to doom2Default
            Copy-Item $sourceTexture1 $doom2DefaultBackup -Force
            Write-Host "  [File Created] texture1-doom2Default.txt" -ForegroundColor Green
            
            # Restore Restricted
            Copy-Item $restrictedBackup $sourceTexture1 -Force
            Write-Host "  [Restored] texture1-Restricted.txt -> texture1.txt" -ForegroundColor Green
        }
    } else {
        Write-Host "  [File Exists]  texture1-All.txt (skipping rebuild)" -ForegroundColor Yellow
        # Still restore Restricted
        Copy-Item $restrictedBackup $sourceTexture1 -Force
        Write-Host "  [Restored] texture1-Restricted.txt -> texture1.txt" -ForegroundColor Green
    }
}

# ============================================================================
# STEP 4: Append Build Targets to doommake.script
# ============================================================================

Write-Host ""
Write-Host "STEP 4: Adding build targets..." -ForegroundColor Cyan

$scriptPath = ".\doommake.script"
$scriptContent = Get-Content $scriptPath -Raw

# ----------------------------------------------------------------------------
# FUNC: Build Targets
# ----------------------------------------------------------------------------
$buildTargetsFile = Join-Path $PSScriptRoot "doommake-tweak_FUNC_BuildTargets.conf"
if (Test-Path $buildTargetsFile) {
    $newTargets = Get-Content $buildTargetsFile -Raw
    
    # Check if already added
    if ($scriptContent -notmatch 'TARGET: nopatch') {
        $scriptContent += $newTargets
        [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
        Write-Host "  [Added] New build targets" -ForegroundColor Green
    } else {
        Write-Host "  [Exists] Build targets already present" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Config file not found: doommake-tweak_FUNC_BuildTargets.conf" -ForegroundColor Red
}

# ============================================================================
# STEP 5: Insert New Functions
# ============================================================================

Write-Host ""
Write-Host "STEP 5: Adding new check functions..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

# ----------------------------------------------------------------------------
# FUNC: Check Functions
# ----------------------------------------------------------------------------
$functionsFile = Join-Path $PSScriptRoot "doommake-tweak_FUNC_checkFunctions.conf"
if (Test-Path $functionsFile) {
    $newFunctions = Get-Content $functionsFile -Raw
    
    # Check if already added
    if ($scriptContent -notmatch 'function doDehWad') {
        # Find the marker comment and doAll() function
        $marker = '/\*\*\s+\*\s+Builds every component for the project release\.\s+\*/\s+check function doAll\(\) \{'
        
        if ($scriptContent -match $marker) {
            # Insert the entire functions file ABOVE this marker
            $scriptContent = $scriptContent -replace "($marker)", "$newFunctions`r`n`$1"
            [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
            Write-Host "  [Added] New check functions" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] Could not find insertion point" -ForegroundColor Red
        }
    } else {
        Write-Host "  [Exists] Functions already present" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Config file not found: doommake-tweak_FUNC_checkFunctions.conf" -ForegroundColor Red
}

# ============================================================================
# STEP 6: Modify doAll() Function
# ============================================================================

Write-Host ""
Write-Host "STEP 6: Modifying doAll() function..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

# ----------------------------------------------------------------------------
# FUNC: doAll() Additions
# ----------------------------------------------------------------------------
$doAllAdditionsFile = Join-Path $PSScriptRoot "doommake-tweak_FUNC_doAll-edits.conf"
if (Test-Path $doAllAdditionsFile) {
    $doAllAdditions = Get-Content $doAllAdditionsFile -Raw
    
    # Extract just the doAll() function to check if already modified
    if ($scriptContent -match '(?s)(check function doAll\(\) \{.*?\n\})') {
        $doAllFunction = $matches[1]
        
        # Check if doAll() already contains the additions (check within the function itself)
        if ($doAllFunction -notmatch '// -- doommake-TWEAK-additions') {
            # Find doAll() function and insert additions before closing brace
            $doAllBody = $doAllFunction.Substring(0, $doAllFunction.LastIndexOf('}'))
            $newDoAll = $doAllBody + "`r`n" + $doAllAdditions + "`r`n}"
            
            # Replace in script
            $scriptContent = $scriptContent -replace [regex]::Escape($doAllFunction), $newDoAll
            [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
            Write-Host "  [Modified] doAll() function" -ForegroundColor Green
        } else {
            Write-Host "  [Exists] doAll() already modified" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [ERROR] Could not find doAll() function" -ForegroundColor Red
    }
} else {
    Write-Host "  [ERROR] Config file not found: doommake-tweak_FUNC_doAll-edits.conf" -ForegroundColor Red
}

# ============================================================================
# STEP 7: Create doAllNoPatch() Function
# ============================================================================

Write-Host ""
Write-Host "STEP 7: Creating doAllNoPatch() function..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

# Check if already exists
if ($scriptContent -notmatch 'function doAllNoPatch') {
    # Find the modified doAll() function
    if ($scriptContent -match '(?s)(check function doAll\(\) \{[^\}]*\})') {
        $doAllFunction = $matches[1]
        
        # Create doAllNoPatch version
        $doAllNoPatchFunction = $doAllFunction -replace 'check function doAll\(\)', 'check function doAllNoPatch()'
        $doAllNoPatchFunction = $doAllNoPatchFunction -replace '(\s+)doPatch\(false\);', '$1// doPatch(false); // - removed by Tweak'
        
        # Find where doAll() ends and insert doAllNoPatch after it
        $insertAfter = [regex]::Escape($doAllFunction)
        $scriptContent = $scriptContent -replace "($insertAfter)", "`$1`r`n`r`n$doAllNoPatchFunction"
        
        [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
        Write-Host "  [Created] doAllNoPatch() function" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] Could not find doAll() function to copy" -ForegroundColor Red
    }
} else {
    Write-Host "  [Exists] doAllNoPatch() already present" -ForegroundColor Yellow
}

# ============================================================================
# STEP 8: Initialize Project
# ============================================================================

Write-Host ""
Write-Host "STEP 8: Initializing blank project..." -ForegroundColor Cyan
Write-Host "  [Running] doommake make" -ForegroundColor Green
Write-Host ""

& doommake make
if ($LASTEXITCODE -ne 0) {
    throw "doommake make failed with exit code $LASTEXITCODE"
}

# ============================================================================
# DONE
# ============================================================================

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkCyan
Write-Host "== Tweak Complete! =======================" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "New build targets available:" -ForegroundColor White
Write-Host "  - doommake deco               (build a dehacked-only WAD)" -ForegroundColor Yellow
Write-Host "  - doommake fresh              (clean the build dir + then a full rebuild)" -ForegroundColor Yellow
Write-Host "  - doommake nopatch            (build Full Release with no DeHackEd)" -ForegroundColor Yellow
Write-Host "  - doommake texturesrestricted (build a restricted texture wad for UDB)" -ForegroundColor Yellow
Write-Host "  - doommake texturesall        (build a full texture wad for UDB, that can run previews)" -ForegroundColor Yellow
Write-Host ""