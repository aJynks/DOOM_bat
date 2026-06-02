# ============================================================================
# doommake-tweak.ps1
# ============================================================================
# Tweaks a fresh DoomMake project to add custom build targets and functions
# ============================================================================

param(
    [string]$IwadPath = ""
)

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
# PRE-STEP: Resolve {{PROJECT_IWAD}} placeholder in doommake.properties
# ============================================================================
# doommake --project-type creates doommake.properties from a template that
# contains the literal placeholder {{PROJECT_IWAD}}. When piped via stdin the
# value may not be substituted. We accept the real IWAD path as an optional
# first argument and patch the file directly before running any doommake cmds.
#
# Usage: doommake-tweak.ps1 [-IwadPath "D:\path\to\doom2.wad"]

$propsPath = ".\doommake.properties"
if (Test-Path $propsPath) {
    $propsContent = Get-Content $propsPath -Raw

    if ($propsContent -match '\{\{PROJECT_IWAD\}\}') {
        # If no path was passed as a param, try to find it in the file itself
        # (some doommake versions write it correctly on a separate key)
        if (-not $IwadPath) {
            $iwadLine = (Get-Content $propsPath) | Where-Object { $_ -match '^\s*iwad\s*=' -and $_ -notmatch '\{\{' } | Select-Object -First 1
            if ($iwadLine) {
                $IwadPath = ($iwadLine -split '=', 2)[1].Trim()
            }
        }

        if ($IwadPath -and (Test-Path $IwadPath)) {
            Write-Host "  [Fixing] Replacing {{PROJECT_IWAD}} -> $IwadPath" -ForegroundColor Cyan
            $propsContent = $propsContent -replace '\{\{PROJECT_IWAD\}\}', ($IwadPath -replace '\\', '\\')
            [System.IO.File]::WriteAllText($propsPath, $propsContent, $utf8NoBom)
        } else {
            Write-Host "  [WARNING] {{PROJECT_IWAD}} placeholder found but no valid IWAD path available." -ForegroundColor Red
            Write-Host "            Pass it with: doommake-tweak.ps1 -IwadPath 'D:\path\to\doom2.wad'" -ForegroundColor Red
            Write-Host "            Continuing, but doommake steps may fail..." -ForegroundColor Yellow
        }
    }
}

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
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-palette.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"
Copy-FileTemplate -SourceFile "doommake-tweak-WADMERGE_merge-playpal-all.txt" -DestPath ".\scripts" -Prefix "WADMERGE_"

# ----------------------------------------------------------------------------
# FILE Templates - Copy to various locations
# ----------------------------------------------------------------------------
Copy-FileTemplate -SourceFile "doommake-tweak-FILE_COMPLVL.txt" -DestPath ".\src\assets\_global" -Prefix "FILE_"
Copy-FileTemplate -SourceFile "doommake-tweak-FILE_UMAPINFO.txt" -DestPath ".\src\assets\_global" -Prefix "FILE_"
Copy-FileTemplate -SourceFile "doommake-tweak-FILE_doom1-playpal.cube" -DestPath ".\" -Prefix "FILE_"

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
# STEP 7b: Remove doDist() from make entry target
# ============================================================================

Write-Host ""
Write-Host "STEP 7b: Removing doDist() from make entry target..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

$oldMake = "check entry make(args) {`r`n`tdoInit();`r`n`tdoAll();`r`n`tdoRelease();`r`n`tdoDist();`r`n}"
$newMake = "check entry make(args) {`r`n`tdoInit();`r`n`tdoAll();`r`n`tdoRelease();`r`n}"

if ($scriptContent -match [regex]::Escape($oldMake)) {
    $scriptContent = $scriptContent -replace [regex]::Escape($oldMake), $newMake
    [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
    Write-Host "  [Modified] Removed doDist() from make entry target" -ForegroundColor Green
} else {
    Write-Host "  [Skipped] doDist() not found in make entry target (already removed?)" -ForegroundColor Yellow
}

# ============================================================================
# STEP 7c: Add doDist() to release entry target
# ============================================================================

Write-Host ""
Write-Host "STEP 7c: Adding doDist() to release entry target..." -ForegroundColor Cyan

$scriptContent = Get-Content $scriptPath -Raw

$oldRelease = "check entry release(args) {`r`n`tdoInit();`r`n`tdoAll();`r`n`tdoRelease();`r`n}"
$newRelease = "check entry release(args) {`r`n`tdoInit();`r`n`tdoAll();`r`n`tdoRelease();`r`n`tdoDist();`r`n}"

if ($scriptContent -match [regex]::Escape($oldRelease)) {
    $scriptContent = $scriptContent -replace [regex]::Escape($oldRelease), $newRelease
    [System.IO.File]::WriteAllText($scriptPath, $scriptContent, $utf8NoBom)
    Write-Host "  [Modified] Added doDist() to release entry target" -ForegroundColor Green
} else {
    Write-Host "  [Skipped] release entry target not found in expected form (already modified?)" -ForegroundColor Yellow
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
Write-Host "DEFAULT targets:" -ForegroundColor White
Write-Host "  doommake all               - Build all project components (no release WAD)" -ForegroundColor Gray
Write-Host "  doommake assets            - Convert and merge assets WAD" -ForegroundColor Gray
Write-Host "  doommake clean             - Delete the build directory" -ForegroundColor Gray
Write-Host "  doommake convert           - Convert graphics, sprites, sounds and palettes" -ForegroundColor Gray
Write-Host "  doommake converttextures   - Convert texture flats and patches to Doom format" -ForegroundColor Gray
Write-Host "  doommake editor            - Rebuild the editor WAD" -ForegroundColor Gray
Write-Host "  doommake init              - Initialise the build directory" -ForegroundColor Gray
Write-Host "  doommake make              - Full build and create release WAD (no zip)" -ForegroundColor Gray
Write-Host "  doommake maps              - Merge the maps WAD" -ForegroundColor Gray
Write-Host "  doommake maptextures       - Export a WAD of only textures used in maps" -ForegroundColor Gray
Write-Host "  doommake patch             - Compile the DeHackEd patch and show budget" -ForegroundColor Gray
Write-Host "  doommake rebuildpalettes   - Rebuild primary palettes and colormaps" -ForegroundColor Gray
Write-Host "  doommake rebuildtextures   - Rebuild texture listings in src/textures" -ForegroundColor Gray
Write-Host "  doommake textures          - Convert and merge textures WAD" -ForegroundColor Gray
Write-Host ""
Write-Host "TWEAK targets:" -ForegroundColor White
Write-Host "  doommake deco              - Compile DECOHack and build a DEHACKED-only WAD" -ForegroundColor Yellow
Write-Host "  doommake fresh             - Clean build dir then do a full rebuild" -ForegroundColor Yellow
Write-Host "  doommake nopatch           - Full build and release WAD without DECOHack/DeHackEd" -ForegroundColor Yellow
Write-Host "  doommake playpal           - Convert palettes and colormaps into a palette-only WAD" -ForegroundColor Yellow
Write-Host "  doommake release           - Full build, create release WAD and zip for distribution" -ForegroundColor Yellow
Write-Host "  doommake texall            - Build texture WAD with ALL textures (for UDB)" -ForegroundColor Yellow
Write-Host "  doommake texrestricted     - Build texture WAD with only project textures (for UDB)" -ForegroundColor Yellow
Write-Host ""