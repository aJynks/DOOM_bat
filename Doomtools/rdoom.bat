@echo off
REM rDoom.bat - launcher wrapper for rDoom.ps1

setlocal

REM Resolve directory this BAT is in (so PS script can live alongside it)
set "SCRIPT_DIR=%~dp0"

REM Call the PowerShell script, forwarding all arguments:
REM   rdoom            -> use defaults in rDoom.ps1
REM   rdoom dsda       -> override source port to 'dsda'
REM   rdoom doom       -> override IWAD to 'doom'
REM   rdoom dsda doom  -> override both, etc.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%rDoom.ps1" %*

endlocal
