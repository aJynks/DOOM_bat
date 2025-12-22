@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ==============================================================================
rem dmake.bat
rem ------------------------------------------------------------------------------
rem Wrapper for doommake with optional post-run of doom.bat
rem
rem Behaviour:
rem   - If ANY argument is "update":
rem       Run doomtools --update && doomtools --update-cleanup && doomtools --update-shell
rem       Ignore all other arguments
rem   - Arguments before "--" are passed to doommake
rem   - If "--" is present, doom.bat is run after doommake
rem   - Arguments after "--" are passed to doom.bat
rem   - If doommake returns non-zero, doom.bat will NOT run
rem ==============================================================================

rem ---- Scan ALL arguments for "update" ------------------------------------------
for %%A in (%*) do (
    if /I "%%~A"=="update" goto do_update
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
rem ---- DoomTools update chain ---------------------------------------------------
call doomtools --update
if errorlevel 1 exit /b %ERRORLEVEL%

call doomtools --update-cleanup
if errorlevel 1 exit /b %ERRORLEVEL%

call doomtools --update-shell
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
echo.
echo USAGE
echo   dmake [doommake_args...] [-- [doom_args...]]
echo   dmake update
echo   dmake fresh update -- -warp 5
echo.
exit /b 0
