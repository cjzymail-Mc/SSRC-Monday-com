@echo off
setlocal
cd /d "%~dp0"
if not defined FLOWBOARD_PYTHON set "FLOWBOARD_PYTHON=python"
"%FLOWBOARD_PYTHON%" -X utf8 flowboard_deploy.py update %*
set "FLOWBOARD_EXIT=%ERRORLEVEL%"
exit /b %FLOWBOARD_EXIT%
