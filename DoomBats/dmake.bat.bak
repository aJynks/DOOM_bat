@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ==============================================================================
rem Editable IWAD paths
rem ==============================================================================
set "IWAD_doom=D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad"
set "IWAD_doom2=D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad"
set "IWAD_tnt=D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad"
set "IWAD_plutonia=D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad"
set "IWAD_heretic=D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad"
set "IWAD_hexen=D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad"
set "IWAD_free1=D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad"
set "IWAD_free2=D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad"

rem ==============================================================================
rem dmake.bat
rem ------------------------------------------------------------------------------
rem Wrapper for doommake with optional post-run of doom.bat
rem
rem Behaviour:
rem   - If ANY argument is "update":
rem       Run doomtools --update && doomtools --update-cleanup && doomtools --update-shell
rem       Ignore all other arguments
rem   - If ANY argument is "create":
rem       Enter create mode (standalone)
rem       Ignore all other arguments
rem   - If ANY argument is "explode":
rem       Enter explode mode (standalone)
rem       Ignore all other arguments
rem   - If ANY argument is "watch":
rem       Enter watch mode (standalone)
rem       Ignore all other arguments
rem   - Arguments before "--" are passed to doommake
rem   - If "--" is present, doom.bat is run after doommake
rem   - Arguments after "--" are passed to doom.bat
rem   - If doommake returns non-zero, doom.bat will NOT run
rem ==============================================================================

rem ---- Scan ALL arguments for special commands ----------------------------------
for %%A in (%*) do (
    if /I "%%~A"=="update"  goto do_update
    if /I "%%~A"=="create"  goto do_create
    if /I "%%~A"=="explode" goto do_explode
    if /I "%%~A"=="watch"   goto do_watch
)

rem ---- Help triggers ------------------------------------------------------------
if "%~1"=="" goto main
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
if /I "%~1"=="/h" goto help
if /I "%~1"=="/?" goto help
if /I "%~1"=="help" goto help

:main
rem ---- Split arguments ----------------------------------------------------------
set "DM_ARGS="
set "DOOM_ARGS="
set "SEEN_DASHDASH="

:parse
if "%~1"=="" goto run

if not defined SEEN_DASHDASH (
    if "%~1"=="--" (
        set "SEEN_DASHDASH=1"
    ) else (
        set "DM_ARGS=!DM_ARGS! "%~1""
    )
) else (
    set "DOOM_ARGS=!DOOM_ARGS! "%~1""
)

shift
goto parse

:run
rem ---- Run doommake -------------------------------------------------------------
call doommake%DM_ARGS%
set "DM_ERR=%ERRORLEVEL%"

if not "%DM_ERR%"=="0" exit /b %DM_ERR%

rem ---- Run doom.bat if requested ------------------------------------------------
if defined SEEN_DASHDASH (
    call doom.bat%DOOM_ARGS%
    exit /b %ERRORLEVEL%
)

exit /b 0

:do_update
rem ---- DoomTools update chain (standalone; ignore all other args) ----------------
doomtools --update && doomtools --update-cleanup && doomtools --update-shell && doomtools --update-docs
exit /b %ERRORLEVEL%


:do_create
rem ---- Create mode (standalone) -------------------------------------------------
set "PROJECT_NAME="
set "IWAD_NAME=doom2"
set "DIR_NAME="

rem Move past the word "create"
:skip_create_word
shift
if "%~1"=="" (
    echo Error: Project name required
    echo Usage: dmake create ProjectName [-i iwad] [-d folder]
    exit /b 2
)

set "PROJECT_NAME=%~1"
shift

:parse_create_loop
if "%~1"=="" goto execute_create

if /I "%~1"=="-i" (
    if "%~2"=="" (
        echo Error: -i requires an IWAD name
        exit /b 2
    )
    set "IWAD_NAME=%~2"
    shift
    shift
    goto parse_create_loop
)

if /I "%~1"=="-d" (
    if "%~2"=="" (
        echo Error: -d requires a directory name
        exit /b 2
    )
    set "DIR_NAME=%~2"
    shift
    shift
    goto parse_create_loop
)

rem Unknown argument - skip it
shift
goto parse_create_loop

:execute_create
set "IWAD_PATH=!IWAD_%IWAD_NAME%!"

echo I am in create mode
echo.
echo Project Name : %PROJECT_NAME%
echo IWAD Path    : %IWAD_PATH%
echo Directory    : %DIR_NAME%
echo.

if "%IWAD_PATH%"=="" (
    echo Error: IWAD path not found for: %IWAD_NAME%
    echo Available IWADs: doom, doom2, tnt, plutonia, heretic, hexen, free1, free2
    exit /b 2
)

if defined DIR_NAME (
    if not exist "%DIR_NAME%" md "%DIR_NAME%"
    cd /d "%DIR_NAME%"
)

(echo %PROJECT_NAME%&echo %IWAD_PATH%&echo dsdhacked)|doommake --project-type wad "./" -n assets maps decohack texturesboom
set "CREATE_ERR=%ERRORLEVEL%"
call doommake-tweak -IwadPath "%IWAD_PATH%"
if defined DIR_NAME (
    endlocal & cd /d "%DIR_NAME%" & exit /b %CREATE_ERR%
)

endlocal & exit /b %CREATE_ERR%


:do_explode
rem ---- Explode mode (standalone) ------------------------------------------------
set "EXPLODE_WAD="
set "IWAD_NAME=doom2"
set "USE_WAD_PAL="

rem Move past the word "explode"
:skip_explode_word
shift
if "%~1"=="" (
    echo Error: WAD filename required
    echo Usage: dmake explode filename.wad [-i iwad]
    exit /b 2
)

set "EXPLODE_WAD=%~1"
shift

