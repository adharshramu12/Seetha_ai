@echo off
title Seetha AI - Open Source Edition
echo ============================================
echo    SEETHA AI - Open Source Edition v3.0
echo ============================================
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] First run: creating virtual environment...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

REM Install/refresh dependencies whenever requirements.txt is newer
REM than the last successful install (keeps updates painless).
if not exist ".venv\.deps_installed" goto install_deps
for /f %%i in ('dir /b /o:d ".venv\.deps_installed" "requirements.txt" 2^>nul') do set NEWEST=%%i
if "%NEWEST%"=="requirements.txt" goto install_deps
goto run_app

:install_deps
echo [INFO] Installing dependencies (first run may take a few minutes)...
.venv\Scripts\python -m pip install --upgrade pip --quiet
.venv\Scripts\python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency install failed. Check your internet connection.
    echo         If PyAudio failed, run:  .venv\Scripts\pip install pipwin ^&^& .venv\Scripts\pipwin install pyaudio
    pause
    exit /b 1
)
echo done > ".venv\.deps_installed"

:run_app
echo [INFO] Starting Seetha...
.venv\Scripts\python -m seetha.main
pause
