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
# STEP 1: Ensure required directories exist
#   - ./src/wads/textures
#   - ./src/convert/colormap-primary
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 1: Ensure required directories exist"
Write-Host "# -------------------------------------------"

# ---- textures ----
$texturesDir = Join-Path $base "src/wads/textures"
$relativeTexturesDir = "./src/wads/textures"

if (-not (Test-Path -LiteralPath $texturesDir -PathType Container)) {
  New-Item -ItemType Directory -Path $texturesDir -Force | Out-Null
  Write-Host "Path Created   : Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor Green
} else {
  Write-Host "Already Present: Path for Texture Wad Extraction : $relativeTexturesDir" -ForegroundColor DarkYellow
}

# ---- primary colormap ----
$colormapPrimaryDir = Join-Path $base "src/convert/colormap-primary"
$relativeColormapPrimaryDir = "./src/convert/colormap-primary"

if (-not (Test-Path -LiteralPath $colormapPrimaryDir -PathType Container)) {
  New-Item -ItemType Directory -Path $colormapPrimaryDir -Force | Out-Null
  Write-Host "Path Created   : Path for Primary Colormap      : $relativeColormapPrimaryDir" -ForegroundColor Green
} else {
  Write-Host "Already Present: Path for Primary Colormap      : $relativeColormapPrimaryDir" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 2: Ensure merge scripts exist (UTF-8 no BOM)
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
CREATE OUT
MERGEFILE OUT ./build/dehacked.deh DEHACKED
FINISH OUT ./build/dehacked.wad
END
"@

  [System.IO.File]::WriteAllText($mergeDehonlyPath, $mergeDehonlyContent, $utf8NoBom)
  Write-Host "File Created   : Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor Green
} else {
  Write-Host "Already Present: Build Script for DEHACKED.WAD : $relativeMergeDehonly" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------------
# STEP 3: Insert primaryColormap() function (idempotent)
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 3: Ensure primaryColormap() exists in doommake.script"
Write-Host "# -------------------------------------------"

$doommakeScriptPath = Join-Path $base "doommake.script"
$lines = Get-Content -LiteralPath $doommakeScriptPath
$joined = $lines -join "`n"

if ($joined -match '(?m)^\s*check\s+function\s+primaryColormap\s*\(') {
  Write-Host "Already Present: primaryColormap() function" -ForegroundColor DarkYellow
} else {
  $insertIndex = -1
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*/\*\*\s*$' -and
        $lines[$i + 1] -match '^\s*\*\s*Builds every component for the project release\.\s*$') {
      $insertIndex = $i
      break
    }
  }

  if ($insertIndex -lt 0) {
    Write-Host "WARNING       : Could not find insertion point for primaryColormap()" -ForegroundColor Yellow
  } else {
    $block = @(
      "/* ------------------------------------------------------------------------ */",
      "/* PRIMARY COLORMAP (PLAYPAL optional; fallback to default conversion palette) */",
      "/* ------------------------------------------------------------------------ */",
      "",
      "#define SRC_DIR_COLORMAP_PRIMARY ""/convert/colormap-primary""",
      "#define SRC_DIR_GLOBAL_ASSETS    ""/assets/_global""",
      "",
      "check function primaryColormap() {",
      "",
      "    colormapDir = getSourceDirectory() + SRC_DIR_COLORMAP_PRIMARY;",
      "    globalDir   = getSourceDirectory() + SRC_DIR_GLOBAL_ASSETS;",
      "",
      "    verifydirs(colormapDir);",
      "    verifydirs(globalDir);",
      "",
      "    cmapFiles = filelist(colormapDir, false, "".*colormap\\..+"");",
      "    if (cmapFiles === null || empty(cmapFiles)) {",
      "        println(""[primaryColormap] No colormap.* found. Skipping."");",
      "        return;",
      "    }",
      "",
      "    palFile = globalDir + ""/PLAYPAL.pal"";",
      "    if (!fileexists(palFile)) {",
      "        println(""[primaryColormap] PLAYPAL.pal not found. Using default conversion palette."");",
      "    } else {",
      "        println(""[primaryColormap] PLAYPAL.pal found. Using project palette for conversion."");",
      "    }",
      "",
      "    println(""[primaryColormap] Converting colormap-primary -> _global ..."");",
      "    convertimg(colormapDir, globalDir, ""colormaps"");",
      "",
      "    lowerOut = globalDir + ""/colormap.cmp"";",
      "    upperOut = globalDir + ""/COLORMAP.cmp"";",
      "",
      "    if (fileexists(lowerOut) && !fileexists(upperOut)) {",
      "        copyfile(file(lowerOut), file(upperOut), true);",
      "        filedelete(lowerOut);",
      "        println(""[primaryColormap] Renamed colormap.cmp -> COLORMAP.cmp"");",
      "    }",
      "",
      "    println(""[primaryColormap] Done."");",
      "}",
      ""
    )

    $new = @()
    if ($insertIndex -gt 0) { $new += $lines[0..($insertIndex - 1)] }
    $new += $block
    $new += $lines[$insertIndex..($lines.Count - 1)]

    [System.IO.File]::WriteAllLines($doommakeScriptPath, $new, $utf8NoBom)
    Write-Host "Inserted      : primaryColormap() function" -ForegroundColor Green
  }
}

