# -------------------------------------------
# doomtools-tweak.ps1
# -------------------------------------------

# Use current working directory as project root
$base = Get-Location

# Path to doommake.script
$doommakePath = Join-Path $base "doommake.script"

# -------------------------------------------
# STEP 1: Ensure ./src/wads/textures exists
# -------------------------------------------

$texturesDir = Join-Path $base "src/wads/textures"
$relativeTexturesDir = "./src/wads/textures"

if (-not (Test-Path $texturesDir)) {
    New-Item -ItemType Directory -Path $texturesDir -Force | Out-Null
    Write-Host "Path Created : Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor Green
} else {
    Write-Host "Already Present : Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor DarkYellow
}

# -------------------------------------------
# STEP 2: Ensure ./scripts/merge-dehonly.txt exists (UTF-8 no BOM)
# -------------------------------------------

$scriptsDir = Join-Path $base "scripts"
$mergeDehonlyPath = Join-Path $scriptsDir "merge-dehonly.txt"
$relativeMergeDehonly = "./scripts/merge-dehonly.txt"

if (-not (Test-Path $mergeDehonlyPath)) {
    if (-not (Test-Path $scriptsDir)) {
        New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
    }

    $mergeDehonlyContent = @"
# Create an in-memory buffer called OUT
CREATE OUT
# Import the .deh file from %2 (source dir) as lump name DEHACKED
MERGEFILE OUT ./build/dehacked.deh DEHACKED

# Write OUT to %1/dehonly.wad (build dir) and discard buffer
FINISH OUT ./build/dehacked.wad

END
"@

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($mergeDehonlyPath, $mergeDehonlyContent, $utf8NoBom)
    Write-Host "File Created : Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor Green
} else {
    Write-Host "Already Present : Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor DarkYellow
}

# -------------------------------------------
# If doommake.script does not exist, stop here
# -------------------------------------------

if (-not (Test-Path $doommakePath)) {
    Write-Host "doommake.script not found in current directory; skipping script patches." -ForegroundColor Yellow
    return
}

# Load doommake.script as lines for in-memory editing
$lines = Get-Content -Path $doommakePath
$modified = $false

function Get-JoinedContent {
    param([string[]]$arr)
    return [string]::Join("`n", $arr)
}

# -------------------------------------------
# STEP 3: Insert doDehWad() function before doAll() doc block
#         but only if deco function header is not present
# -------------------------------------------

$joined = Get-JoinedContent -arr $lines

$decoFuncMarker1 = "/* This is the deco function */"
$decoFuncMarker2 = "/* Creates a WAD containing ONLY the DEHACKED lump */"

if ($joined -notlike "*" + $decoFuncMarker1 + "*" -and
    $joined -notlike "*" + $decoFuncMarker2 + "*") {

    # Find the "Builds every component for the project release" comment
    $insertIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -like "*Builds every component for the project release.*") {
            # We want to insert BEFORE the /** line which should be just above this
            $insertIndex = $i - 1
            break
        }
    }

    if ($insertIndex -lt 0) {
        Write-Host "WARNING: Could not find 'Builds every component for the project release' doc block in doommake.script." -ForegroundColor Yellow
    } else {
        $decoFuncBlock = @(
            "/* ------------------------------------------------------------------------ */",
            "/* This is the deco function */",
            "/* Creates a WAD containing ONLY the DEHACKED lump */",
            "check function doDehWad() {",
            "",
            "    initBuild();",
            "",
            "    outWad = getBuildDirectory() + ""/dehonly.wad"";",
            "",
            "    println(""Building DEH-only WAD: "" + outWad);",
            "",
            "    // Run WadMerge with our custom script.",
            "    // %1 = build dir, %2 = src dir (see merge-dehonly.txt below).",
            "    wadmerge(file(""scripts/merge-dehonly.txt""), [",
            "        getBuildDirectory(),",
            "        getSourceDirectory()",
            "    ]);",
            "",
            "    setBuilt(""dehonly"");",
            "}",
            ""
        )

        $newLines = @()

        if ($insertIndex -gt 0) {
            $newLines += $lines[0..($insertIndex - 1)]
        }

        $newLines += $decoFuncBlock
        $newLines += $lines[$insertIndex..($lines.Count - 1)]

        $lines = $newLines
        $modified = $true
        Write-Host "Inserted : doDehWad() function to build DEHACKED.WAD." -ForegroundColor Green
    }
} else {
    Write-Host "Already Present : doDehWad() function to build DEHACKED.WAD" -ForegroundColor DarkYellow
}

