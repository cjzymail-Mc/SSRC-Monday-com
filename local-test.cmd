@echo off
setlocal

cd /d "%~dp0"

set "FLOWBOARD_LOCAL_TEST_DIR=%~dp0local-test-data"
set "FLOWBOARD_DB=%FLOWBOARD_LOCAL_TEST_DIR%\flowboard.db"
set "FLOWBOARD_ATTACHMENT_DIR=%FLOWBOARD_LOCAL_TEST_DIR%\attachments"
set "FLOWBOARD_BACKUP_DIR=%FLOWBOARD_LOCAL_TEST_DIR%\backups"
set "FLOWBOARD_HOST=127.0.0.1"
set "FLOWBOARD_PORT=8081"
set "FLOWBOARD_SECURE_COOKIE="
set "FLOWBOARD_INITIAL_PASSWORD=localtest"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

if not exist "%FLOWBOARD_LOCAL_TEST_DIR%" mkdir "%FLOWBOARD_LOCAL_TEST_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot create local test directory: %FLOWBOARD_LOCAL_TEST_DIR%
    pause
    exit /b 1
)

python -X utf8 flowboard_dev_seed.py
if errorlevel 1 (
    echo [ERROR] Local test database initialization failed.
    pause
    exit /b 1
)

if /i "%~1"=="--check" (
    echo [OK] Flowboard local test launcher is ready.
    exit /b 0
)

echo.
echo Flowboard local test service
echo URL: http://127.0.0.1:%FLOWBOARD_PORT%
echo Database: %FLOWBOARD_DB%
echo Developer login: test / test ^(full local admin access^)
echo Permission test logins: u2 / localtest ^(member^), u3 / localtest ^(viewer^)
echo Press Ctrl+C to stop.
echo.

python -u server.py
set "SERVER_EXIT=%ERRORLEVEL%"

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo [ERROR] Flowboard local test service stopped with exit code %SERVER_EXIT%.
    pause
)

exit /b %SERVER_EXIT%