# ---------------------------------------------------------------------
# STEP 4: Ensure primaryColormap() is called after initBuild() in doAll()
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 4: Patch doAll() to call primaryColormap()"
Write-Host "# -------------------------------------------"

$lines = @(Get-Content -LiteralPath $doommakeScriptPath)

$start = -1
$end   = -1
$brace = 0

for ($i = 0; $i -lt $lines.Length; $i++) {
  if ($lines[$i].Trim() -eq "check function doAll() {") { $start = $i; break }
}

if ($start -ge 0) {
  for ($i = $start; $i -lt $lines.Length; $i++) {
    $brace += ([regex]::Matches($lines[$i], '\{')).Count
    $brace -= ([regex]::Matches($lines[$i], '\}')).Count
    if ($i -gt $start -and $brace -eq 0) { $end = $i; break }
  }
}

if ($start -lt 0 -or $end -lt 0) {
  Write-Host "WARNING       : Could not patch doAll()" -ForegroundColor Yellow
} else {
  $block = $lines[$start..$end]
  if ($block -match 'primaryColormap\s*\(') {
    Write-Host "Already Present: primaryColormap() call in doAll()" -ForegroundColor DarkYellow
  } else {
    $new = @()
    for ($i = 0; $i -lt $lines.Length; $i++) {
      $new += $lines[$i]
      if ($i -gt $start -and $lines[$i].Trim() -eq "initBuild();") {
        $new += "    primaryColormap();"
      }
    }
    [System.IO.File]::WriteAllLines($doommakeScriptPath, $new, $utf8NoBom)
    Write-Host "Inserted      : primaryColormap() call into doAll()" -ForegroundColor Green
  }
}

# ---------------------------------------------------------------------
# STEP 5: Ensure TARGET: pcm exists
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------"
Write-Host "# STEP 5: Ensure TARGET: pcm exists"
Write-Host "# -------------------------------------------"

$lines = @(Get-Content -LiteralPath $doommakeScriptPath)
$joined = $lines -join "`n"

if ($joined -match '(?m)^\s*\*\s*TARGET:\s*pcm\s*$') {
  Write-Host "Already Present: TARGET: pcm" -ForegroundColor DarkYellow
} else {
  $block = @(
    "",
    "/****************************************************************************",
    " * TARGET: pcm",
    " ****************************************************************************",
    " * Builds a Primary Colour Map off playpal.pal",
    " * doommake pcm",
    " ****************************************************************************/",
    "check entry pcm(args) {",
    "    primaryColormap();",
    "}",
    ""
  )

  $lines += $block
  [System.IO.File]::WriteAllLines($doommakeScriptPath, $lines, $utf8NoBom)
  Write-Host "Inserted      : TARGET: pcm" -ForegroundColor Green
}

# ---------------------------------------------------------------------
# FINISHED
# ---------------------------------------------------------------------

Write-Host ""
Write-Host "# -------------------------------------------" -ForegroundColor Cyan
Write-Host "# doommake-tweak : FINISHED" -ForegroundColor Cyan
Write-Host "# -------------------------------------------" -ForegroundColor Cyan
Write-Host ""

exit 0
