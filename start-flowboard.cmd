@echo off
setlocal
cd /d "%~dp0"
if not defined FLOWBOARD_PYTHON set "FLOWBOARD_PYTHON=python"
"%FLOWBOARD_PYTHON%" -X utf8 flowboard_deploy.py start %*
set "FLOWBOARD_EXIT=%ERRORLEVEL%"
if not "%FLOWBOARD_EXIT%"=="0" if "%~1"=="" (
  echo.
  echo [ERROR] Flowboard did not start. Review the error above before closing this window.
  pause
)
exit /b %FLOWBOARD_EXIT%
