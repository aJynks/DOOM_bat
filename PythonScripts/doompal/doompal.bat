@echo off
REM doompal.bat - Launcher for doompal Python script
REM Place this .bat file in your PATH alongside doompal_standalone.py

REM Run the Python script with all arguments passed through
python "%~dp0doompal_standalone.py" %*