# -------------------------------------------
# STEP 4: Ensure doDehWad() is called at the end of doAll()
#         but only if doDehWad(); is not already inside that function
# -------------------------------------------

$joined = Get-JoinedContent -arr $lines

# Find start of check function doAll() {
$startIndex = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq "check function doAll() {") {
        $startIndex = $i
        break
    }
}

if ($startIndex -lt 0) {
    Write-Host "Could not find check function doAll() in doommake.script; skipping doAll() patch." -ForegroundColor Yellow
} else {
    # Track brace depth to find closing } of this function
    $braceDepth = 0
    $endIndex = -1

    for ($i = $startIndex; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        $braceDepth += ($line.ToCharArray() | Where-Object { $_ -eq '{' }).Count
        $braceDepth -= ($line.ToCharArray() | Where-Object { $_ -eq '}' }).Count

        if ($i -gt $startIndex -and $braceDepth -eq 0) {
            $endIndex = $i
            break
        }
    }

    if ($endIndex -lt 0) {
        Write-Host "ERROR: Could not find closing brace for doAll() function." -ForegroundColor Red
    } else {
        $functionBlock = $lines[$startIndex..$endIndex]

        if ($functionBlock -like "*doDehWad();*") {
            Write-Host "Already Present : doDehWad() is beng called by the doAll() function." -ForegroundColor DarkYellow
        } else {
            $callLine = "    doDehWad();"

            $newLines = @()

            if ($endIndex -gt 0) {
                $newLines += $lines[0..($endIndex - 1)]
            }

            $newLines += $callLine
            $newLines += $lines[$endIndex..($lines.Count - 1)]

            $lines = $newLines
            $modified = $true
            Write-Host "Inserted : doDehWad() as the last call of the doAll() function." -ForegroundColor Green
        }
    }
}

# -------------------------------------------
# STEP 5: Append deco target at end if missing
# -------------------------------------------

$joined = Get-JoinedContent -arr $lines

$decoTargetMarker = "* TARGET: deco"

if ($joined -notlike "*" + $decoTargetMarker + "*") {
    $decoTargetBlock = @(
        "",
        "/****************************************************************************",
        " * TARGET: deco",
        " ****************************************************************************",
        " * Creates a WAD containing only the DEHACKED lump.",
        " * doommake deco",
        " ****************************************************************************/",
        "check entry deco(args) {",
		"    doPatch(false);",
        "    doDehWad();",
        "}"
    )

    $lines += $decoTargetBlock
    $modified = $true
    Write-Host "Inserted : DECO command to doommake." -ForegroundColor Green
} else {
    Write-Host "Already Present : DECO command in doommake." -ForegroundColor DarkYellow
}

# -------------------------------------------
# STEP 6: Append fresh target at end if missing
# -------------------------------------------

$joined = Get-JoinedContent -arr $lines

$freshTargetMarker = "* TARGET: fresh"

if ($joined -notlike "*" + $freshTargetMarker + "*") {
    $freshTargetBlock = @(
        "",
        "/****************************************************************************",
        " * TARGET: fresh",
        " ****************************************************************************",
        " * CLEANS the ./build dir, and then runs MAKE for the entire project",
        " * doommake fresh",
        " ****************************************************************************/",
        "check entry fresh(args) {",
        "    doClean();",
        "    doInit();",
        "    doAll();",
        "    doRelease();",
        "    doDist();",
        "}"
    )

    $lines += $freshTargetBlock
    $modified = $true
    Write-Host "Inserted : FRESH command to doommake." -ForegroundColor Green
} else {
    Write-Host "Already Present : FRESH command in doommake." -ForegroundColor DarkYellow
}

# -------------------------------------------
# FINAL OUTPUT STATUS
# -------------------------------------------

Write-Host ""   # Blank line before status block

if ($modified) {

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($doommakePath, $lines, $utf8NoBom)

    Write-Host "-----------------------------------------------" -ForegroundColor Yellow
    Write-Host "-- Doom Tweak Scripts and Dirs Applied" -ForegroundColor Yellow
    Write-Host "-----------------------------------------------" -ForegroundColor Yellow
    Write-Host ""  # spacing

} else {

    Write-Host "-----------------------------------------------" -ForegroundColor Magenta
    Write-Host "-- No Changes Needed" -ForegroundColor Magenta
    Write-Host "-----------------------------------------------" -ForegroundColor Magenta
    Write-Host ""  # spacing
}

