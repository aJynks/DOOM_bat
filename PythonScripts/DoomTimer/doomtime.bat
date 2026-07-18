@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0doomtime.ps1" -ArgString "%*"