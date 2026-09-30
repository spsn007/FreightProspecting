@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo FreightProspecting V1 — Local Application Launcher (Stage 2.5)
echo ======================================================================
echo Target Workspace: D:\FreightProspecting
echo Runtime: Pure Local Python + SQLite WAL (Zero External APIs)
echo.

:: 1. Check Python Virtual Environment
if not exist "D:\FreightProspecting\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at D:\FreightProspecting\.venv
    echo Please create or restore the virtual environment before launching.
    pause
    exit /b 1
)

:: 2. Prepare Server Port (Safely manage port 8000 and avoid stale orphan processes)
"D:\FreightProspecting\.venv\Scripts\python.exe" scripts\prepare_server_port.py
if errorlevel 1 (
    echo [ERROR] Cannot start FreightProspecting because port 8000 is occupied.
    pause
    exit /b 1
)

:: 3. Check Database Integrity
if not exist "D:\FreightProspecting\data\prospects.db" (
    echo [WARNING] prospects.db not found at data\prospects.db.
    echo Initializing database schema...
    "D:\FreightProspecting\.venv\Scripts\python.exe" scripts\init_db.py --seed
)

echo [OK] Python runtime: D:\FreightProspecting\.venv
echo [OK] Database: D:\FreightProspecting\data\prospects.db
echo.
echo Starting local web server on http://127.0.0.1:8000 ...
echo (Press CTRL+C in this window to stop the server)
echo.

:: 4. Launch default web browser after short delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000/"

:: 5. Execute Uvicorn bound strictly to localhost with auto-reload
"D:\FreightProspecting\.venv\Scripts\python.exe" -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload

endlocal
