@echo off
REM build-exeFiles-script.bat - Build doompal executables and standalone script

setlocal

REM Check for help
if "%1"=="-h" goto :show_help
if "%1"=="-help" goto :show_help
if "%1"=="--help" goto :show_help

REM Default to folder build if no args
if "%1"=="" goto :build_folder

REM Check for valid options
if "%1"=="-standalone-exe" goto :build_standalone_exe
if "%1"=="-standalone-python" (
    if "%2"=="-dependants" (
        goto :build_standalone_python_deps
    ) else (
        goto :build_standalone_python
    )
)
if "%1"=="-folder" goto :build_folder

echo ERROR: Invalid option: %1
echo.
goto :show_help

:show_help
echo ========================================
echo Build doompal executables
echo ========================================
echo.
echo Usage:
echo   [no args]                       Build folder-based .exe (default, faster)
echo   -folder                         Build folder-based .exe (faster ~0.5s startup)
echo   -standalone-exe                 Build single-file .exe (portable, slower ~2s startup)
echo   -standalone-python              Build single-file Python script (no .exe)
echo   -standalone-python -dependants  Build Python script + install dependencies
echo   -h                              Show this help
echo.
echo Output Locations:
echo   -folder              dist\doompal\doompal.exe (+ DLLs in same folder)
echo   -standalone-exe      dist\doompal-standalone.exe (single .exe file)
echo   -standalone-python   build\doompal_standalone.py (single Python script)
echo.
echo Comparison:
echo   -folder              Faster startup (~0.5s), requires folder
echo   -standalone-exe      Slower startup (~2s), single portable .exe
echo   -standalone-python   Fastest (~0.1s), requires Python installed
echo.
echo Recommendation: 
echo   Personal use:     -folder (fastest .exe)
echo   Distribution:     -standalone-exe (portable .exe)
echo   Developers:       -standalone-python (requires Python)
echo.
goto :end

:build_standalone_exe
echo ========================================
echo Building STANDALONE .EXE
echo ========================================
echo.
echo Pros: One portable .exe file
echo Cons: Slower startup (~2 seconds)
echo.

REM Check PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building...
pyinstaller --clean ^
    --onefile ^
    --name doompal-standalone ^
    --console ^
    --noconfirm ^
    --log-level WARN ^
    doompal.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output: dist\doompal-standalone.exe
echo Size: ~15-20 MB
echo Startup: ~2 seconds
echo.
echo To use:
echo   1. Copy dist\doompal-standalone.exe anywhere
echo   2. Rename to doompal.exe if desired
echo   3. Add to PATH or run directly
echo.
goto :success

:build_standalone_python
echo ========================================
echo Building STANDALONE PYTHON SCRIPT
echo ========================================
echo.
echo Pros: Fastest startup (~0.1s), no .exe bloat
echo Cons: Requires Python + dependencies installed
echo.

echo Building from ./doompal/ directory...
python build-singlePython-script.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    echo.
    echo Make sure build-singlePython-script.py exists and ./doompal/ directory is present
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output: build\doompal_standalone.py
echo Size: ~50-60 KB
echo Startup: ~0.1 seconds
echo.
echo To use:
echo   1. Run: python build\doompal_standalone.py [command]
echo   2. Or copy to PATH location
echo.
echo Dependencies required:
echo   pip install Pillow numpy
echo.
echo To build AND install dependencies, use:
echo   -standalone-python -dependants
echo.
goto :success

:build_standalone_python_deps
echo ========================================
echo Building STANDALONE PYTHON SCRIPT
echo WITH DEPENDENCIES
echo ========================================
echo.
echo This will:
echo   1. Update pip
echo   2. Install/update all dependencies
echo   3. Build standalone Python script
echo.

echo [1/3] Updating pip...
python -m pip install --upgrade pip

if %errorlevel% neq 0 (
    echo.
    echo WARNING: pip update failed, continuing anyway...
)

echo.
echo [2/3] Installing dependencies...
pip install Pillow numpy

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo [3/3] Building standalone script...
python build-singlePython-script.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    echo.
    echo Make sure build-singlePython-script.py exists and ./doompal/ directory is present
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output: build\doompal_standalone.py
echo Size: ~50-60 KB
echo Startup: ~0.1 seconds
echo Dependencies: Installed
echo.
echo To use:
echo   python build\doompal_standalone.py [command]
echo.
goto :success

:build_folder
echo ========================================
echo Building FOLDER-BASED .EXE
echo ========================================
echo.
echo Pros: Fast startup (~0.5 seconds)
echo Cons: Need entire folder (exe + DLLs)
echo.

REM Check PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building...
pyinstaller --clean ^
    --onedir ^
    --name doompal ^
    --console ^
    --noconfirm ^
    --log-level WARN ^
    doompal.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output: dist\doompal\doompal.exe
echo Folder size: ~25-30 MB
echo Startup: ~0.5 seconds
echo.
echo To use:
echo   1. Copy entire dist\doompal\ folder
echo   2. Add folder to PATH
echo   3. Run: doompal [command]
echo.
goto :success

:success
echo Build successful!
echo.
pause
goto :end

:end
endlocal