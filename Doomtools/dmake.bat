@echo off
REM dmake.bat - thin wrapper that launches dmake.ps1 and passes all args

setlocal
set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%dmake.ps1" %*

endlocal
