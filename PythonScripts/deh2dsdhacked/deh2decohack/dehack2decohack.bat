@echo off
rem dehack2decohack.bat -- drag a .deh file onto this .bat, or run:
rem     dehack2decohack.bat input.deh [output.dh]
rem
rem Uses %~dp0 (this .bat's own folder) to find deh_parser.py, so it works
rem correctly no matter what directory you call it from or where your
rem .deh file lives.
if "%~1"=="" (
    echo Usage: dehack2decohack.bat input.deh [output.dh]
    pause
    exit /b 1
)
if "%~2"=="" (
    python "%~dp0deh_parser.py" "%~1"
) else (
    python "%~dp0deh_parser.py" "%~1" -o "%~2"
)
pause