:parse_explode_loop
if "%~1"=="" goto execute_explode

if /I "%~1"=="-i" (
    if "%~2"=="" (
        echo Error: -i requires an IWAD name
        exit /b 2
    )
    set "IWAD_NAME=%~2"
    shift
    shift
    goto parse_explode_loop
)

if /I "%~1"=="-p" (
    set "USE_WAD_PAL=1"
    shift
    goto parse_explode_loop
)

rem Unknown argument - skip it
shift
goto parse_explode_loop

:execute_explode
set "IWAD_PATH=!IWAD_%IWAD_NAME%!"

rem Strip extension from WAD filename to build project name
for %%F in ("%EXPLODE_WAD%") do set "EXPLODE_STEM=%%~nF"
set "EXPLODE_PROJECT=_%EXPLODE_STEM%"

echo I am in explode mode
echo.
echo WAD File     : %EXPLODE_WAD%
echo Project Name : %EXPLODE_PROJECT%
if defined USE_WAD_PAL (
    echo PLAYPAL      : %EXPLODE_WAD% ^(from input WAD^)
) else (
    echo IWAD Path    : %IWAD_PATH%
)
echo.

if "%IWAD_PATH%"=="" (
    echo Error: IWAD path not found for: %IWAD_NAME%
    echo Available IWADs: doom, doom2, tnt, plutonia, heretic, hexen, free1, free2
    exit /b 2
)

if defined USE_WAD_PAL (
    (echo %EXPLODE_STEM%&echo %IWAD_PATH%&echo dsdhacked)|doommake %EXPLODE_PROJECT% --convert-palette "%EXPLODE_WAD%" --convert --explode "%EXPLODE_WAD%"
) else (
    (echo %EXPLODE_STEM%&echo %IWAD_PATH%&echo dsdhacked)|doommake %EXPLODE_PROJECT% --convert-palette "%IWAD_PATH%" --convert --explode "%EXPLODE_WAD%"
)
endlocal & exit /b %ERRORLEVEL%


:do_watch
rem ---- Watch mode (standalone; ignore all other args) ---------------------------
rem Verify we are inside a DoomTools project root by checking for both:
rem   - doommake.script
rem   - .doommake folder

if not exist "doommake.script" (
    echo Error: doommake.script not found in current directory.
    echo dmake watch must be run from the root of a DoomTools project.
    exit /b 2
)
if not exist "doommake.project.properties" (
    echo Error: doommake.project.properties not found in current directory.
    echo dmake watch must be run from the root of a DoomTools project.
    exit /b 2
)
if not exist "doommake.properties" (
    echo Error: doommake.properties not found in current directory.
    echo dmake watch must be run from the root of a DoomTools project.
    exit /b 2
)

echo Watching project in: %CD%
echo.
for /f "delims=" %%P in ('where dmake_watch.py 2^>nul') do set "WATCH_SCRIPT=%%P" & goto found_watch
echo Error: dmake_watch.py not found on PATH.
exit /b 2
:found_watch
py "%WATCH_SCRIPT%"
exit /b %ERRORLEVEL%


:help
echo.
echo ==============================================================================
echo  DMAKE.BAT
echo  doommake wrapper with optional doom.bat launch
echo ==============================================================================
echo.
echo DESCRIPTION
echo   dmake forwards arguments to doommake.
echo.
echo   If "--" is present, doom.bat is run AFTER doommake
echo   and receives the remaining arguments.
echo.
echo   SPECIAL BEHAVIOUR:
echo     If ANY argument is "update", ALL other arguments are ignored and:
echo       doomtools --update
echo       doomtools --update-cleanup
echo       doomtools --update-shell
echo       doomtools --update-docs
echo.
echo     If ANY argument is "create", ALL other arguments are ignored and:
echo       create mode is entered
echo.
echo     If ANY argument is "explode", ALL other arguments are ignored and:
echo       explode mode is entered
echo.
echo     If ANY argument is "watch", ALL other arguments are ignored and:
echo       watch mode is entered (must be run from a DoomTools project root)
echo.
echo USAGE
echo   dmake [doommake_args...] [-- [doom_args...]]
echo   dmake update
echo   dmake create ProjectName [-i iwad] [-d folder]
echo   dmake explode filename.wad [-i iwad] [-p]
echo   dmake watch
echo.
echo CREATE MODE OPTIONS
echo   ProjectName              Name of the project to create
echo   -i iwad                  IWAD to use (default: doom2)
echo                            Options: doom, doom2, tnt, plutonia, heretic,
echo                                     hexen, free1, free2
echo   -d folder                Directory to create project in (optional)
echo.
echo EXPLODE MODE OPTIONS
echo   filename.wad             WAD file to explode
echo   -i iwad                  IWAD to use (default: doom2)
echo                            Options: doom, doom2, tnt, plutonia, heretic,
echo                                     hexen, free1, free2
echo   -p                       Use input WAD's own PLAYPAL for palette conversion
echo                            instead of the IWAD (for WADs with custom palettes)
echo.
echo WATCH MODE
echo   Monitors the project for file changes and rebuilds automatically.
echo   Must be run from the root of a DoomTools project (requires
echo   doommake.script, doommake.project.properties, and
echo   doommake.properties to be present in the current directory).
echo.
echo EXAMPLES
echo   dmake create MyWAD
echo   dmake create MyWAD -i doom -d projects
echo   dmake create TestWAD -d "_01"
echo   dmake explode summoner.wad
echo   dmake explode summoner.wad -i tnt
echo   dmake explode summoner.wad -p
echo   dmake explode summoner.wad -i tnt -p
echo   dmake -- -skill 4 -warp 1
echo   dmake update
echo   dmake watch
echo.
exit /b 0