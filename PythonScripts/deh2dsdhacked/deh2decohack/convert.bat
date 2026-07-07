@echo off
rem deh2decohack -- drag a .deh file onto this .bat, or run:
rem     convert.bat input.deh [output.dh]
if "%~1"=="" (
    echo Usage: convert.bat input.deh [output.dh]
    pause
    exit /b 1
)
if "%~2"=="" (
    python "%~dp0convert.py" "%~1"
) else (
    python "%~dp0convert.py" "%~1" -o "%~2"
)
pause
