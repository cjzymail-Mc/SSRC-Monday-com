@echo off
setlocal

cd /d "%~dp0"

set "TRIAL_ROOT=%TEMP%\flowboard-gate5-trial"
set "TRIAL_DB=%TRIAL_ROOT%\flowboard-trial.db"

if not exist "flowboard.db" (
    echo [ERROR] flowboard.db not found in the repository root.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

if not exist "%TRIAL_ROOT%" mkdir "%TRIAL_ROOT%"
if errorlevel 1 (
    echo [ERROR] Cannot create trial directory: %TRIAL_ROOT%
    pause
    exit /b 1
)

if not exist "%TRIAL_DB%" (
    copy /y "flowboard.db" "%TRIAL_DB%" >nul
    if errorlevel 1 (
        echo [ERROR] Cannot create the isolated trial database.
        pause
        exit /b 1
    )
    echo [INFO] Created an isolated copy of flowboard.db.
) else (
    echo [INFO] Reusing the existing trial database.
)

set "FLOWBOARD_DB=%TRIAL_DB%"
set "FLOWBOARD_ATTACHMENT_DIR=%TRIAL_ROOT%\attachments"
set "FLOWBOARD_BACKUP_DIR=%TRIAL_ROOT%\backups"

if /i "%~1"=="--check" (
    echo [OK] Trial launcher is ready.
    echo [INFO] Database: %FLOWBOARD_DB%
    exit /b 0
)

echo.
echo Flowboard Gate 5 trial
echo URL: http://localhost:8080
echo Database: %FLOWBOARD_DB%
echo The real repository database will not be modified.
echo Press Ctrl+C to stop the service.
echo.

python server.py
set "SERVER_EXIT=%ERRORLEVEL%"

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo [ERROR] Flowboard stopped with exit code %SERVER_EXIT%.
    pause
)

exit /b %SERVER_EXIT%
