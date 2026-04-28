@echo off
:: shortdirs.bat
:: Usage: shortdirs [-dry]
setlocal enabledelayedexpansion
set "SHORTDIRS_ARGS=%*"
python "%~dp0shortdirs.py"
endlocal