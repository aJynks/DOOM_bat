@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_P=%~dp0playpal_genPlayPalPNG.py"
set "SCRIPT_C=%~dp0playpal_genColourMap.py"
set "SCRIPT_S=%~dp0playpal_playpalpng2Slade.py"

if "%~1"=="" goto :help

set "MODE="
if /I "%~1"=="-p" set "MODE=P"
if /I "%~1"=="-c" set "MODE=C"
if /I "%~1"=="-s" set "MODE=S"
if /I "%~1"=="--slade" set "MODE=S"

if not defined MODE goto :help

REM Remove mode flag
shift

REM Rebuild forwarded args (mode flag stripped)
set "FWDARGS="
set /a POS=0
set "EXPECT_VAL="

:parse
if "%~1"=="" goto :validate

set "FWDARGS=!FWDARGS! "%~1""

if defined EXPECT_VAL (
    set "EXPECT_VAL="
) else (
    if /I "%MODE%"=="P" (
        if /I "%~1"=="--scale" (
            set "EXPECT_VAL=1"
        ) else (
            set /a POS+=1
        )
    ) else if /I "%MODE%"=="S" (
        if /I "%~1"=="--cell" (
            set "EXPECT_VAL=1"
        ) else if /I "%~1"=="--outdir" (
            set "EXPECT_VAL=1"
        ) else (
            set /a POS+=1
        )
    ) else (
        set /a POS+=1
    )
)

shift
goto :parse

:validate
if defined EXPECT_VAL goto :help_missing_val

if /I "%MODE%"=="P" (
    if %POS% LSS 2 goto :help_p
    py -3 "%SCRIPT_P%" %FWDARGS%
    exit /b %errorlevel%
)

if /I "%MODE%"=="C" (
    if %POS% LSS 2 goto :help_c
    py -3 "%SCRIPT_C%" %FWDARGS%
    exit /b %errorlevel%
)

if /I "%MODE%"=="S" (
    if %POS% LSS 1 goto :help_s
    py -3 "%SCRIPT_S%" %FWDARGS%
    exit /b %errorlevel%
)

goto :help

:help
echo.
echo Usage (short flags):
echo   playpal -p ^<input^> ^<output.png^> [--scale N]
echo   playpal -c ^<input^> ^<output.png^>
echo   playpal -s ^<strip.png^> [--cell N] [--outdir DIR]
echo.
echo -------------------------
echo.
echo Usage (long flags):
echo   playpal --playpalpng ^<input^> ^<output.png^> [--scale N]
echo   playpal --colourmap  ^<input^> ^<output.png^>
echo   playpal --slade      ^<strip.png^> [--cell N] [--outdir DIR]
echo.
exit /b 2


:help_missing_val
echo.
echo Error: option requires a value.
echo.
goto :help

:help_p
echo.
echo Error: -p requires input and output.
echo Usage: playpal -p ^<input^> ^<output.png^> [--scale N]
echo.
exit /b 2

:help_c
echo.
echo Error: -c requires input and output.
echo Usage: playpal -c ^<input^> ^<output.png^>
echo.
exit /b 2

:help_s
echo.
echo Err
