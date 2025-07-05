@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

:: === Editable Config ===
set "ENGINE_EXE=d:\Projects\Doom Projects\_Resources\_Apps\_Engines\nyan-Doom\nyan-doom.exe"
set "IWAD_FILE=d:\Projects\Doom Projects\_Resources\_Apps\_Engines\_IWADs\doom2.wad"

:: === Name of DoomMake Project Build Wad ===
set "MAP_WAD=DT_Tut_02-Textures.wad"

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


:: === TextureX Data ===
set "textureX_Path=.\scripts\TextureX"
set "txtRestricted=texture1-Restricted.txt"
set "txtALL=texture1-ALL.txt"

:: === Handle Special Commands Early ===
if /I "%~1"=="-setTxA" (
    echo Adding all the Doom Textures to texture1.txt
    copy /Y "%textureX_Path%\%txtALL%" ".\src\textures\texture1.txt"
	doommake textures
    goto :eof
)

if /I "%~1"=="-setTxR" (
    echo restricting texture1.txt to only the new custom textures
    copy /Y "%textureX_Path%\%txtRestricted%" ".\src\textures\texture1.txt"
	doommake textures
    goto :eof
)

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

:: =============================================================================
:: Doom Launcher Batch Script
::
:: This script launches the specified Doom engine with configurable IWAD, WAD files,
:: and command-line options.
::
:: === How to Configure ===
:: - Edit the variables below in the "Editable Config" section to change:
::     * ENGINE_EXE        : Path to your Doom engine executable
::     * IWAD_FILE         : Path to your IWAD file (e.g. doom2.wad)
::     * MAP_WAD           : The name of the build WAD to test; this is usually
::                           located at "./build/yourmapname.wad"
::     * OPTIONAL_WAD1..5  : Optional additional WAD files to load (full paths only).
::                           Leave empty ("") to skip.
::
:: === How to Use ===
:: Run this batch file with optional command-line arguments:
::
::   -menu             : Launch the game without warping, so you see the title screen
::                       and game menu instead of starting a map.
::   -skill 4          : If a skill is not specified, it will default to -skill 4
::   -warp 1           : If a warp map is not specified, it will default to -warp 1
::
::   Additionally, all source port command-line options will be passed through
::   directly to the engine.
::   Example: -nomonsters -nosound
::
:: Examples:
::   run.bat -warp 3 -skill 2
::   run.bat -menu
::   run.bat -nosound -warp 5
::   run.bat -nomonsters -nosound -skill 1
::
:: The script prints the final command line before launching the engine.
::
::
:: === Additional DoomTools Texture Build Feature ===
::
:: If you wish to use the Texture1 trick to enable proper previews in Ultimate Doom Builder (UDB),
:: you should create two versions of your texture1.txt file:
::
::     1. "RESTRICTED" — contains only your custom texture definitions
::     2. "ALL"        — includes both custom and IWAD texture definitions
::
:: To do this:
::   - Copy the default texture1.txt
::   - Generate the full version using `doommake rebuildtextures`
::   - Save both versions in a directory of your choice
::
:: Then, in this batch file, configure the === TextureX Data === section
:: to point to that directory and the two file names.
::
:: Use the following flags to switch modes:
::   -setTxA   : Copies texture1-ALL.txt into the project directory and runs `doommake textures`
::   -setTxR   : Copies texture1-RESTRICTED.txt into the project directory and runs `doommake textures`
::
:: See my DoomTools texturing tutorial for a full walkthrough:
::   https://youtu.be/32MVnFJrZlk?t=1303 (at 21:43)
:: =============================================================================
