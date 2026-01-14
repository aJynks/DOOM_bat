@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===== Config defaults =====
set "USE_PYTHON=true"
set "PYTHON_CMD=png2cube.py"
set "EXE_CMD=PNG2Cube.exe"
REM ===========================

if "%~1"=="" (
  echo Usage: doomcube palette.png [-title "My LUT Title"] [--python ^| --exe]
  exit /b 1
)

set "INPUT=%~1"
set "NAME=%~n1"
shift

if not exist "%INPUT%" (
  echo ERROR: File not found: %INPUT%
  exit /b 1
)

REM TITLE is param-only (or defaults later)
set "TITLE="

REM ---- parse optional args ----
:parse
if "%~1"=="" goto doneparse

if /I "%~1"=="--python" (
  set "USE_PYTHON=true"
  shift
  goto parse
)

if /I "%~1"=="--exe" (
  set "USE_PYTHON=false"
  shift
  goto parse
)

REM Accept -title or --title
if /I "%~1"=="-title"  goto read_title
if /I "%~1"=="--title" goto read_title

echo ERROR: Unknown option: %~1
echo Usage: doomcube palette.png [-title "My LUT Title"] [--python ^| --exe]
exit /b 1

:read_title
shift
if "%~1"=="" (
  echo ERROR: -title requires a value.
  exit /b 1
)
set "TITLE=%~1"
shift
goto parse

:doneparse

REM Default title if not set by param
if not defined TITLE set "TITLE=%NAME%"

set "HALD=%NAME%_(hald).png"
set "HALD_INDEXED=%NAME%_(hald_indexed).png"
set "HALD_RGB16=%NAME%_(hald_indexed_rgb16).png"
set "CUBE=%NAME%.cube"

echo Input palette: %INPUT%
if /I "%USE_PYTHON%"=="true" (
  echo Using: PYTHON == %PYTHON_CMD%
) else (
  echo Using: EXE == %EXE_CMD%
)
echo Title: %TITLE%
echo.

echo Generating HALD...
magick hald:8 -depth 16 -colorspace sRGB "%HALD%" || goto :error

echo Indexing HALD to Doom palette...
magick "%HALD%" -dither None -remap "%INPUT%" "%HALD_INDEXED%" || goto :error

echo Converting indexed HALD back to RGB 16-bit...
magick "%HALD_INDEXED%" -colorspace sRGB -depth 16 "%HALD_RGB16%" || goto :error

echo Converting to .cube...
if /I "%USE_PYTHON%"=="true" (
  "%PYTHON_CMD%" "%HALD_RGB16%" "%CUBE%" --title "%TITLE%" || goto :error
) else (
  "%EXE_CMD%" "%HALD_RGB16%" "%CUBE%" || goto :error
)

echo Cleaning up temporary PNGs...
del "%HALD%" >nul 2>&1
del "%HALD_INDEXED%" >nul 2>&1
del "%HALD_RGB16%" >nul 2>&1

echo.
echo Done!
echo Output: %CUBE%
echo.
exit /b 0

:error
echo.
echo ERROR: Something failed. Temporary files not deleted.
exit /b 1
