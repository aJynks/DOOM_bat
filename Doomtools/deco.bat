@echo off
setlocal

rem Directory of this BAT file
set "SCRIPT_DIR=%~dp0"
set "PS1_FILE=%SCRIPT_DIR%deco.ps1"

if not exist "%PS1_FILE%" (
    echo [ERROR] PowerShell script not found: "%PS1_FILE%"
    exit /b 1
)

rem Call PowerShell, preserving CMD working directory and forwarding args
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" %*

set "EXITCODE=%ERRORLEVEL%"
endlocal & exit /b %EXITCODE%
