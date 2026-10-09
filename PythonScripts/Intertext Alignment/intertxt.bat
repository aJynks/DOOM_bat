@echo off
setlocal
rem intertext - UMAPINFO intertext formatter. Keep next to intertext_script.py.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0intertxt_script.py" %*
) else (
    python "%~dp0intertxt_script.py" %*
)
exit /b %errorlevel%
