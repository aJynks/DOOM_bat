:: =============================================================================
:: Doom Launcher Batch Script
::
:: This script launches the nyan-Doom engine with configurable IWAD, WAD files,
:: and command-line options.
::
:: === How to Configure ===
:: - Edit the variables below in the "Editable Config" section to change:
::     * ENGINE_EXE   : Path to your Doom engine executable
::     * IWAD_FILE   : Path to your IWAD file (e.g. doom2.wad)
::     * MAP_WAD     : The DoomMake project build WAD to load (relative path)
::     * OPTIONAL_WAD1..5 : Optional additional WAD files to load, specify full paths.
::                       Leave empty ("") to skip.
::
:: === How to Use ===
:: Run this batch file with optional command-line arguments:
::
::   -warp [number]   : Set the warp (map) number (overrides default warp 1)
::   -skill [number]  : Set the skill level (overrides default skill 4)
::   -menu            : Launch the game menu instead of starting a map.
::                      If -menu is used, -warp and -skill are NOT added.
::   Any other arguments are passed through directly to the engine.
::
:: Examples:
::   run.bat -warp 3 -skill 2
::   run.bat -menu
::   run.bat -nosound -warp 5
::
:: The script prints the final command line before launching the engine.
:: =============================================================================

@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

:: === Editable Config ===
set "ENGINE_EXE=d:\Projects\Doom Projects\_Resources\_Apps\_Engines\nyan-Doom\nyan-doom.exe"
set "IWAD_FILE=d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\doom2.wad"

:: === Name of DoomMake Project Build Wad ===
set "MAP_WAD=DT_Tut_01.wad"

:: == Any Optional Wads you wish to load ==
set "OPTIONAL_WAD1=d:\Games\Doom\Mods and WADs\GamePlay\_tweaks\extHUD_nyan-dsda\Vertical\Time on Screen\extHUD_dsda-nyan_VERTICAL_Time.MapName.wad"
set "OPTIONAL_WAD2=d:\Games\Doom\Mods and WADs\GamePlay\_tweaks\StatusBars\statusBar-GFXonly-Helmet.wad"
set "OPTIONAL_WAD3="
set "OPTIONAL_WAD4="
set "OPTIONAL_WAD5="

:: === Flags ===
set "HAS_WARP=false"
set "HAS_SKILL=false"
set "IS_MENU=false"
set "FINAL_ARGS="

:: === Parse Arguments ===
:parse_loop
if "%~1"=="" goto after_parse

if /I "%~1"=="-warp"  set HAS_WARP=true
if /I "%~1"=="-skill" set HAS_SKILL=true
if /I "%~1"=="-menu" (
    set IS_MENU=true
) else (
    set "FINAL_ARGS=!FINAL_ARGS! %~1"
)

shift
goto parse_loop

:after_parse

:: === Conditionally add default skill/warp unless -menu ===
set "EXTRA_ARGS="
if "%IS_MENU%"=="false" (
    if "%HAS_WARP%"=="false"  set "EXTRA_ARGS=!EXTRA_ARGS! -warp 1"
    if "%HAS_SKILL%"=="false" set "EXTRA_ARGS=!EXTRA_ARGS! -skill 4"
)

:: === Build -file line dynamically ===
set "FILE_ARGS="

for %%L in (OPTIONAL_WAD1 OPTIONAL_WAD2 OPTIONAL_WAD3 OPTIONAL_WAD4 OPTIONAL_WAD5) do (
    if defined %%L (
        set "VAL=!%%L!"
        if not "!VAL!"=="" set "FILE_ARGS=!FILE_ARGS! "!VAL!""
    )
)

if not "%MAP_WAD%"=="" set "FILE_ARGS=!FILE_ARGS! ".\build\%MAP_WAD%""

:: === Build the FULL command line string ===
set "FULL_CMD="

if not "%ENGINE_EXE%"=="" set FULL_CMD="%ENGINE_EXE%"
if not "%IWAD_FILE%"=="" set FULL_CMD=%FULL_CMD% -iwad "%IWAD_FILE%"
if not "!FILE_ARGS!"=="" set FULL_CMD=%FULL_CMD% -file !FILE_ARGS!
if not "!EXTRA_ARGS!"=="" set FULL_CMD=%FULL_CMD% !EXTRA_ARGS!
if not "!FINAL_ARGS!"=="" set FULL_CMD=%FULL_CMD% !FINAL_ARGS!

:: === Show the full command line ===
echo Running command:
echo %FULL_CMD%
echo.

:: === Execute the command ===
cmd /c "%FULL_CMD%"

endlocal
