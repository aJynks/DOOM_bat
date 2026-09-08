@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Create the Doom project config directories in the current directory.
mkdir "_config" 2>nul
mkdir "_config\Autosaves" 2>nul
mkdir "_config\Demos" 2>nul
mkdir "_config\Screenshots" 2>nul

REM Explicit invocation: mdoom -invun <wadname>.wad
if /i "%~1"=="-invun" (
    if not "%~2"=="" (
        python "%~dp0addInvun.py" "%~2"
    )
    goto :eof
)

REM Any other arguments are ignored. Bare mdoom continues below.
if not "%~1"=="" goto :eof

REM Find WAD files in the current directory.
set "WAD_COUNT=0"
set "ONLY_WAD="
for /f "delims=" %%F in ('dir /b /a-d "*.wad" 2^>nul') do (
    set /a WAD_COUNT+=1
    set "ONLY_WAD=%%F"
)

REM Automatically run addInvun.py only when exactly one WAD was found.
if "!WAD_COUNT!"=="1" (
    python "%~dp0addInvun.py" "!ONLY_WAD!"
)

endlocal
