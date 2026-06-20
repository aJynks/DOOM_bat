@echo off
setlocal

rem ==============================================================================
rem doommake-tweak.bat - shim with project-root guard + pre-run confirmation
rem ------------------------------------------------------------------------------
rem Launches doommake-tweak-zscript.ps1 (sitting next to this .bat) only if the
rem CURRENT directory is a DoomTools project root - all three marker files
rem present. Otherwise errors out loudly. On pass, reports the target dir.
rem (Pause is currently disabled - re-enable the two rem'd lines below to make
rem  it wait for a keypress before modifying anything.)
rem ==============================================================================

set "MISSING="
if not exist "doommake.properties"          set "MISSING=%MISSING% doommake.properties"
if not exist "doommake.script"              set "MISSING=%MISSING% doommake.script"
if not exist "doommake.project.properties"  set "MISSING=%MISSING% doommake.project.properties"

if defined MISSING (
    echo.
    echo ERROR: doommake-tweak must be run from the root of a DoomTools project.
    echo        Current directory: "%CD%"
    echo        Missing file^(s^):%MISSING%
    echo.
    endlocal
    exit /b 2
)

echo.
echo ==============================================================================
echo  doommake-tweak - about to tweak this project:
echo      "%CD%"
echo  Found: doommake.properties, doommake.script, doommake.project.properties
echo ==============================================================================
rem echo.
rem pause

powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0doommake-tweak-zscript.ps1" %*
set "PS_ERR=%ERRORLEVEL%"
endlocal & exit /b %PS_ERR%