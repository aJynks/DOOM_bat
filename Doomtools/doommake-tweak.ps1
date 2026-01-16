Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-FatalError {
  param (
    [Parameter(Mandatory)]
    [string] $Message
  )

  $text  = "-- ERROR : $Message --"
  $line  = '-' * $text.Length

  Write-Host $line -ForegroundColor Red
  Write-Host $text -ForegroundColor Red
  Write-Host $line -ForegroundColor Red
  exit 1
}

# ---------------------------------------------------------------------
# DoomMake project sanity check
# ---------------------------------------------------------------------

$requiredFiles = @(
  'doommake.project.properties',
  'doommake.script',
  'doommake.properties'
)

foreach ($file in $requiredFiles) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
    Write-FatalError "This tool must be run from inside the DoomMake root folder"
  }
}

$base = Get-Location

# ---------------------------------------------------------------------
# STEP 0: Read project name + update editor WAD name
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 0: Read DoomMake project name"
Write-Host "# -------------------------------------------"

$projectPropsPath = Join-Path $base "doommake.project.properties"
$projectName = $null

foreach ($line in Get-Content -LiteralPath $projectPropsPath) {
  if ($line -match '^\s*doommake\.project\.name\s*=\s*(.+)\s*$') {
    $projectName = $Matches[1].Trim()
    break
  }
}

if ([string]::IsNullOrWhiteSpace($projectName)) {
  Write-FatalError "Could not determine DoomMake project name"
}

Write-Host "Project Name   : $projectName" -ForegroundColor Green

$doommakePropsPath = Join-Path $base "doommake.properties"
$desiredValue = "${projectName}_UDB-editorAssets.wad"
$desiredLine  = "doommake.file.editor=$desiredValue"

$linesProps = Get-Content -LiteralPath $doommakePropsPath
$found = $false
$changed = $false

for ($i = 0; $i -lt $linesProps.Count; $i++) {
  if ($linesProps[$i] -match '^\s*doommake\.file\.editor\s*=\s*(.*)\s*$') {
    $found = $true
    if ($Matches[1].Trim() -ne $desiredValue) {
      $linesProps[$i] = $desiredLine
      $changed = $true
    }
    break
  }
}

if (-not $found) {
  Write-FatalError "doommake.file.editor entry not found in doommake.properties"
}

