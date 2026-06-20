@echo off
REM compareImages.bat - wrapper for compareImages.py
REM The script next to this .bat is invoked (%~dp0), but it OPERATES on the
REM directory you run the command from (your current directory).
python "%~dp0compareImages.py" %*
