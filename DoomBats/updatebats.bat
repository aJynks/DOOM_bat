@echo off
REM updateBats.bat - Batch file wrapper for updateBats.ps1

REM Pass all parameters to PowerShell script
powershell.exe -ExecutionPolicy Bypass -File "%~dp0updateBats.ps1" %*

REM Exit with the same error code as PowerShell
exit /b %ERRORLEVEL%