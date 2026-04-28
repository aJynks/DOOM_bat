@echo off
:: fetchflats.bat
:: Usage: fetchflats -o "destination\path\"
setlocal enabledelayedexpansion
set "FETCHFLATS_ARGS=%*"
python "%~dp0fetchflats.py"
endlocal