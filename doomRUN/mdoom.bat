@echo off
REM =====================================================
REM mdoom.bat
REM Creates _config folder structure for Doom projects.
REM Supports:
REM   -a Author Name
REM   -w Wad Name
REM No quotes needed, order doesn’t matter.
REM =====================================================

setlocal enabledelayedexpansion

set "AUTHOR="
set "WAD="
set "currentFlag="

REM --- Parse all arguments ---
:parse
if "%~1"=="" goto done_parse

if /i "%~1"=="-a" (
    set "currentFlag=AUTHOR"
    shift
    goto parse
)

if /i "%~1"=="-w" (
    set "currentFlag=WAD"
    shift
    goto parse
)

REM Append words to whichever flag is active
if defined currentFlag (
    if "!%currentFlag%!"=="" (
        set "%currentFlag%=%~1"
    ) else (
        set "%currentFlag%=!%currentFlag%! %~1"
    )
)
shift
goto parse

:done_parse

REM --- Handle all cases ---

REM 1) No params
if "%AUTHOR%"=="" if "%WAD%"=="" (
    echo Creating _config in current directory...
    mkdir "_config" 2>nul
    mkdir "_config\Autosaves" 2>nul
    mkdir "_config\Demos" 2>nul
    mkdir "_config\Screenshots" 2>nul
    echo Done.
    goto :eof
)

REM 2) -a only (error)
if not "%AUTHOR%"=="" if "%WAD%"=="" (
    echo [ERROR] Missing -w Wad Name. Nothing created.
    pause
    goto :eof
)

REM 3) -w only
if "%AUTHOR%"=="" if not "%WAD%"=="" (
    echo Creating structure for Wad: "%WAD%"...
    mkdir "%WAD%" 2>nul
    mkdir "%WAD%\_config" 2>nul
    mkdir "%WAD%\_config\Autosaves" 2>nul
    mkdir "%WAD%\_config\Demos" 2>nul
    mkdir "%WAD%\_config\Screenshots" 2>nul
    echo Done.
    goto :eof
)

REM 4) -a and -w
if not "%AUTHOR%"=="" if not "%WAD%"=="" (
    echo Creating structure for "%AUTHOR%\%WAD%"...
    mkdir "%AUTHOR%" 2>nul
    mkdir "%AUTHOR%\%WAD%" 2>nul
    mkdir "%AUTHOR%\%WAD%\_config" 2>nul
    mkdir "%AUTHOR%\%WAD%\_config\Autosaves" 2>nul
    mkdir "%AUTHOR%\%WAD%\_config\Demos" 2>nul
    mkdir "%AUTHOR%\%WAD%\_config\Screenshots" 2>nul
    echo Done.
    goto :eof
)
