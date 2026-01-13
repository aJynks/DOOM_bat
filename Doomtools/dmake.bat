@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ==============================================================================
rem Editable IWAD paths
rem ==============================================================================
set "IWAD_doom=d:\Games\Doom\_SourcePort\_iwads\doom.wad"
set "IWAD_doom2=d:\Games\Doom\_SourcePort\_iwads\doom2.wad"
set "IWAD_tnt=d:\Games\Doom\_SourcePort\_iwads\tnt.wad"
set "IWAD_plutonia=d:\Games\Doom\_SourcePort\_iwads\plutonia.wad"
set "IWAD_heretic=d:\Games\Doom\_SourcePort\_iwads\heretic.wad"
set "IWAD_hexen=d:\Games\Doom\_SourcePort\_iwads\hexen.wad"
set "IWAD_free1=d:\Games\Doom\_SourcePort\_iwads\freedoom1.wad"
set "IWAD_free2=d:\Games\Doom\_SourcePort\_iwads\freedoom2.wad"

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
rem   - Arguments before "--" are passed to doommake
rem   - If "--" is present, doom.bat is run after doommake
rem   - Arguments after "--" are passed to doom.bat
rem   - If doommake returns non-zero, doom.bat will NOT run
rem ==============================================================================

rem ---- Scan ALL arguments for "update" or "create" ------------------------------
for %%A in (%*) do (
    if /I "%%~A"=="update" goto do_update
    if /I "%%~A"=="create" goto do_create
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
shift
if "%~1"=="" exit /b 2

set "PROJECT_NAME=%~1"
shift

:parse_create
if "%~1"=="" goto show_create

if /I "%~1"=="-i" (
    if "%~2"=="" exit /b 2
    set "IWAD_NAME=%~2"
    shift
    shift
    goto parse_create
)

if /I "%~1"=="-d" (
    if "%~2"=="" exit /b 2
    set "DIR_NAME=%~2"
    shift
    shift
    goto parse_create
)

shift
goto parse_create

:show_create
set "IWAD_PATH=!IWAD_%IWAD_NAME%!"

echo I am in create mode
echo.
echo Project Name : %PROJECT_NAME%
echo IWAD Path   : %IWAD_PATH%
echo Directory   : %DIR_NAME%
echo.

if "%IWAD_PATH%"=="" exit /b 2

if defined DIR_NAME (
    if not exist "%DIR_NAME%" md "%DIR_NAME%"
    cd /d "%DIR_NAME%"
)

(echo %PROJECT_NAME%&echo %IWAD_PATH%&echo dsdhacked)|doommake --project-type wad "./" -n assets maps decohack texturesboom
set "CREATE_ERR=%ERRORLEVEL%"
call doommake-tweak
if defined DIR_NAME (
    endlocal & cd /d "%DIR_NAME%" & exit /b %CREATE_ERR%
)

endlocal & exit /b %CREATE_ERR%







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
echo.
echo     If ANY argument is "create", ALL other arguments are ignored and:
echo       create mode is entered
echo.
echo USAGE
echo   dmake [doommake_args...] [-- [doom_args...]]
echo   dmake update
echo   dmake create ProjectName [-i iwad] [-d folder]
echo.
exit /b 0
