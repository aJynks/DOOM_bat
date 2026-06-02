@echo off
setlocal EnableDelayedExpansion

set ROOT=D:\tmp\doomtools-dev
set REPO=%ROOT%\git
set RELEASE=%ROOT%\release
set GITURL=https://github.com/MTrop/DoomTools.git

set DO_SETUP=0

REM ------------------------------------------------------------
REM Parse arguments
REM ------------------------------------------------------------

for %%A in (%*) do (
    if /I "%%~A"=="-setup" set DO_SETUP=1
    if /I "%%~A"=="--setup" set DO_SETUP=1
    if /I "%%~A"=="-s" set DO_SETUP=1
)

echo.
echo =====================================
echo DoomTools
echo =====================================
echo.

REM ------------------------------------------------------------
REM Ensure base directories exist (create each level explicitly)
REM ------------------------------------------------------------

if not exist "D:\tmp" mkdir "D:\tmp"
if not exist "%ROOT%" mkdir "%ROOT%"
if not exist "%RELEASE%" mkdir "%RELEASE%"

REM ------------------------------------------------------------
REM SETUP MODE
REM ------------------------------------------------------------

if "%DO_SETUP%"=="1" goto setup

REM ------------------------------------------------------------
REM NORMAL BUILD MODE
REM ------------------------------------------------------------

echo [INFO] Build mode

if not exist "%REPO%\.git" (
    echo [ERROR] Repo not found.
    echo Run:
    echo     build-doomtools.bat --setup
    goto fail
)

cd /d "%REPO%"

echo.
echo [INFO] Updating repository...
git pull
if errorlevel 1 goto fail

echo.
echo [INFO] Compiling...
call ant compile
if errorlevel 1 goto fail

echo.
echo [INFO] Deploying...
call ant deploy.cmd -Ddeploy.dir="%RELEASE%"
if errorlevel 1 goto fail

echo.
echo =====================================
echo BUILD COMPLETE
echo Output:
echo %RELEASE%
echo =====================================
goto success

REM ------------------------------------------------------------
REM SETUP
REM ------------------------------------------------------------

:setup

echo [INFO] Setup mode

REM Ensure gsudo exists first (needed to elevate)
where gsudo >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing gsudo via choco...
    choco install gsudo -y
    if errorlevel 1 (
        echo [ERROR] Could not install gsudo. Is Chocolatey installed?
        goto fail
    )
)

REM Relaunch elevated if not already admin
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Requesting admin privileges...
    gsudo "%~f0" --setup
    exit /b %errorlevel%
)

echo.
echo [INFO] Installing prerequisites...

choco install git -y
if errorlevel 1 goto fail

choco install temurin -y
if errorlevel 1 goto fail

choco install ant -y
if errorlevel 1 goto fail

choco install gsudo -y
if errorlevel 1 goto fail

REM Refresh PATH so git/ant/java are available in this session
echo [INFO] Refreshing environment...
call refreshenv 2>nul

echo.
echo [INFO] Preparing repository...

if not exist "%REPO%\.git" (

    if exist "%REPO%" (
        echo [INFO] Removing incomplete repo directory...
        rmdir /S /Q "%REPO%"
    )

    echo [INFO] Cloning repository...
    git clone %GITURL% "%REPO%"
    if errorlevel 1 goto fail
)

cd /d "%REPO%"

echo.
echo [INFO] Installing DoomTools dependencies...
call ant dependencies
if errorlevel 1 goto fail

echo.
echo =====================================
echo SETUP COMPLETE
echo Run:
echo     build-doomtools.bat
echo =====================================
goto success

:success
exit /b 0

:fail
echo.
echo =====================================
echo FAILED
echo =====================================
pause
exit /b 1