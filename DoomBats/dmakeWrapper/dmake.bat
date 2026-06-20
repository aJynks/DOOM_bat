@echo off
setlocal

rem ==============================================================================
rem dmake.bat - thin shim
rem ------------------------------------------------------------------------------
rem All logic lives in dmakeScript.ps1 (found on PATH). This shim:
rem   1. Locates dmakeScript.ps1
rem   2. Runs it with all arguments
rem   3. Propagates the exit code
rem   4. If dmakeScript.ps1 requested a directory change (create -d), applies it
rem      to this cmd session via a temp handshake file
rem ==============================================================================

for /f "delims=" %%P in ('where dmakeScript.ps1 2^>nul') do set "DMAKE_PS1=%%P" & goto found_ps1
echo Error: dmakeScript.ps1 not found on PATH.
exit /b 2
:found_ps1

set "DMAKE_CD_FILE=%TEMP%\dmake_cd_%RANDOM%%RANDOM%.tmp"

powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%DMAKE_PS1%" %*
set "PS_ERR=%ERRORLEVEL%"

if exist "%DMAKE_CD_FILE%" goto apply_cd
endlocal & exit /b %PS_ERR%

:apply_cd
set /p NEW_DIR=<"%DMAKE_CD_FILE%"
del "%DMAKE_CD_FILE%" >nul 2>&1
endlocal & cd /d "%NEW_DIR%" & exit /b %PS_ERR%