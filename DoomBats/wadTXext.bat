@echo off
REM wadTXext.bat - WAD Texture Extractor Wrapper
REM Extracts textures, patches, and flats from Doom WAD files

setlocal enabledelayedexpansion

REM Default values
set "OUTPUT_DIR=%CD%"
set "SHOW_HELP=0"
set "WADFILE="
set "MAPNAME="
set "IWAD="
set "MODE="

REM Parse arguments
:parse_args
if "%~1"=="" goto check_args
if /i "%~1"=="-h" set "SHOW_HELP=1" & shift & goto parse_args
if /i "%~1"=="--help" set "SHOW_HELP=1" & shift & goto parse_args
if /i "%~1"=="help" set "SHOW_HELP=1" & shift & goto parse_args
if /i "%~1"=="-d" set "OUTPUT_DIR=%~2" & shift & shift & goto parse_args
if /i "%~1"=="--directoryOutput" set "OUTPUT_DIR=%~2" & shift & shift & goto parse_args
if /i "%~1"=="-map" set "MAPNAME=%~2" & shift & shift & goto parse_args
if /i "%~1"=="-iwad" set "IWAD=%~2" & shift & shift & goto parse_args
if /i "%~1"=="-list" set "MODE=-list" & shift & goto parse_args
if /i "%~1"=="-lump" set "MODE=-lump" & shift & goto parse_args
if /i "%~1"=="-png" set "MODE=-png" & shift & goto parse_args
if not defined WADFILE set "WADFILE=%~1" & shift & goto parse_args
shift
goto parse_args

:check_args
if %SHOW_HELP%==1 goto show_help
if not defined WADFILE goto show_help
if not defined MAPNAME goto show_help
if not defined IWAD goto show_help

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo.
    echo Please install Python 3.6 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    goto end
)

REM Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Change to output directory
pushd "%OUTPUT_DIR%"

REM Find wadTXext.py in PATH
for /f "delims=" %%i in ('where wadTXext.py 2^>nul') do set "PYTHON_SCRIPT=%%i"

if not defined PYTHON_SCRIPT (
    echo ERROR: wadTXext.py not found in PATH!
    echo Please ensure wadTXext.py is in the same directory as wadTXext.bat or in your PATH.
    popd
    goto end
)

REM Build Python command
set "CMD=python "%PYTHON_SCRIPT%" "%WADFILE%" -map %MAPNAME% -iwad "%IWAD%""
if defined MODE set "CMD=!CMD! %MODE%"

REM Execute Python script
echo Running: !CMD!
echo.
!CMD!

REM Return to original directory
popd

goto end

:show_help
echo.
echo wadTXext.bat - WAD Texture Extractor
echo ====================================
echo.
echo Extracts textures, patches, and flats used by a specific map from a Doom WAD file.
echo.
echo USAGE:
echo   wadTXext.bat WADFILE -map MAPNAME -iwad IWADFILE [OPTIONS]
echo.
echo REQUIRED ARGUMENTS:
echo   WADFILE              Path to the WAD file containing the map
echo   -map MAPNAME         Map to extract textures from (e.g., MAP01, E1M1)
echo   -iwad IWADFILE       Path to IWAD file (e.g., doom2.wad)
echo.
echo OPTIONS:
echo   -d, --directoryOutput DIR
echo                        Output directory (default: current directory)
echo   -list                List resources only (don't extract)
echo   -lump                Extract as raw lump files
echo   -png                 Extract as PNG images (default if no mode specified)
echo   -h, --help           Show this help message
echo.
echo OUTPUT STRUCTURE:
echo   flats/               Floor and ceiling flats
echo   flats/doom2/         Flats from IWAD (if needed)
echo   patches/             Individual patch graphics
echo   patches/doom2/       Patches from IWAD (if needed)
echo   composite/           Multi-patch composite textures
echo   composite/singlePatch/   Single-patch textures (by texture name)
echo   composite/doom2/     Composites from IWAD (if needed)
echo   composite/singlePatch/doom2/  Single-patch from IWAD (if needed)
echo.
echo EXAMPLES:
echo   List all resources used by MAP01:
echo     wadTXext.bat mymap.wad -map MAP01 -iwad doom2.wad -list
echo.
echo   Extract as PNG to current directory:
echo     wadTXext.bat mymap.wad -map MAP01 -iwad doom2.wad
echo.
echo   Extract as PNG to specific directory:
echo     wadTXext.bat mymap.wad -map MAP01 -iwad doom2.wad -d "C:\Doom\Textures"
echo.
echo   Extract as raw lumps:
echo     wadTXext.bat mymap.wad -map MAP01 -iwad doom2.wad -lump
echo.
echo REQUIREMENTS:
echo   - Python 3.6 or higher
echo   - wadTXext.py must be in PATH or same directory
echo   - Pillow library for PNG export: pip install Pillow
echo.

:end
endlocal