if ($changed) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($doommakePropsPath, $linesProps, $utf8NoBom)
  Write-Host "Updated        : Editor Assets WAD Name       : $desiredValue" -ForegroundColor Green
} else {
  Write-Host "Already Set    : Editor Assets WAD Name       : $desiredValue" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 1: Ensure ./src/wads/textures exists
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 1: Ensure ./src/wads/textures exists"
Write-Host "# -------------------------------------------"

$texturesDir = Join-Path $base "src/wads/textures"
$relativeTexturesDir = "./src/wads/textures"

if (-not (Test-Path -LiteralPath $texturesDir -PathType Container)) {
  New-Item -ItemType Directory -Path $texturesDir -Force | Out-Null
  Write-Host "Path Created   : Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor Green
} else {
  Write-Host "Already Present: Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 2: Ensure merge scripts exist (UTF-8 no BOM)
#   - ./scripts/merge-dehonly.txt
#   - ./scripts/merge-release-nopatch.txt
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 2: Ensure merge scripts exist (UTF-8 no BOM)"
Write-Host "# -------------------------------------------"

$scriptsDir = Join-Path $base "scripts"
if (-not (Test-Path -LiteralPath $scriptsDir -PathType Container)) {
  New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ---- merge-dehonly.txt ----
$mergeDehonlyPath = Join-Path $scriptsDir "merge-dehonly.txt"
$relativeMergeDehonly = "./scripts/merge-dehonly.txt"

if (-not (Test-Path -LiteralPath $mergeDehonlyPath -PathType Leaf)) {

  $mergeDehonlyContent = @"
# Create an in-memory buffer called OUT
CREATE OUT
# Import the .deh file from %2 (source dir) as lump name DEHACKED
MERGEFILE OUT ./build/dehacked.deh DEHACKED

# Write OUT to %1/dehonly.wad (build dir) and discard buffer
FINISH OUT ./build/dehacked.wad

END
"@

  [System.IO.File]::WriteAllText($mergeDehonlyPath, $mergeDehonlyContent, $utf8NoBom)
  Write-Host "File Created   : Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor Green
} else {
  Write-Host "Already Present: Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor DarkYellow
}

# ---- merge-release-nopatch.txt ----
$mergeReleaseNoPatchPath = Join-Path $scriptsDir "merge-release-nopatch.txt"
$relativeMergeReleaseNoPatch = "./scripts/merge-release-nopatch.txt"

if (-not (Test-Path -LiteralPath $mergeReleaseNoPatchPath -PathType Leaf)) {

  $mergeReleaseNoPatchContent = @"
# ===========================================================================
# WadMerge Script for Release (NO PATCH)
# ===========================================================================
#
# Argument 0: The build directory.
# Argument 1: The source directory.
# Argument 2: The output WAD.
#

create out
datemarker out __VER__

mergefile  out `$1/wadinfo.txt
mergefile  out `$1/credits.txt

mergewad   out `$0/`$3
mergewad   out `$0/`$4
mergewad   out `$0/`$5

finish out `$0/`$2
end
"@

  [System.IO.File]::WriteAllText($mergeReleaseNoPatchPath, $mergeReleaseNoPatchContent, $utf8NoBom)
  Write-Host "File Created   : Build Script for Release (NoPatch) : $relativeMergeReleaseNoPatch" -ForegroundColor Green
} else {
  Write-Host "Already Present: Build Script for Release (NoPatch) : $relativeMergeReleaseNoPatch" -ForegroundColor DarkYellow
}


# ---------------------------------------------------------------------
# STEP 3: Ensure doDehWad() exists in doommake.script (idempotent)
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 3: Ensure doDehWad() exists in doommake.script"
Write-Host "# -------------------------------------------"

$doommakeScriptPath = Join-Path $base "doommake.script"
$scriptLines = Get-Content -LiteralPath $doommakeScriptPath
$joined = $scriptLines -join "`n"

$decoFuncMarker1 = "/* This is the deco function */"
$decoFuncMarker2 = "/* Creates a WAD containing ONLY the DEHACKED lump */"

if ($joined -notlike ("*" + $decoFuncMarker1 + "*") -and
    $joined -notlike ("*" + $decoFuncMarker2 + "*")) {

  $insertIndex = -1
  for ($i = 0; $i -lt $scriptLines.Count; $i++) {
    if ($scriptLines[$i] -like "*Builds every component for the project release*") {
      $insertIndex = $i - 1
      break
    }
  }

  if ($insertIndex -lt 0) {
    Write-Host "WARNING       : Could not find doAll() doc block insertion point in doommake.script" -ForegroundColor Yellow
  } else {
    $decoFuncBlock = @(
      "/* ------------------------------------------------------------------------ */",
      "/* This is the deco function */",
      "/* Creates a WAD containing ONLY the DEHACKED lump */",
      "check function doDehWad() {",
      "",
      "    initBuild();",
      "",
      "    outWad = getBuildDirectory() + ""/dehacked.wad"";",
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
    if ($insertIndex -gt 0) { $newLines += $scriptLines[0..($insertIndex - 1)] }
    $newLines += $decoFuncBlock
    $newLines += $scriptLines[$insertIndex..($scriptLines.Count - 1)]

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($doommakeScriptPath, $newLines, $utf8NoBom)

    Write-Host "Inserted      : doDehWad() function to build DEHACKED.WAD" -ForegroundColor Green
  }

} else {
  Write-Host "Already Present: doDehWad() function to build DEHACKED.WAD" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 4: Ensure doDehWad() is called at the end of doAll() (idempotent)
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 4: Ensure doDehWad() is called by doAll()"
Write-Host "# -------------------------------------------"

# Re-read in case STEP 3 modified the file
$lines = @(Get-Content -LiteralPath $doommakeScriptPath)

# Find start of check function doAll() {
$startIndex = -1
for ($i = 0; $i -lt $lines.Length; $i++) {
  if ($lines[$i].Trim() -eq "check function doAll() {") {
    $startIndex = $i
    break
  }
}

if ($startIndex -lt 0) {
  Write-Host "WARNING       : Could not find check function doAll() in doommake.script; skipping doAll() patch" -ForegroundColor Yellow
} else {

  # Track brace depth to find closing } of this function
  $braceDepth = 0
  $endIndex = -1

  for ($i = $startIndex; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]

    # Regex brace counts are always safe under StrictMode
    $braceDepth += ([regex]::Matches($line, '\{')).Count
    $braceDepth -= ([regex]::Matches($line, '\}')).Count

    if ($i -gt $startIndex -and $braceDepth -eq 0) {
      $endIndex = $i
      break
    }
  }

  if ($endIndex -lt 0) {
    Write-Host "WARNING       : Could not find closing brace for doAll() function; skipping doAll() patch" -ForegroundColor Yellow
  } else {
    $functionBlock = $lines[$startIndex..$endIndex]

    # Robust check: exact call, ignoring whitespace
    $alreadyCalls = $false
    foreach ($l in $functionBlock) {
      if ($l -match '^\s*doDehWad\s*\(\s*\)\s*;\s*$') {
        $alreadyCalls = $true
        break
      }
    }

    if ($alreadyCalls) {
      Write-Host "Already Present: doDehWad() is being called by the doAll() function" -ForegroundColor DarkYellow
    } else {
      $callLine = "    doDehWad();"

      $newLines = @()
      if ($endIndex -gt 0) { $newLines += $lines[0..($endIndex - 1)] }
      $newLines += $callLine
      $newLines += $lines[$endIndex..($lines.Length - 1)]

      $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
      [System.IO.File]::WriteAllLines($doommakeScriptPath, $newLines, $utf8NoBom)

      Write-Host "Inserted      : doDehWad() as the last call of the doAll() function" -ForegroundColor Green
    }
  }
}

# ---------------------------------------------------------------------
# STEP 5: Append TARGET: deco at end if missing (idempotent)
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 5: Ensure TARGET: deco exists in doommake.script"
Write-Host "# -------------------------------------------"

# Re-read in case previous steps modified the file
$lines = @(Get-Content -LiteralPath $doommakeScriptPath)
$joined = $lines -join "`n"

# Marker: just look for the header line
if ($joined -notmatch '(?m)^\s*\*\s*TARGET:\s*deco\s*$') {

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

  $newLines = @()
  $newLines += $lines
  $newLines += $decoTargetBlock

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($doommakeScriptPath, $newLines, $utf8NoBom)

  Write-Host "Inserted      : DECO command to DoomMake (TARGET: deco)" -ForegroundColor Green
} else {
  Write-Host "Already Present: DECO command in DoomMake (TARGET: deco)" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 6: Append TARGET: fresh at end if missing (idempotent)
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 6: Ensure TARGET: fresh exists in doommake.script"
Write-Host "# -------------------------------------------"

# Re-read in case previous steps modified the file
$lines = @(Get-Content -LiteralPath $doommakeScriptPath)
$joined = $lines -join "`n"

# Marker: match the exact header line inside the big comment block
if ($joined -notmatch '(?m)^\s*\*\s*TARGET:\s*fresh\s*$') {

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
    "}",
    ""
  )

  $newLines = @()
  $newLines += $lines
  $newLines += $freshTargetBlock

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($doommakeScriptPath, $newLines, $utf8NoBom)

  Write-Host "Inserted      : FRESH command to DoomMake (TARGET: fresh)" -ForegroundColor Green
} else {
  Write-Host "Already Present: FRESH command in DoomMake (TARGET: fresh)" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 7: Ensure NoPatch support exists in doommake.script (idempotent)
#   - MERGESCRIPT_RELEASE_NOPATCH define
#   - doAllNoPatch()
#   - doReleaseNoPatch()
#   - TARGET: nopatch
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 7: Ensure NoPatch target support exists in doommake.script"
Write-Host "# -------------------------------------------"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Re-read current file
$lines = @(Get-Content -LiteralPath $doommakeScriptPath)
$joined = $lines -join "`n"
$modified = $false

# ---------- 7.1: Define MERGESCRIPT_RELEASE_NOPATCH ----------
if ($joined -match '(?m)^\s*#define\s+MERGESCRIPT_RELEASE_NOPATCH\s+"scripts/merge-release-nopatch\.txt"\s*$') {
  Write-Host "Already Present: MERGESCRIPT_RELEASE_NOPATCH define" -ForegroundColor DarkYellow
} else {
  $releaseDefineIndex = -1
  for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*#define\s+MERGESCRIPT_RELEASE\s+"scripts/merge-release\.txt"\s*$') {
      $releaseDefineIndex = $i
      break
    }
  }

  if ($releaseDefineIndex -lt 0) {
    Write-Host "WARNING       : Could not find MERGESCRIPT_RELEASE define; skipping nopatch define insert" -ForegroundColor Yellow
  } else {
    $insert = '#define MERGESCRIPT_RELEASE_NOPATCH "scripts/merge-release-nopatch.txt"'
    $newLines = @()
    if ($releaseDefineIndex -ge 0) { $newLines += $lines[0..$releaseDefineIndex] }
    $newLines += $insert
    if ($releaseDefineIndex + 1 -le $lines.Length - 1) { $newLines += $lines[($releaseDefineIndex + 1)..($lines.Length - 1)] }
    $lines = $newLines
    $joined = $lines -join "`n"
    $modified = $true
    Write-Host "Inserted      : MERGESCRIPT_RELEASE_NOPATCH define" -ForegroundColor Green
  }
}

# ---------- 7.2: Insert doAllNoPatch() ----------
if ($joined -match '(?m)^\s*check\s+function\s+doAllNoPatch\s*\(\s*\)\s*\{') {
  Write-Host "Already Present: doAllNoPatch() function" -ForegroundColor DarkYellow
} else {
  $doAllStart = -1
  $doAllEnd = -1
  for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*check\s+function\s+doAll\s*\(\s*\)\s*\{') { $doAllStart = $i; break }
  }

  if ($doAllStart -lt 0) {
    Write-Host "WARNING       : Could not find doAll(); skipping doAllNoPatch insert" -ForegroundColor Yellow
  } else {
    # find end brace of doAll() using regex brace depth
    $braceDepth = 0
    for ($i = $doAllStart; $i -lt $lines.Length; $i++) {
      $braceDepth += ([regex]::Matches($lines[$i], '\{')).Count
      $braceDepth -= ([regex]::Matches($lines[$i], '\}')).Count
      if ($i -gt $doAllStart -and $braceDepth -eq 0) { $doAllEnd = $i; break }
    }

    if ($doAllEnd -lt 0) {
      Write-Host "WARNING       : Could not find end of doAll(); skipping doAllNoPatch insert" -ForegroundColor Yellow
    } else {
      $block = @(
        "",
        "/**",
        " * Builds every component for the project release (NO PATCH).",
        " */",
        "check function doAllNoPatch() {",
        "    initBuild();",
        "    // doPatch(false);  // intentionally skipped",
        "    doConvertSounds();",
        "    doConvertGraphics();",
        "    doConvertSprites();",
        "    doConvertColormaps();",
        "    doAssets();",
        "    doConvertFlats();",
        "    doConvertPatches();",
        "    doConvertTextures();",
        "    doTextures();",
        "    doMaps();",
        "    doMapTextures();",
        "}",
        ""
      )

      $newLines = @()
      $newLines += $lines[0..$doAllEnd]
      $newLines += $block
      if ($doAllEnd + 1 -le $lines.Length - 1) { $newLines += $lines[($doAllEnd + 1)..($lines.Length - 1)] }
      $lines = $newLines
      $joined = $lines -join "`n"
      $modified = $true
      Write-Host "Inserted      : doAllNoPatch() function" -ForegroundColor Green
    }
  }
}

# ---------- 7.3: Insert doReleaseNoPatch() ----------
if ($joined -match '(?m)^\s*check\s+function\s+doReleaseNoPatch\s*\(\s*\)\s*\{') {
  Write-Host "Already Present: doReleaseNoPatch() function" -ForegroundColor DarkYellow
} else {
  $doRelStart = -1
  $doRelEnd = -1
  for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*check\s+function\s+doRelease\s*\(\s*\)\s*\{') { $doRelStart = $i; break }
  }

  if ($doRelStart -lt 0) {
    Write-Host "WARNING       : Could not find doRelease(); skipping doReleaseNoPatch insert" -ForegroundColor Yellow
  } else {
    $braceDepth = 0
    for ($i = $doRelStart; $i -lt $lines.Length; $i++) {
      $braceDepth += ([regex]::Matches($lines[$i], '\{')).Count
      $braceDepth -= ([regex]::Matches($lines[$i], '\}')).Count
      if ($i -gt $doRelStart -and $braceDepth -eq 0) { $doRelEnd = $i; break }
    }

    if ($doRelEnd -lt 0) {
      Write-Host "WARNING       : Could not find end of doRelease(); skipping doReleaseNoPatch insert" -ForegroundColor Yellow
    } else {
      $block = @(
        "",
        "/**",
        " * Merges all components into the project file and creates the distributable (NO PATCH).",
        " */",
        "check function doReleaseNoPatch() {",
        "",
        "    outFile = getBuildDirectory() + ""/"" + getProjectWAD();",
        "",
        "    // NOTE: do not include ""dehacked"" as a dependency here.",
        "    if (checkFileExistenceAndBuildStatuses(outFile, [""maps"", ""assets"", ""maptextures""])) {",
        "        println(""[Skipped] No pertinent project data built."");",
        "        return;",
        "    }",
        "",
        "    wadmerge(file(MERGESCRIPT_RELEASE_NOPATCH), [",
        "        getBuildDirectory()",
        "        ,getSourceDirectory()",
        "        ,getProjectWad()",
        "        ,getAssetsWAD()",
        "        ,getMapsWad()",
        "        ,getMapTexWad()",
        "    ]);",
        "    setBuilt(""release"");",
        "}",
        ""
      )

      $newLines = @()
      $newLines += $lines[0..$doRelEnd]
      $newLines += $block
      if ($doRelEnd + 1 -le $lines.Length - 1) { $newLines += $lines[($doRelEnd + 1)..($lines.Length - 1)] }
      $lines = $newLines
      $joined = $lines -join "`n"
      $modified = $true
      Write-Host "Inserted      : doReleaseNoPatch() function" -ForegroundColor Green
    }
  }
}

# ---------- 7.4: Insert TARGET: nopatch ----------
if ($joined -match '(?m)^\s*\*\s*TARGET:\s*nopatch\s*$') {
  Write-Host "Already Present: TARGET: nopatch" -ForegroundColor DarkYellow
} else {
  $makeTargetIndex = -1
  for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^\s*\*\s*TARGET:\s*make\s*$') {
      $makeTargetIndex = $i
      break
    }
  }

  $block = @(
    "",
    "/****************************************************************************",
    " * TARGET: nopatch",
    " ****************************************************************************",
    " * Builds and packages the project WITHOUT compiling/merging DeHackEd.",
    " * doommake nopatch",
    " ****************************************************************************/",
    "check entry nopatch(args) {",
    "    doInit();",
    "    doAllNoPatch();",
    "    doReleaseNoPatch();",
    "    doDist();",
    "}",
    ""
  )

  if ($makeTargetIndex -gt 0) {
    # Insert before the make target comment block (keep targets together)
    $insertAt = $makeTargetIndex - 1
    $newLines = @()
    if ($insertAt -gt 0) { $newLines += $lines[0..($insertAt - 1)] }
    $newLines += $block
    $newLines += $lines[$insertAt..($lines.Length - 1)]
    $lines = $newLines
    $joined = $lines -join "`n"
    $modified = $true
    Write-Host "Inserted      : TARGET: nopatch" -ForegroundColor Green
  } else {
    # Fall back: append
    $lines += $block
    $joined = $lines -join "`n"
    $modified = $true
    Write-Host "Inserted      : TARGET: nopatch (appended)" -ForegroundColor Green
  }
}

# ---------- Write back if anything changed ----------
if ($modified) {
  [System.IO.File]::WriteAllLines($doommakeScriptPath, $lines, $utf8NoBom)
}

# ---------------------------------------------------------------------
# Step : FINISHED
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------" -ForegroundColor Cyan
Write-Host ""

Write-Host "DoomMake project tweaks completed successfully." -ForegroundColor Green
Write-Host ""

Write-Host "New DoomMake Commands Available:" -ForegroundColor White
Write-Host ""

Write-Host "  fresh" -ForegroundColor Cyan
Write-Host "    Performs a full clean and complete rebuild of the project," -ForegroundColor Gray
Write-Host "    then creates the final release and distributable." -ForegroundColor Gray
Write-Host ""

Write-Host "  deco" -ForegroundColor Cyan
Write-Host "    Builds a WAD containing ONLY the DEHACKED lump," -ForegroundColor Gray
Write-Host "    intended for fast gameplay / DEH testing." -ForegroundColor Gray
Write-Host ""

Write-Host "  nopatch" -ForegroundColor Cyan
Write-Host "    Builds the entire project WITHOUT compiling or merging" -ForegroundColor Gray
Write-Host "    any DeHackEd patch into the final WAD." -ForegroundColor Gray
Write-Host ""

Write-Host "Default Build Changes:" -ForegroundColor White
Write-Host "  - DEHACKED.WAD generation has been added to the standard build pipeline." -ForegroundColor Green
Write-Host ""

Write-Host "# -------------------------------------------" -ForegroundColor Cyan
Write-Host "# doommake-tweak : FINISHED" -ForegroundColor Cyan
Write-Host "# -------------------------------------------" -ForegroundColor Cyan
Write-Host ""


exit 0
