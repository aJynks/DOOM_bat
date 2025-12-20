@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ==============================================================================
rem dmake.bat
rem ------------------------------------------------------------------------------
rem Wrapper for doommake with optional post-run of doom.bat
rem
rem Behaviour:
rem   - Arguments before "--" are passed to doommake
rem   - If "--" is present, doom.bat is run after doommake
rem   - Arguments after "--" are passed to doom.bat
rem   - If doommake returns a non-zero errorlevel, doom.bat will NOT run
rem ==============================================================================

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

:help
echo.
echo ==============================================================================
echo  DMAKE.BAT
echo  doommake wrapper with optional doom.bat launch
echo ==============================================================================
echo.
echo DESCRIPTION
echo   dmake is a small command-line wrapper for doommake.
echo.
echo   It forwards all arguments to doommake as normal.
echo   If a literal "--" is present, doom.bat is run AFTER doommake
echo   and receives any remaining arguments.
echo.
echo USAGE
echo   dmake [doommake_args...] [-- [doom_args...]]
echo.
echo EXAMPLES
echo   dmake fresh
echo       Runs: doommake fresh
echo.
echo   dmake fresh --
echo       Runs: doommake fresh
echo       Then: doom.bat
echo.
echo   dmake fresh -- -warp 5 -skill 5 -nosound
echo       Runs: doommake fresh
echo       Then: doom.bat -warp 5 -skill 5 -nosound
echo.
echo   dmake -- helion
echo       Runs: doommake
echo       Then: doom.bat helion
