@echo off

REM Define variables for easy editing
set "DOOMMAKE_DIR=D:\Projects\Doom Projects\NOX\_NOX-WADproject"
set "DSDA_DOOM_EXE=D:\Projects\Doom Projects\_resources\_doom-engines\dsda-Doom\dsda-doom-0.28.3\dsda-doom.exe"
set "IWAD_PATH=D:\Games\Doom\_Engines\_IWADs\doom2.wad"
set "WAD_FILE=%DOOMMAKE_DIR%\build\NOX.wad"

REM Store the current directory
set "ORIGINAL_DIR=%CD%"

goto :check_args

:help
    echo.
    echo =============================================
    echo  This batch file is a wrapper for DoomMake
    echo  for my projects.
    echo.
    echo  Edit the variables at the top of the file
    echo  to set the correct paths.
    echo =============================================
    echo.
    echo  makewad        - Builds the project and runs Doom
    echo  makewad run    - Runs Doom without building
    echo  makewad clean  - Deletes all data in the build dir
    echo  makewad fresh  - Cleans, builds, and runs Doom
    echo.
	pause
    exit /b

:check_args
REM Check for invalid arguments or multiple arguments
if not "%2"=="" goto :error
if "%1"=="" goto :build
if "%1"=="help" goto :help
if "%1"=="run" goto :run
if "%1"=="clean" goto :clean
if "%1"=="fresh" goto :fresh

goto :error

:run
    call "%DSDA_DOOM_EXE%" -iwad "%IWAD_PATH%" -file "%WAD_FILE%"
	pause
    exit /b

:clean
    echo ---=== CLEANING build dir ===---
    call doommake clean
	pause
    exit /b

:fresh
    echo ---=== CLEANING build dir ===---
    call doommake clean
    echo.
    echo ---=== BUILDING ===---
    call doommake
	pause
    cd /d "%ORIGINAL_DIR%"
    call "%DSDA_DOOM_EXE%" -iwad "%IWAD_PATH%" -file "%WAD_FILE%"
	pause
    exit /b

:build
    echo ---=== BUILDING ===---
    call doommake
    pause
    cd /d "%ORIGINAL_DIR%"
    call "%DSDA_DOOM_EXE%" -iwad "%IWAD_PATH%" -file "%WAD_FILE%"
    pause
    exit /b

:error
	echo.
    echo ERROR: Invalid argument "%1".
    goto :help
