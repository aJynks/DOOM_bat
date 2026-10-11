@echo off
setlocal

rem ==============================================================================
rem doom.bat - thin shim
rem ------------------------------------------------------------------------------
rem All logic lives in doom_script.py (found on PATH). This shim:
rem   1. Locates doom_script.py
rem   2. Runs it with all arguments via the py launcher
rem   3. Propagates the exit code
rem ==============================================================================

for /f "delims=" %%P in ('where doom_script.py 2^>nul') do set "DOOM_PY=%%P" & goto found_py
echo Error: doom_script.py not found on PATH.
exit /b 2
:found_py

py "%DOOM_PY%" %*
exit /b %ERRORLEVEL%
