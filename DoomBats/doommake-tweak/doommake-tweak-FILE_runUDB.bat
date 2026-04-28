@echo off
set "ARGS=%*"
set "ROOT=%~dp0"
powershell -ExecutionPolicy Bypass -Command "& '%ROOT%runUDB.ps1' -ArgString '%ARGS%' -RootDir '%ROOT%'"
REM pause