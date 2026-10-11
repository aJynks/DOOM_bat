@echo off
setlocal

rem ==============================================================================
rem conform2palette.bat - thin shim
rem ------------------------------------------------------------------------------
rem All logic lives in conform2palette_script.py (found on PATH). This shim:
rem   1. Locates conform2palette_script.py
rem   2. Runs it with all arguments via the py launcher
rem   3. Propagates the exit code
rem ==============================================================================

for /f "delims=" %%P in ('where conform2palette_script.py 2^>nul') do set "C2P_PY=%%P" & goto found_py
echo Error: conform2palette_script.py not found on PATH.
exit /b 2
:found_py

py "%C2P_PY%" %*
exit /b %ERRORLEVEL%
