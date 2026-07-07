@echo off
rem textureextract.bat — run textureextract.py from anywhere on PATH.
setlocal
python "%~dp0textureextract.py" %*
endlocal
