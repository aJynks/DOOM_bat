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
    echo [INFO] Installing gsudo...
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

REM ------------------------------------------------------------
REM Stage tracking
REM ------------------------------------------------------------

set STAGE_GIT=PENDING
set STAGE_JAVA=PENDING
set STAGE_ANT=PENDING
set STAGE_GSUDO=PENDING
set STAGE_CLONE=PENDING
set STAGE_DEPS=PENDING

echo.
echo [INFO] Installing prerequisites...

REM --- git ---
choco install git -y
if errorlevel 1 (
    set STAGE_GIT=FAILED
) else (
    set STAGE_GIT=OK
)

REM --- temurin (Java) - retry up to 3 times ---
set JAVA_ATTEMPT=0
:temurin_retry
set /a JAVA_ATTEMPT+=1
echo [INFO] Installing temurin (attempt !JAVA_ATTEMPT! of 3)...
choco install temurin -y
if errorlevel 1 (
    if !JAVA_ATTEMPT! LSS 3 (
        echo [WARN] temurin install failed, retrying...
        timeout /t 5 /nobreak >nul
        goto temurin_retry
    )
    set STAGE_JAVA=FAILED
) else (
    set STAGE_JAVA=OK
)

REM --- ant ---
choco install ant -y
if errorlevel 1 (
    set STAGE_ANT=FAILED
) else (
    set STAGE_ANT=OK
)

REM --- gsudo ---
choco install gsudo -y
if errorlevel 1 (
    REM already installed counts as OK
    set STAGE_GSUDO=OK
) else (
    set STAGE_GSUDO=OK
)

REM Refresh PATH so git/ant/java are available in this session
echo.
echo [INFO] Refreshing environment...
call refreshenv 2>nul

echo.
echo [INFO] Preparing repository...

REM --- clone ---
if not exist "%REPO%\.git" (

    if exist "%REPO%" (
        echo [INFO] Removing incomplete repo directory...
        rmdir /S /Q "%REPO%"
    )

    echo [INFO] Cloning repository...
    git clone %GITURL% "%REPO%"
    if errorlevel 1 (
        set STAGE_CLONE=FAILED
    ) else (
        set STAGE_CLONE=OK
    )
) else (
    echo [INFO] Repo already exists, skipping clone.
    set STAGE_CLONE=OK
)

REM --- dependencies ---
if "%STAGE_CLONE%"=="OK" (
    cd /d "%REPO%"
    echo.
    echo [INFO] Installing DoomTools dependencies...
    call ant dependencies
    if errorlevel 1 (
        set STAGE_DEPS=FAILED
    ) else (
        set STAGE_DEPS=OK
    )
) else (
    set STAGE_DEPS=SKIPPED
)

REM ------------------------------------------------------------
REM Setup report
REM ------------------------------------------------------------

echo.
echo =====================================
echo SETUP REPORT
echo =====================================
echo   git          : %STAGE_GIT%
echo   java/temurin : %STAGE_JAVA%
echo   ant          : %STAGE_ANT%
echo   gsudo        : %STAGE_GSUDO%
echo   repo clone   : %STAGE_CLONE%
echo   dependencies : %STAGE_DEPS%
echo =====================================

REM Fail if any critical stage failed
if "%STAGE_GIT%"=="FAILED"   goto setup_fail
if "%STAGE_JAVA%"=="FAILED"  goto setup_fail
if "%STAGE_ANT%"=="FAILED"   goto setup_fail
if "%STAGE_CLONE%"=="FAILED" goto setup_fail
if "%STAGE_DEPS%"=="FAILED"  goto setup_fail

echo.
echo =====================================
echo SETUP SUCCESSFUL
echo Run:
echo     build-doomtools.bat
echo =====================================
goto success

:setup_fail
echo.
echo =====================================
echo SETUP INCOMPLETE - see report above
echo =====================================
pause
exit /b 1

:success
exit /b 0

:fail
echo.
echo =====================================
echo FAILED
echo =====================================
pause
exit /b 1