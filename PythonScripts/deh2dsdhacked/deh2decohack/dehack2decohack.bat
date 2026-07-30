@echo off
rem dehack2decohack.bat -- drag a .deh / .bex / DECORATE lump onto this .bat,
rem or run:  dehack2decohack.bat input.deh [output.dh]
rem
rem Uses %~dp0 (this .bat's own folder) to find deh_parser.py, so it works
rem no matter what directory you call it from or where your input lives.
rem Input format (DeHackEd vs DECORATE) is auto-detected.
if "%~1"=="" (
    echo Usage: dehack2decohack.bat input.deh ^[output.dh^]
    echo        input may be a DeHackEd/BEX patch or a DECORATE lump.
    pause
    exit /b 1
)
if "%~2"=="" (
    python "%~dp0deh_parser.py" "%~1"
) else (
    python "%~dp0deh_parser.py" "%~1" -o "%~2"
)
pause
