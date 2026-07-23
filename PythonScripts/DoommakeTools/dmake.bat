@echo off
setlocal

rem ==============================================================================
rem dmake.bat - thin shim
rem ------------------------------------------------------------------------------
rem All logic lives in dmake_script.py (found on PATH). This shim:
rem   1. Locates dmake_script.py
rem   2. Runs it with all arguments via the py launcher
rem   3. Propagates the exit code
rem   4. If dmake_script.py requested a directory change (create -d), applies it
rem      to this cmd session via a temp handshake file
rem ==============================================================================

for /f "delims=" %%P in ('where dmake_script.py 2^>nul') do set "DMAKE_PY=%%P" & goto found_py
echo Error: dmake_script.py not found on PATH.
exit /b 2
:found_py

set "DMAKE_CD_FILE=%TEMP%\dmake_cd_%RANDOM%%RANDOM%.tmp"

py "%DMAKE_PY%" %*
set "PY_ERR=%ERRORLEVEL%"

if exist "%DMAKE_CD_FILE%" goto apply_cd
endlocal & exit /b %PY_ERR%

:apply_cd
set /p NEW_DIR=<"%DMAKE_CD_FILE%"
del "%DMAKE_CD_FILE%" >nul 2>&1
endlocal & cd /d "%NEW_DIR%" & exit /b %PY_ERR%
