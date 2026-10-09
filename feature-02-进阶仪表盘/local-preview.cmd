@echo off
setlocal
cd /d "%~dp0.."
python -X utf8 "%~dp0preview.py" %*
if errorlevel 1 pause
