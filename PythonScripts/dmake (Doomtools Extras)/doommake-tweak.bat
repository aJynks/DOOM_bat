@echo off
setlocal

rem ==============================================================================
rem doommake-tweak.bat - thin shim
rem ------------------------------------------------------------------------------
rem All logic lives in doommake-tweak-script.py (found on PATH). This shim:
rem   1. Locates doommake-tweak-script.py
rem   2. Runs it with all arguments via the py launcher
rem   3. Propagates the exit code
rem ==============================================================================

for /f "delims=" %%P in ('where doommake-tweak-script.py 2^>nul') do set "TWEAK_PY=%%P" & goto found_py
echo Error: doommake-tweak-script.py not found on PATH.
exit /b 2
:found_py

py "%TWEAK_PY%" %*
exit /b %ERRORLEVEL%
