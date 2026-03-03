@echo off
REM DoomTools Backup Utility - Batch Wrapper
REM This wrapper calls the PowerShell script with all arguments passed through

PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0dtbackup-doomtools-backup.ps1" %*