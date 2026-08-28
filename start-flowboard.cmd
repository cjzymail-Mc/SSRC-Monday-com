@echo off
setlocal

cd /d "%~dp0"

set "FLOWBOARD_DB=%~dp0flowboard.db"
set "FLOWBOARD_ATTACHMENT_DIR=%~dp0flowboard-attachments"
set "FLOWBOARD_BACKUP_DIR=%~dp0backups"
set "FLOWBOARD_HOST=0.0.0.0"
set "FLOWBOARD_PORT=8080"
set "FLOWBOARD_SECURE_COOKIE="

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

if not exist "%FLOWBOARD_DB%" (
    echo [ERROR] Local database not found: %FLOWBOARD_DB%
    pause
    exit /b 1
)

python -X utf8 -c "import sqlite3,sys; from flowboard.database import SCHEMA_VERSION; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); v=c.execute('PRAGMA user_version').fetchone()[0]; ok=c.execute('PRAGMA integrity_check').fetchone()[0]; fk=len(c.execute('PRAGMA foreign_key_check').fetchall()); c.close(); print(f'[INFO] Database schema: v{v}; required: v{SCHEMA_VERSION}; integrity: {ok}; foreign keys: {fk}'); raise SystemExit(0 if v==SCHEMA_VERSION and ok=='ok' and fk==0 else 3)" "%FLOWBOARD_DB%"
if errorlevel 3 (
    echo [ERROR] Database preflight failed. Do not start until the local database is backed up and upgraded.
    pause
    exit /b 3
)
if errorlevel 1 (
    echo [ERROR] Database preflight could not run.
    pause
    exit /b 1
)

if /i "%~1"=="--check" (
    echo [OK] Flowboard local launcher is ready.
    echo [INFO] Database: %FLOWBOARD_DB%
    exit /b 0
)

if not exist "%FLOWBOARD_ATTACHMENT_DIR%" mkdir "%FLOWBOARD_ATTACHMENT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot create attachment directory: %FLOWBOARD_ATTACHMENT_DIR%
    pause
    exit /b 1
)
if not exist "%FLOWBOARD_BACKUP_DIR%" mkdir "%FLOWBOARD_BACKUP_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot create backup directory: %FLOWBOARD_BACKUP_DIR%
    pause
    exit /b 1
)

echo.
echo Flowboard local LAN service
echo Database: %FLOWBOARD_DB%
echo Port: %FLOWBOARD_PORT%
echo Keep this window open while colleagues are using Flowboard.
echo Press Ctrl+C to stop.
echo.

python -u server.py
set "SERVER_EXIT=%ERRORLEVEL%"

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo [ERROR] Flowboard stopped with exit code %SERVER_EXIT%.
    pause
)

exit /b %SERVER_EXIT%
