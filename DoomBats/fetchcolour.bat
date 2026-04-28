@echo off
:: fetchcolour.bat
:: Usage: fetchcolour.bat "destination\path\" -c COLOUR [-v PERCENT]
setlocal enabledelayedexpansion

:: Grab the raw command line and strip the script name from the front,
:: leaving just the arguments exactly as typed.
set "ARGS=%*"

:: Pass the raw argument string to Python as a single environment variable.
:: Python will parse it properly, handling the trailing backslash-quote issue.
set "FETCHCOLOUR_ARGS=%ARGS%"
python "%~dp0fetchcolour.py"
endlocal