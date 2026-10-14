@echo off
setlocal
where py >nul 2>&1
if %errorlevel%==0 (
    py "%~dp0decorand_script.py" %*
) else (
    python "%~dp0decorand_script.py" %*
)
exit /b %errorlevel%
