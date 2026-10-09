@echo off
setlocal
python "%~dp0seamtile_script.py" %*
if errorlevel 1 pause
endlocal
